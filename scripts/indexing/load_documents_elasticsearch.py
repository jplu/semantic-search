import argparse
import os
import json
import timeit
import distutils.util
import urllib3
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import multiprocessing as mp
from psutil import cpu_count
import pathlib
import ray
import pyarrow
from asyncio import Event
from typing import Dict, List, Tuple
import pandas as pd
import time

from tqdm import tqdm
from elasticsearch import Elasticsearch
from elasticsearch.helpers import streaming_bulk


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


def preprocess(documents: pyarrow.Table) -> List[Dict]:
    dict_documents = documents.to_pydict()
    list_documents = list(zip(dict_documents["id"], dict_documents["url"], dict_documents["paragraphs"], dict_documents["title"]))
    es_documents = []

    for doc in list_documents:
        title = doc[3]
        id = doc[0]
        url = doc[1]
        
        for paragraph in doc[2]:
            source = paragraph
            source["title"] = title
            source["id"] = id
            source["url"] = url
            doc = {
                '_op_type': 'create',
                "_id": paragraph["pid"],
                "_source": source
            }
            
            es_documents.append(doc)

    return es_documents


def create_pipeline(data_dir: pathlib.Path, num_shards: int) -> List[ray.data.dataset.Dataset]:
    return ray.data.read_json(data_dir.as_posix()) \
        .map_batches(preprocess) \
        .split(num_shards)


@ray.remote
class Worker:
    def __init__(self, rank: int, shard: ray.data.dataset.Dataset, args: argparse.Namespace):
        self.rank = rank
        self.shard = shard
        self.index_name = args.index

        if args.is_secure:
            import ssl
            from elasticsearch.connection import create_ssl_context

            ssl_context = create_ssl_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            self.es_client = Elasticsearch(
                args.hosts.split(","),
                http_auth=(args.login, args.password) if args.login and args.password else None,
                scheme=args.scheme,
                port=args.port,
                timeout=300,
                retry_on_timeout=True,
                max_retries=10,
                maxsize=cpu_count() if args.remote else 1,
                ssl_context=ssl_context,
            )
        else:
            self.es_client = Elasticsearch(
                args.hosts.split(","),
                http_auth=(args.login, args.password) if args.login and args.password else None,
                scheme=args.scheme,
                port=args.port,
                timeout=300,
                retry_on_timeout=True,
                max_retries=10,
                maxsize=cpu_count() if args.remote else 1,
            )
    
    def data_generator(self):
        for batch in self.shard.iter_batches(batch_size=1):
            yield(batch[0])

    def load(self, pba: ProgressBarActor = None) -> pd.DataFrame:
        good, missing, errors = 0, 0, 0
        bulk_args = {
            "client": self.es_client,
            "index": self.index_name,
            "max_retries": 1000,
            "chunk_size": 1000,
            "actions": self.data_generator(),
        }
        count = 0

        for ok, result in streaming_bulk(raise_on_exception=False, raise_on_error=False, **bulk_args):
            _, result = result.popitem()
            status_code = result.get('status', 500)

            if ok:
                good += 1
            elif status_code == 'TIMEOUT':
                errors += 1
            elif status_code == 404:
                missing += 1
            elif not isinstance(status_code, int):
                errors += 1
            elif status_code >= 400 and status_code < 500:
                errors += 1
            
            count += 1
            
            if count % 100 == 0:
                pba.update.remote(100)
                count = 0

        if count > 0:
            pba.update.remote(count)
        
        assert good + missing + errors == self.shard.count()

        return good, missing, errors



def init_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTION] ...",
        description="Load the documents in Elasticsearch."
    )
    parser.add_argument(
        "-v", "--version", action="version",
        version = f"{parser.prog} version 1.0.0"
    )
    parser.add_argument(
        "--update", action='store_true', help="Update the index instead of delete (if already exists) and create."
    )
    parser.add_argument(
        "--scheme", type=str, default="http", help="Update the index instead of delete (if already exists) and create."
    )
    parser.add_argument(
        "--login", type=str, help="Elasticsearch login. Superseded by the ES_LOGIN env variable if it exists."
    )
    parser.add_argument(
        "--password", type=str, help="Elasticsearch password. Superseded by the ES_PASSWORD env variable if it exists."
    )
    parser.add_argument(
        "--port", type=int, default=9200, help="Elasticsearch port."
    )
    parser.add_argument(
        "--is_secure", action='store_true', help="If the connection with Elasticsearch goes through SSL."
    )
    
    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "-l", "--local", action='store_true', help="Run the process locally."
    )
    group.add_argument(
        "-r", "--remote", action='store_true', help="Run the process remotely on a cluster."
    )

    requiredNamed = parser.add_argument_group('required arguments')

    requiredNamed.add_argument(
        "--input", type=pathlib.Path, help="Folder containing the formatted JSON file(s) to load.", required=True
    )
    requiredNamed.add_argument(
        "--hosts", type=str, nargs='?', help="Elasticsearch hosts. Multiple hosts must be comma separated.", required=True
    )
    requiredNamed.add_argument(
        "--index", type=str, help="Elasticsearch index name.", required=True
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
    
    if os.getenv('ES_LOGIN'):
        args.login = os.getenv('ES_LOGIN')
    
    if os.getenv('ES_PASSWORD'):
        args.password = os.getenv('ES_PASSWORD')
    
    if args.password and not args.login:
        raise ValueError("--login is mandatory if the --password argument or ES_PASSWORD var env is given.")
    
    if not args.password and args.login:
        raise ValueError("--password is mandatory if the --login argument or ES_LOGIN var env is given.")
    
    if args.local and args.remote:
        raise ValueError("--local and --remote are exclusive arguments.")
    
    if not args.local and not args.remote:
        raise ValueError("You must add either the --local or --remote argument")
    
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
    
    if args.is_secure:
        import ssl
        from elasticsearch.connection import create_ssl_context

        ssl_context = create_ssl_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        es_client = Elasticsearch(
            args.hosts.split(","),
            http_auth=(args.login, args.password) if args.login and args.password else None,
            scheme=args.scheme,
            port=args.port,
            timeout=300,
            retry_on_timeout=True,
            max_retries=10,
            maxsize=cpu_count() if args.remote else 1,
            ssl_context=ssl_context,
        )
    else:
        es_client = Elasticsearch(
            args.hosts.split(","),
            http_auth=(args.login, args.password) if args.login and args.password else None,
            scheme=args.scheme,
            port=args.port,
            timeout=300,
            retry_on_timeout=True,
            max_retries=10,
            maxsize=cpu_count() if args.remote else 1,
        )

    if args.update:
        logger.info(f"Update the index {args.index}")
    else:
        logger.info(f"Delete (if already exists) and create the index {args.index}")
        es_client.indices.delete(index=args.index, ignore=[400, 404])
        es_client.indices.create(index=args.index, ignore=400)
    
    splits = create_pipeline(args.input, args.workers)
    total = 0
    workers = []

    for rank, shard in enumerate(splits):
        workers.append(Worker.remote(rank, shard, args))
        total += shard.count()
    
    pb = ProgressBar(total)
    actor = pb.actor
    tasks = [worker.load.remote(actor) for worker in workers]
    good, missing, errors = 0, 0, 0

    pb.print_until_done()

    start_time = timeit.default_timer()

    while len(tasks):
        done_task, tasks = ray.wait(tasks)
        current_good, current_missing, current_errors = ray.get(done_task[0])
        good += current_good
        missing += current_missing
        errors += current_errors
    
    logger.info(f"Time taken: {timeit.default_timer() - start_time} sec")
    logger.info(f"Completed import with {good} success, {missing} missing and {errors} errors")


if __name__ == "__main__":
    main()
