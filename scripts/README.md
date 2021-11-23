# Create a FAISS index

The creation of an index is divided in 5 sub-tasks:

* Create the optimized and quantized ONNX model you want to use to encode your data.
* Download the dataset you want to create an index from.
* Turn this dataset into our intermediate format.
* Encode these formatted dataset into vectors.
* Index these vectors with FAISS.

Before to start be sure to have all the required python packages installed with:
```
pip install -r requirements.txt
```

## Create the ONNX model

In order to create the quantized and optimized ONNX version of a Tensorflow or Pytorch model you can use the `create_onnx_model.py` script. For example with an encoder model:

```
python create_onnx_model.py --model <MODEL_NAME> --encoder --output <OUTPUT_PATH>
```

You have to replace:
* `<MODEL_NAME>` with the HuggingFace transformers model name. The model can either be an encoder (embedding output) or a sentence classifier and must be BERT based.
* `<OUTPUT_PATH>` with the location where you want the ONNX model to be saved.

The scripts proposes other options, you can check the usage in order to know which ones:

```
usage: create_onnx_model.py [OPTION] ...

Create, optimize and quantize Bert based model in ONNX.

optional arguments:
  -h, --help       show this help message and exit
  --version        show program's version number and exit
  --encoder        If the model is for encoding or not. Must be BERT based.
  --rerank         If the model is for encoding or not. Must be BERT based.

required arguments:
  --model MODEL    The HuggingFace model to use for reranking or encoding. Must be BERT based.
  --output OUTPUT  Folder where to save the ONNX model.
```

If you want you can test the performance of your newly created ONNX model with:

```
python -m onnxruntime.transformers.bert_perf_test --model <MODEL_LOCATION> -b 1 -s 128 -t 100 --input_ids_name input_ids --input_mask_name attention_mask --segment_ids token_type_ids --opt_level 2
```

Replace `<MODEL_LOCATION>` with the location of the ONNX model.

## Process the dataset

Here as example we will take the English Wikipedia, but the logic can be applied to any textual dataset. The first step is to download the XML Wikipedia dump with:

```
wget https://dumps.wikimedia.org/enwiki/20211101/enwiki-20211101-pages-articles.xml.bz2
```

Once done, you can turn and split this dump into multiple JSON files with the tool [Ruby Slippers](https://github.com/alvations/rubyslippers). Check its documentation to know how to do that.

Now that we have the Wikipedia pages into JSON we can turn these JSON files into the intermediate format with the command line:

```
python indexing/wikipedia/format_wikipedia_pages.py --input <INPUT_JSON_FOLDER> --output <OUTPUT_FOLDER> --workers <NUMBER_OF_WORKERS>
```

You have to replace:
* `<INPUT_JSON_FOLDER>` with the location of the JSON files created with Ruby Slippers.
* `<OUTPUT_FOLDER>` with the location where you want the JSON formatted Wikipedia pages.
* `<NUMBER_OF_WORKERS>` the number of workers to run in parallel.

The scripts proposes other options, you can check the usage in order to know which ones:

```
usage: format_wikipedia_pages.py [OPTION] ...

Format and split Wikipedia articles into paragraphs.

optional arguments:
  -h, --help            show this help message and exit
  --version         show program's version number and exit
  --max_len_paragraph MAX_LEN_PARAGRAPH
                        Max number of character of a paragraph. Those with a higher number will be ignored. (default: 2500)
  --min_len_paragraph MIN_LEN_PARAGRAPH
                        Min number of character of a paragraph. Those with a lower number will be ignored. (default: 125)
  --local               Run the process locally.
  --remote              Run the process remotely on a cluster.

required arguments:
  --input INPUT         Folder containing the JSON file(s) to encode.
  --output OUTPUT       Folder where to save the vectors in Parquet format.
  --workers WORKERS     Number of encoding worker to run in parallel. If run locally this number should not be higher than the number of available threads. If run remotely this number should not be higher than the number of available nodes in the cluster.
```

The script can also de deployed into a Ray cluster, see the `config.yaml` to have an example of a cluster on GCP. More details on how to run and deploy this kind of workflow are available on the [official Ray website](https://docs.ray.io/en/master/cluster/index.html).

Finally, we can move to the creation of the vectors for each piece of text from every JSON files newly created. To do that, one has to run the following command line:

```
python indexing/encode_documents.py --input <INPUT_JSON_FOLDER> --model <MODEL_PATH> --workers <NUMBER_OF_WORKERS> --tokenizer <TOKENIZER_NAME> --output <OUTPUT_FOLDER> --local
```

You have to replace:
* `<INPUT_JSON_FOLDER>` with the location of the formatted JSON files (created with the `format_wikipedia_pages.py` script for Wikipedia or any other script that creates the formatted JSON files).
* `<MODEL_PATH>` with the location of the ONNX model you want to use to encode the text into vectors.
* `<NUMBER_OF_WORKERS>` the number of workers to run in parallel.
* `<TOKENIZER_NAME>` the tokenizer to use for tokenizing the text. This has to be a HuggingFace tokenizer name, more precisely the one that is shipped with the model you have turned into ONNX.
* `<OUTPUT_FOLDER>` with the location where you want to save the Parquet files containing the vectors.

The scripts proposes other options, you can check the usage in order to know which ones:

```
usage: encode_documents.py [OPTION] ...

Vectorizing textual content with an encoding model.

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --local               Run the process locally.
  --remote              Run the process remotely on a cluster.

required arguments:
  --input INPUT         Folder containing the JSON file(s) to encode.
  --model MODEL         The ONNX model to use for encoding.
  --workers WORKERS     Number of encoding worker to run in parallel. If run locally this number should not be higher than the number of available threads. If run remotely this number should not be higher than the number of available nodes in the cluster.
  --tokenizer TOKENIZER
                        The HuggingFace tokenizer to use.
  --output OUTPUT       Folder where to save the vectors in Parquet format.
```

The script can also de deployed into a Ray cluster, see the `config.yaml` to have an example of a cluster on GCP. More details on how to run and deploy this kind of workflow are available on the [official Ray website](https://docs.ray.io/en/master/cluster/index.html).

## Build the FAISS index

All the documents are now properly encoded with the model. The final step is now to build the FAISS index with the command line:

```
python indexing/create_faiss_index.py -i <INPUT_PARQUET_FOLDER> -o <OUTPUT_FOLDER>
```

You have to replace:
* `<INPUT_PARQUET_FOLDER>` with the location of the Parquet files.
* `<OUTPUT_FOLDER>` with the location where you want to save the FAISS index.

There are no other options to know for this script.

# Import the textual content into Elasticsearch

The tool we use to retrieve the textual content that corresponds to a vector is Elasticsearch but you can use any other retrieval system. Then, in order to load all the textual content in Elasticsearch you can run the following command line:

```
python indexing/load_documents_elasticsearch.py --input <INPUT_JSON_FOLDER> --workers <NUMBER_OF_WORKERS> --login <ES_LOGIN> --password <ES_PASSWORD> --hosts <ES_HOSTS> --local --index <ES_INDEX_NAME>
```

You have to replace:
* `<INPUT_JSON_FOLDER>` with the location of the formatted JSON files (created with the `format_wikipedia_pages.py` script for Wikipedia or any other script that creates the formatted JSON files).
* `<NUMBER_OF_WORKERS>` the number of workers to run in parallel.
* `<ES_LOGIN>` the Elasticsearch connection login if any.
* `<ES_PASSWORD>` the Elasticsearch connection password if any.
* `<ES_HOSTS>` the Elasticsearch hosts, separated by a comma if many.
* `<ES_INDEX_NAME>` the index name where to load the JSON files.

The scripts proposes other options, you can check the usage in order to know which ones:

```
usage: load_documents_elasticsearch.py [OPTION] ...

Load the documents in Elasticsearch.

optional arguments:
  -h, --help           show this help message and exit
  -v, --version        show program's version number and exit
  --update             Update the index instead of delete (if already exists) and create.
  --scheme SCHEME      Update the index instead of delete (if already exists) and create.
  --login LOGIN        Elasticsearch login. Superseded by the ES_LOGIN env variable if it exists.
  --password PASSWORD  Elasticsearch password. Superseded by the ES_PASSWORD env variable if it exists.
  --port PORT          Elasticsearch port.
  --is_secure          If the connection with Elasticsearch goes through SSL.
  -l, --local          Run the process locally.
  -r, --remote         Run the process remotely on a cluster.

required arguments:
  --input INPUT        Folder containing the formatted JSON file(s) to load.
  --hosts [HOSTS]      Elasticsearch hosts. Multiple hosts must be comma separated.
  --index INDEX        Elasticsearch index name.
  --workers WORKERS    Number of encoding worker to run in parallel. If run locally this number should not be higher than the number of available threads. If run remotely this number should not be higher than the number of available nodes in the cluster.
```

The script can also de deployed into a Ray cluster, see the `config.yaml` to have an example of a cluster on GCP. More details on how to run and deploy this kind of workflow are available on the [official Ray website](https://docs.ray.io/en/master/cluster/index.html).