import argparse
import math
import os
import subprocess
from pathlib import Path
import torch

class Arguments():
    None


def smallest_factor(n):
    return sorted([i for i in range(1, int(n**0.5) + 1) if n%i==0 and n/i>=200000 and n/i<=400000])


def run_dump_phrase(args):
    def get_cmd(start_doc, end_doc, device, batch_size):
        return ["python", "encode_wikipedia_articles.py",
                "--predict_file", f"{start_doc}:{end_doc}",
                "--device", f"{device}", "--batch_size", f"{batch_size}"]

    num_docs = args.end - args.start
    num_gpus = torch.cuda.device_count()
    num_docs_per_gpu = int(math.ceil(num_docs / num_gpus))
    start_docs = list(range(args.start, args.end, num_docs_per_gpu))
    end_docs = start_docs[1:] + [args.end]
    batch_size = int(num_docs_per_gpu / smallest_factor(num_docs_per_gpu)[0])
    

    for device_idx, (start_doc, end_doc) in enumerate(zip(start_docs, end_docs)):
        print(get_cmd(start_doc, end_doc, device_idx, batch_size))
        subprocess.Popen(get_cmd(start_doc, end_doc, device_idx, batch_size))


def get_args():
    args = Arguments()
    args.start = 0
    args.end = len(list(Path("formatted-wikipedia-articles").rglob(f"*.json")))

    return args


def main():
    args = get_args()
    run_dump_phrase(args)


if __name__ == '__main__':
    main()

