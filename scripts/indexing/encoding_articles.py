import logging
import timeit
import os
import json
import argparse
import math

from pathlib import Path

import faiss
import torch
import numpy as np

from tqdm import tqdm
from sentence_transformers import SentenceTransformer


logger = logging.getLogger(__name__)
os.environ["TOKENIZERS_PARALLELISM"] = "true"
os.environ["MKL_SERVICE_FORCE_INTEL"] = "1"


def smallest_factor(n):
    return sorted([i for i in range(1, int(n**0.5) + 1) if n%i==0 and n/i>=200000 and n/i<=400000])


def encode_articles(args, model):
    if not os.path.exists(args.output_folder):
        os.makedirs(args.output_folder)

    start_time = timeit.default_timer()
    
    if args.predict_file == "all":
        predict_files = list(Path(args.wikipedia_folder).rglob(f"*.json"))
    elif ':' not in args.predict_file:
        predict_files = [args.predict_file]
    else:
        start, end = args.predict_file.split(':')

        def last_id(x):
            return int(x.stem.split("-")[1])

        all_files = list(Path(args.wikipedia_folder).rglob(f"*.json"))
        all_files = sorted(all_files, key=last_id)
        predict_files = all_files[int(start):int(end)+1]

    total_files = len(predict_files)

    if args.batch_size == 0:
        args.batch_size = int(total_files / smallest_factor(total_files)[0])
    
    assert total_files % args.batch_size == 0
    
    batches_idx = list(range(0, len(predict_files), args.batch_size))
    count_total_examples = 0
    count_processed_files = 0

    for batch_idx in tqdm(batches_idx, desc="Encoding"):
        dataset = {}
        outputs = []
        batch_predict_files = predict_files[batch_idx:batch_idx+args.batch_size]
        from_idx = batch_predict_files[0].stem.split("-")[1]
        to_idx = batch_predict_files[-1].stem.split("-")[1]
        
        if not os.path.exists(os.path.join(args.output_folder, f"{from_idx}-{to_idx}.faiss")):
            for predict_file in batch_predict_files:
                count_processed_files += 1
                logger.info(f"***** Read paragraphs from {predict_file} -- {total_files - count_processed_files} files remaining *****")
            
                with open(predict_file, encoding="utf-8") as f:
                    article = json.load(f)
            
                for paragraph in article["paragraphs"]:
                    dataset[paragraph["pid"]] = [article["title"], paragraph["context"]]
            
        
            logger.info("  Num examples = %d", len(dataset))

            count_total_examples += len(dataset)
            start_time = timeit.default_timer()
            outputs = model.encode(list(dataset.values()), show_progress_bar=True, batch_size=128, convert_to_numpy=True, device=args.device, normalize_embeddings=True)
            end_time = timeit.default_timer() - start_time

            logger.info(f"Encoding done in {end_time} secs ({end_time / len(dataset)} sec per example)")

            assert len(outputs) == len(list(dataset.keys()))
        
            start_time = timeit.default_timer()
            quantizer = faiss.IndexFlatIP(768)
            #1048576
            index_ivf_flat = faiss.IndexIVFFlat(quantizer, 768, 1048576, faiss.METRIC_INNER_PRODUCT)
            res = faiss.StandardGpuResources()

            res.noTempMemory()
            res.setPinnedMemory(0)
            
            co = faiss.GpuClonerOptions()
            co.useFloat16 = True
            gpu_index = faiss.index_cpu_to_gpu(res, args.device, index_ivf_flat, co)
            gpu_index.verbose = True
        
            gpu_index.train(outputs)
        
            index = faiss.index_gpu_to_cpu(gpu_index)
            index_ivf = faiss.extract_index_ivf(index)
        
            index_ivf.add_with_ids(outputs, np.asarray(list(dataset.keys()), dtype=np.int64))
            faiss.write_index(index_ivf, os.path.join(args.output_folder, f"{from_idx}-{to_idx}.faiss"))
            index_ivf.reset()
            index.reset()
            gpu_index.reset()
            index_ivf_flat.reset()
        else:
            count_processed_files += len(batch_predict_files)
    
    end_time = timeit.default_timer() - start_time

    logger.info(f"indexing done in {end_time} secs")
    logger.info(f'Total number of examples: {count_total_examples}')


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default=0, type=int)
    parser.add_argument('--batch_size', default=0, type=int)
    parser.add_argument('--predict_file', default="all", type=str)
    args = parser.parse_args()

    return args


def main(args):
    args.wikipedia_folder = "formatted-wikipedia-articles"
    args.output_folder = "encoded-wikipedia-articles"
    start_time = timeit.default_timer()

    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO,
    )

    logger.info(
        "device: %s",
        args.device,
    )

    model = SentenceTransformer('MODEL/NAME', device=args.device)

    model.max_seq_length = 512
    
    logger.info('Number of model params while dumping: {:,}'.format(sum(p.numel() for p in model.parameters())))
    
    encode_articles(args, model)

    logger.info(f"Time taken: {timeit.default_timer() - start_time} sec")

if __name__ == "__main__":
    args = get_args()
    main(args)
