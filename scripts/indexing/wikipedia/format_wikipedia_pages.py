import argparse
import datetime
import json
import logging
import pathlib
import time
import timeit
import uuid

from asyncio import Event
from typing import Dict, Tuple, List

import ray

from psutil import cpu_count
from tqdm import tqdm


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


def create_pipeline(data_dir: pathlib.Path, num_shards: int) -> List[ray.data.dataset.Dataset]:
    if not any(data_dir.iterdir()):
        raise ValueError(f"Folder {data_dir.as_posix()} is empty.")
    
    json_files = list(pathlib.Path(data_dir.as_posix()).rglob(f"*.json"))

    return ray.data.from_items(json_files).split(num_shards)


@ray.remote
class Worker:
    def __init__(self, min_len_paragraph: int, max_len_paragraph: int, rank: int, shard: ray.data.dataset.Dataset):
        self.rank = rank
        self.shard = shard
        self.max_len_paragraph = max_len_paragraph
        self.min_len_paragraph = min_len_paragraph
    
    def parse_wikipedia_page(self, page_path):
        try:
            with open(page_path.as_posix(), encoding="utf-8") as f:
                page = json.load(f)
        
            if len(page["text"]) == 0:
                return None

            paragraphes = page["text"].strip().split('\n')
            page["paragraphs"] = []

            for paragraph in paragraphes:
                if len(paragraph) >= self.min_len_paragraph and len(paragraph) <= self.max_len_paragraph:
                    page["paragraphs"].append({"context": paragraph})

            if len(page["paragraphs"]) == 0:
                return None
        
            page["title"] = page["url"].split("/")[-1].replace("_", " ")
        
            del page["text"]
            del page["categories"]
            del page["infobox_types"]
            del page["annotations"]

            return page
        except UnicodeDecodeError as err:
            return None

    def run_parse(self, pba: ProgressBarActor = None) -> Tuple[int, Dict]:
        parsed_wikipedia_pages = []
        count = 0
        unreadable_pages = 0
        
        for batch in self.shard.iter_batches(batch_size=1):
            parsed_wikipedia_page = self.parse_wikipedia_page(batch[0])
            
            if parsed_wikipedia_page:
                counter = 0
                for passage in parsed_wikipedia_page["paragraphs"]:
                    passage["pid"] = int(str(parsed_wikipedia_page["id"]) + str(counter).zfill(4))
                    counter += 1
                parsed_wikipedia_pages.append(parsed_wikipedia_page)
            else:
                unreadable_pages += 1
            
            count += 1

            if count % 100 == 0:
                pba.update.remote(100)
                count = 0

        if count > 0:
            pba.update.remote(count)

        assert len(parsed_wikipedia_pages) + unreadable_pages == self.shard.count()

        return unreadable_pages, parsed_wikipedia_pages


def init_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTION] ...",
        description="Format and split Wikipedia articles into paragraphs."
    )
    parser.add_argument(
        "-v", "--version", action="version",
        version = f"{parser.prog} version 1.0.0"
    )
    parser.add_argument(
        "--max_len_paragraph", type=int, default=2500, help="Max number of character of a paragraph. Those with a higher number will be ignored. (default: 2500)"
    )
    parser.add_argument(
        "--min_len_paragraph", type=int, default=125, help="Min number of character of a paragraph. Those with a lower number will be ignored. (default: 125)"
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
        "--output", type=pathlib.Path, help="Folder where to save the vectors in Parquet format.", required=True
    )
    requiredNamed.add_argument(
        "--workers", type=int, help="Number of encoding worker to run in parallel. If run locally this number should not be higher than the number of available threads. If run remotely this number should not be higher than the number of available nodes in the cluster.", required=True
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

    if not args.remote and not args.local:
        raise ValueError("One of the arguments --local or --remote is mandatory.")

    if args.local:
        ray.init()

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
        workers.append(Worker.remote(args.min_len_paragraph, args.max_len_paragraph, rank, shard))
        total += shard.count()

    pb = ProgressBar(total)
    actor = pb.actor
    start_time = timeit.default_timer()
    tasks = [worker.run_parse.remote(actor) for worker in workers]

    pb.print_until_done()

    total_unreadable_pages = 0

    while len(tasks):
        done_task, tasks = ray.wait(tasks)
        unreadable_pages, formatted_pages = ray.get(done_task[0])
        total_unreadable_pages += unreadable_pages
        
        for page in formatted_pages:
            filepath = (final_output / str(page["id"])).as_posix() + ".json"
            with open(filepath, "w", encoding="utf-8") as file:
                json.dump(page, file, indent=4)
                file.flush()

    duration = datetime.timedelta(seconds=timeit.default_timer() - start_time)
    duration_seconds = datetime.timedelta(seconds=duration.seconds)
    hours, minutes, seconds = str(duration_seconds).split(":")

    logger.info(f"Time taken: {duration.days} days {hours} hours {minutes} minutes {seconds} seconds {duration.microseconds} microseconds sec")
    logger.info(f"The formatted Wikipedia pages are in {final_output}")
    logger.info(f"{total_unreadable_pages} pages couldn't be read.")


if __name__ == "__main__":
    main()