import os
import math
import faiss
from tqdm import tqdm
import numpy as np

names = os.listdir("encoded-wikipedia-articles")
index_paths = [os.path.join("encoded-wikipedia-articles", name) for name in names if name.endswith(".faiss")]

index = faiss.read_index(index_paths[0])

for index_path in tqdm(index_paths[1:], desc="loading sub-indexes"):
    tmp_index = faiss.read_index(index_path)
    index.merge_from(tmp_index, 0)

faiss.write_index(index, "merged.faiss")
