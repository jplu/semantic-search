import sys
import os
import json
import timeit
import distutils.util
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import multiprocessing as mp

from pathlib import Path

from elasticsearch import Elasticsearch
from elasticsearch.helpers import streaming_bulk

es_hosts = "localhost"
es_login = os.getenv('ES_LOGIN')
es_password = os.getenv('ES_PASSWORD')
es_port = os.getenv('ES_PORT')
es_is_secure = os.getenv('ES_IS_SECURE')
index_name = 'en_wikipedia'
all_files = list(Path("formatted-wikipedia-articles").rglob(f"*.json"))


def data_generator():
    for json_file in all_files:
        with open(json_file, encoding="utf-8") as f:
            article = json.load(f)

            for paragraph in article["paragraphs"]:
                source = paragraph
                source["title"] = article["title"]
                source["id"] = article["id"]
                source["url"] = article["url"]
                doc = {
                    '_op_type': 'create',
                    '_index': "en_wikipedia",
                    "_id": paragraph["pid"],
                    "_source": source
                }
            
                yield(doc)


def main():
    if bool(distutils.util.strtobool(es_is_secure)):
        es_client = Elasticsearch(
            [es_hosts],
            http_auth=(es_login, es_password),
            scheme="https",
            port=es_port,
            timeout=300,
            retry_on_timeout=True,
            max_retries=10,
            maxsize=25,
        )
    else:
        import ssl
        from elasticsearch.connection import create_ssl_context

        ssl_context = create_ssl_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        es_client = Elasticsearch(
            [es_hosts],
            http_auth=(es_login, es_password),
            scheme="https",
            port=es_port,
            timeout=300,
            retry_on_timeout=True,
            max_retries=10,
            maxsize=25,
            ssl_context=ssl_context,
        )

    print("Creating an index...")
    
    es_client.indices.create(index=index_name, ignore=400)

    print("Indexing documents...")

    good, missing, errors = 0, 0, 0
    bulk_args = {
        "client": es_client,
        "index": index_name,
        "max_retries": 1000,
        "chunk_size": 1000,
        "actions": data_generator(),
    }
    start_time = timeit.default_timer()

    for ok, result in streaming_bulk(raise_on_exception=False, raise_on_error=False, **bulk_args):
        action, result = result.popitem()
        status_code = result.get('status', 500)

        if ok:
            good += 1
        elif status_code == 'TIMEOUT':
            errors += 1
            print(result["error"])
        elif status_code == 404:
            missing += 1
            print(result["error"])
        elif not isinstance(status_code, int):
            errors += 1
            print(result["error"])
        elif status_code >= 400 and status_code < 500:
            errors += 1
            print(result["error"])

    end_time = timeit.default_timer() - start_time

    print(f'Completed import with {good} success {missing} missing and {errors} errors')
    print(f'Done in {end_time} sec')

if __name__ == "__main__":
    main()
