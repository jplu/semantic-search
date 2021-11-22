import argparse
import logging
import os
import pathlib
import time
import timeit
import uuid

from asyncio import Event
from typing import Tuple, List

import onnxruntime
import pandas as pd
import pyarrow
import ray

from psutil import cpu_count
from tqdm import tqdm
from transformers import AutoTokenizer


logger = logging.getLogger(__name__)


@ray.remote
class ProgressBarActor:
    def __init__(self):
        self.counter = 0
        self.delta = 0
        self.event = Event()

    def update(self, num_items_completed):
        self.counter += num_items_completed
        self.delta += num_items_completed
        
        self.event.set()

    async def wait_for_update(self) -> Tuple[int, int]:
        await self.event.wait()
        self.event.clear()

        saved_delta = self.delta
        self.delta = 0
        
        return saved_delta, self.counter

    def get_counter(self) -> int:
        return self.counter


class ProgressBar:
    def __init__(self, total: int, description: str = ""):
        self.progress_actor = ProgressBarActor.remote()
        self.total = total
        self.description = description

    @property
    def actor(self) -> ProgressBarActor:
        return self.progress_actor

    def print_until_done(self) -> None:
        pbar = tqdm(desc=self.description, total=self.total)

        while True:
            delta, counter = ray.get(self.actor.wait_for_update.remote())

            pbar.update(delta)

            if counter >= self.total:
                pbar.close()

                return


def preprocess(documents: pyarrow.Table) -> pd.DataFrame:
    df_documents = documents.to_pandas()
    dataset = []

    for row in zip(df_documents['paragraphs'], df_documents['title']):
        for paragraph in row[0]:
            dataset.append([paragraph["pid"], row[1], paragraph["context"]])
        
    return pd.DataFrame(dataset, columns=["pid", "title", "context"])


def create_pipeline(data_dir: pathlib.Path, num_shards: int) -> List[ray.data.dataset.Dataset]:
    return ray.data.read_json(data_dir.as_posix()) \
        .map_batches(preprocess) \
        .split(num_shards)


@ray.remote
class Worker:
    def __init__(self, model_path: pathlib.Path, tokenizer: str, rank: int, shard: ray.data.dataset.Dataset, is_remote: bool = False):
        self.rank = rank
        self.shard = shard
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer)
        sess_options = onnxruntime.SessionOptions()
        sess_options.intra_op_num_threads = cpu_count() if is_remote else 1
        sess_options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.model = onnxruntime.InferenceSession(model_path.as_posix(), sess_options, providers=["CPUExecutionProvider"])

    def infer(self, pba: ProgressBarActor = None) -> pd.DataFrame:
        encoded = []
        count = 0
        
        for batch in self.shard.iter_batches(batch_size=1):
            batch_dict = batch.to_pydict()
            title_context = list(zip(batch_dict["title"], batch_dict["context"]))
            tokenized_dataset = self.tokenizer.batch_encode_plus(title_context, return_tensors="pt", padding="longest", truncation=True, max_length=512)
            tokenized_dataset = {name : value.cpu().detach().numpy() for name, value in tokenized_dataset.items()}
            outputs = self.model.run(None, tokenized_dataset)
            
            for id, vector in zip(batch_dict["pid"], outputs[0]):
                encoded.append([id, vector])
            
            count += 1

            if count % 100 == 0:
                pba.update.remote(100)
                count = 0

        if count > 0:
            pba.update.remote(count)

        pdf = pd.DataFrame(encoded, columns=["pid", "vector"])

        assert len(encoded) == self.shard.count() == len(pdf.index)

        return pdf


def init_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTION] ...",
        description="Vectorizing textual content with an encoding model."
    )
    parser.add_argument(
        "--version", action="version",
        version = f"{parser.prog} version 1.0.0"
    )

    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "--local", action='store_true', help="Run the process locally."
    )
    group.add_argument(
        "--remote", action='store_true', help="Run the process remotely on a cluster."
    )

    requiredNamed = parser.add_argument_group('required arguments')

    requiredNamed.add_argument(
        "--input", type=pathlib.Path, help="Folder containing the JSON file(s) to encode.", required=True
    )
    requiredNamed.add_argument(
        "--model", type=pathlib.Path, help="The ONNX model to use for encoding.", required=True
    )
    requiredNamed.add_argument(
        "--workers", type=int, help="Number of encoding worker to run in parallel. If run locally this number should not be higher than the number of available threads. If run remotely this number should not be higher than the number of available nodes in the cluster.", required=True
    )
    requiredNamed.add_argument(
        "--tokenizer", type=str, help="The HuggingFace tokenizer to use.", required=True
    )
    requiredNamed.add_argument(
        "--output", type=pathlib.Path, help="Folder where to save the vectors in Parquet format.", required=True
    )
    
    return parser


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO,
    )

    parser = init_argparse()
    args = parser.parse_args()

    if args.local:
        ray.init()

        os.environ["TOKENIZERS_PARALLELISM"] = "true"

        if args.workers > cpu_count():
            raise ValueError(f"{args.workers} cannot be higher than {cpu_count()}")
    else:
        ray.init(address='auto')
        
        while len(ray.nodes()) < args.workers:
                logger.info(
                    f"waiting for nodes to start up: {len(ray.nodes())}/{args.workers}"
                )
                time.sleep(10)
    
    final_output = args.output / str(uuid.uuid1())

    final_output.mkdir(parents=True, exist_ok=True)

    splits = create_pipeline(args.input, args.workers)
    total = 0
    workers = []

    for rank, shard in enumerate(splits):
        workers.append(Worker.remote(args.model, args.tokenizer, rank, shard, args.remote))
        total += shard.count()

    pb = ProgressBar(total)
    actor = pb.actor
    tasks = [worker.infer.remote(actor) for worker in workers]

    pb.print_until_done()

    start_time = timeit.default_timer()

    while len(tasks):
        done_task, tasks = ray.wait(tasks)
        encoding_results = ray.get(done_task[0])
        encoding_results.to_parquet((final_output / str(uuid.uuid1())).as_posix() + ".parquet")
    
    logger.info(f"Time taken: {timeit.default_timer() - start_time} sec")
    logger.info(f"The Parquet files are in {final_output}")


if __name__ == "__main__":
    main()