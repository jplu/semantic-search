import time
import json
import queue
import math
import os
from queue import Empty
from pathlib import Path

from tqdm.auto import tqdm
import multiprocessing as mp


class Arguments():
    None


def print_qsize(event, precv_pipe, queue):
    pbar = tqdm(bar_format="{desc}")
    while not (event.is_set() and queue.empty()):
        if not precv_pipe.poll():
            continue

        remaining, name = precv_pipe.recv()
        pbar.desc = f"rem : {remaining:4}, current : {name}"
        pbar.update()
    pbar.close()


def parse_article(args, article_path):
    try:
        with open(article_path.as_posix(), encoding="utf-8") as f:
            article = json.load(f)
    
        if len(article["text"]) == 0:
            return None

        paragraphes = article["text"].strip().split('\n')
        article["paragraphs"] = []

        for paragraph in paragraphes:
            if len(paragraph) >= args.min_chars and len(paragraph) <= args.max_chars:
                article["paragraphs"].append({"context": paragraph})

        if len(article["paragraphs"]) == 0:
            return None
    
        article["title"] = article["url"].split("/")[-1].replace("_", " ")
    
        del article["text"]
        del article["categories"]
        del article["infobox_types"]
        del article["annotations"]

        return article
    except UnicodeDecodeError as err:
        return None

### Producer

def read_articles_into_q(args, queue, event, psend_pipe):
    article_list = list(args.articles_dir.rglob(f"*.json"))
    article_list.sort()
    start_size = len(article_list)

    def filter_existing_valid_files(path):
        already_formatted_articles_list = list(args.output_dir.rglob(f"*{path.stem}*"))
        if len(already_formatted_articles_list) > 0:
            try:
                with open(already_formatted_articles_list[0].as_posix(), encoding="utf-8") as f:
                    _ = json.load(f)
                    
                    return False
            except UnicodeDecodeError as err:
                return True
        else:
            ret = parse_article(args, path)

        return True if ret else False

    print("Filtering articles")
    article_list_iterator = filter(filter_existing_valid_files, article_list)
    article_list = list(article_list_iterator)
    article2index = {article_path:str(index).zfill(9) for index, article_path in enumerate(article_list)}
    print(f"Will process {len(article_list)} articles. {start_size - len(article_list)} articles will be ignored because either they already exists or they are redirect, disambiguation,... or their paragraphs have not a length between {args.min_chars} and {args.max_chars} characters.")

    while len(article_list) > 0:
        if queue.full():
            continue
        else:
            article_path = article_list.pop()
            article = parse_article(args, article_path)
            queue.put((article, article_path, article2index[article_path]))
            psend_pipe.send((len(article_list), article_path.stem))
            
    event.set()
    queue.join()


### Consumer

def write_formatted_article(args, queue, event):
    while not (event.is_set() and queue.empty()):
        try:
            article, article_path, index = queue.get(block=True, timeout=0.1)
        except Empty:
            continue
        
        file_path = args.output_dir.joinpath(f"{article_path.stem}-{index}.json")

        queue.task_done()
        handle_output(article, file_path)


def handle_output(article, file_path):
    counter = 0
    for passage in article["paragraphs"]:
        passage["pid"] = int(str(article["id"]) + str(counter).zfill(4))
        counter += 1
    with open(file_path.as_posix(), "w", encoding="utf-8") as file:
        json.dump(article, file, indent=4)
        file.flush()


### Caller

def caller(args, formatter_count, qsize):
    start = time.time()
    queue = mp.JoinableQueue(qsize)
    event = mp.Event()
    precv_pipe, psend_pipe = mp.Pipe(duplex=False)
    closables = [queue, precv_pipe, psend_pipe]
    reader_process = mp.Process(target=read_articles_into_q, args=(args, queue, event, psend_pipe))
    formatter_processes = [mp.Process(target=write_formatted_article, args=(args, queue, event)) for i in range(formatter_count)]
    
    reader_process.start()
    [ep.start() for ep in formatter_processes]

    print_qsize(event, precv_pipe, queue)

    [ep.join() for ep in formatter_processes]
    reader_process.join()

    [ep.close() for ep in closables]
    reader_process.close()
    print(f"time taken : {time.time() - start} s.")

if __name__ == "__main__":
    args = Arguments()
    args.articles_dir = Path("./extracted-wikipedia-articles")
    args.output_dir = Path("./formatted-wikipedia-articles")
    args.min_chars = 125
    args.max_chars = 2500
    
    os.makedirs(args.output_dir, exist_ok=True)

    qsize = math.ceil(len(list(args.articles_dir.rglob(f"*.json"))) / mp.cpu_count())
    caller(args, formatter_count=mp.cpu_count(), qsize=qsize)

