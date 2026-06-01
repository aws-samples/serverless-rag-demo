#!/usr/bin/env python3
"""Create the AOSS vector index after collection deployment.

Usage: python scripts/create_aoss_index.py <collection_name> <index_name> [vector_dims]
"""

import json
import sys
import time

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import urllib3


def get_collection_endpoint(collection_name: str, region: str) -> str:
    client = boto3.client("opensearchserverless", region_name=region)
    resp = client.batch_get_collection(names=[collection_name])
    details = resp.get("collectionDetails", [])
    if not details:
        raise RuntimeError(f"Collection '{collection_name}' not found")
    return details[0]["collectionEndpoint"]


def signed_request(method, url, region, body=None):
    session = boto3.Session()
    creds = session.get_credentials().get_frozen_credentials()

    headers = {"Content-Type": "application/json"}
    request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(creds, "aoss", region).add_auth(request)

    http = urllib3.PoolManager()
    response = http.request(
        method,
        url,
        body=body.encode("utf-8") if body else None,
        headers=dict(request.headers),
    )
    return response.status, response.data.decode("utf-8")


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/create_aoss_index.py <collection_name> <index_name> [vector_dims]")
        sys.exit(1)

    collection_name = sys.argv[1]
    index_name = sys.argv[2]
    vector_dims = int(sys.argv[3]) if len(sys.argv) > 3 else 1024

    region = boto3.Session().region_name or "us-east-1"

    print(f"Looking up collection '{collection_name}' in {region}...")
    endpoint = get_collection_endpoint(collection_name, region)
    print(f"Endpoint: {endpoint}")

    index_url = f"{endpoint}/{index_name}"

    # Check if index exists
    status, _ = signed_request("HEAD", index_url, region)
    if status == 200:
        print(f"Index '{index_name}' already exists. Done.")
        return

    # Create index with FAISS engine (required by Bedrock Knowledge Base)
    mapping = {
        "settings": {"index": {"knn": True, "knn.algo_param.ef_search": 512}},
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "knn_vector",
                    "dimension": vector_dims,
                    "method": {"name": "hnsw", "engine": "faiss", "parameters": {"m": 16, "ef_construction": 512}},
                },
                "text": {"type": "text"},
                "metadata": {"type": "text"},
                "AMAZON_BEDROCK_TEXT_CHUNK": {"type": "text"},
                "AMAZON_BEDROCK_METADATA": {"type": "text"},
            }
        },
    }

    # Retry with backoff (data access policy propagation)
    for attempt in range(10):
        status, resp = signed_request("PUT", index_url, region, json.dumps(mapping))
        if status in (200, 201):
            print(f"Created index '{index_name}' successfully.")
            return
        if status == 403:
            wait = 10 * (attempt + 1)
            print(f"  Got 403 (attempt {attempt+1}/10), retrying in {wait}s...")
            time.sleep(wait)
            continue
        raise RuntimeError(f"Failed to create index: {status} {resp}")

    raise RuntimeError("Failed after 10 attempts — check data access policy principals")


if __name__ == "__main__":
    main()
