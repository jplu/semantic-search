import argparse
import datetime
import logging
import math
import pathlib
import timeit
import uuid

import faiss
import numpy as np
import pandas as pd


logger = logging.getLogger(__name__)


def convert_to_faiss(input_path: pathlib.Path, output_path: pathlib.Path) -> None:
    parquet_files = list(pathlib.Path(input_path.as_posix()).rglob(f"*.parquet"))
    df = pd.DataFrame(columns=['pid', 'vector'])
    
    for parquet_file in parquet_files:
        df = df.append(pd.read_parquet(parquet_file), ignore_index=True)
        
    ndim = df["vector"][0].shape[0]
    quantizer = faiss.IndexFlatIP(ndim)
    index_ivf_flat = faiss.IndexIVFFlat(quantizer, ndim, 4 * math.ceil(math.sqrt(df.shape[0])), faiss.METRIC_INNER_PRODUCT)
    
    index_ivf_flat.train(np.vstack(df["vector"].to_numpy()))
    index_ivf_flat.add_with_ids(np.vstack(df["vector"].to_numpy()), df["pid"].to_numpy(dtype=np.int64))
    
    faiss.write_index(index_ivf_flat, output_path.as_posix())


def init_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTION] ...",
        description="Create the faiss index from Parquet files."
    )
    parser.add_argument(
        "--version", action="version",
        version = f"{parser.prog} version 1.0.0"
    )

    requiredNamed = parser.add_argument_group('required arguments')

    requiredNamed.add_argument(
        "--input", type=pathlib.Path, help="Folder containing the Parquet file(s).", required=True
    )
    requiredNamed.add_argument(
        "--output", type=pathlib.Path, help="Folder where to save the FAISS index.", required=True
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
    final_output = args.output / str(uuid.uuid1())

    final_output.mkdir(parents=True, exist_ok=True)

    final_output = final_output / "index.faiss"

    start_time = timeit.default_timer()

    convert_to_faiss(args.input, final_output)

    duration = datetime.timedelta(seconds=timeit.default_timer() - start_time)
    duration_seconds = datetime.timedelta(seconds=duration.seconds)
    hours, minutes, seconds = str(duration_seconds).split(":")

    logger.info(f"Time taken: {duration.days} days {hours} hours {minutes} minutes {seconds} seconds {duration.microseconds} microseconds sec")
    logger.info(f"The FAISS index is in {final_output}")


if __name__ == "__main__":
    main()