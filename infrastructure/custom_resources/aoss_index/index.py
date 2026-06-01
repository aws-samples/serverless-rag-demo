"""Lambda handler to create an OpenSearch Serverless index.

Invoked by deploy.sh via `aws lambda invoke` after the AOSS stack deploys.
The Lambda role is pre-authorized in the AOSS data access policy.
"""

import json
import os
import time
import hashlib
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


def signed_request(method, url, region, body=None):
    """Make a SigV4-signed request to AOSS using urllib (stdlib)."""
    session = boto3.Session()
    creds = session.get_credentials().get_frozen_credentials()

    body_bytes = body.encode("utf-8") if body else b""
    headers = {
        "Content-Type": "application/json",
        "x-amz-content-sha256": hashlib.sha256(body_bytes).hexdigest(),
    }

    request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(creds, "aoss", region).add_auth(request)

    try:
        req = Request(
            url,
            data=body_bytes if method in ("PUT", "POST") else None,
            headers=dict(request.headers),
            method=method,
        )
        response = urlopen(req)
        return response.status, response.read().decode("utf-8")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8")


def on_event(event, context):
    """Handle direct invocation."""
    region = os.environ.get("AWS_REGION", "us-east-1")
    collection_endpoint = event.get("CollectionEndpoint") or os.environ.get("COLLECTION_ENDPOINT")
    index_name = event.get("IndexName", "srd-embeddings-test")
    vector_dims = int(event.get("VectorDimensions", "1024"))

    if not collection_endpoint:
        return {"status": "ERROR", "message": "No CollectionEndpoint provided"}

    index_url = f"{collection_endpoint}/{index_name}"

    # Check if index already exists
    status, resp = signed_request("HEAD", index_url, region)
    print(f"HEAD {index_url}: {status}")
    if status == 200:
        return {"status": "EXISTS", "message": f"Index '{index_name}' already exists"}

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
    max_retries = 12
    for attempt in range(max_retries):
        status, resp = signed_request("PUT", index_url, region, json.dumps(mapping))
        print(f"PUT attempt {attempt+1}: status={status} resp={resp[:200]}")

        if status in (200, 201):
            return {"status": "CREATED", "message": f"Index '{index_name}' created", "response": resp}

        if status == 403 and attempt < max_retries - 1:
            wait_time = 15 * (attempt + 1)
            print(f"Got 403 on attempt {attempt + 1}/{max_retries}, retrying in {wait_time}s...")
            time.sleep(wait_time)
            continue

        return {"status": "ERROR", "message": f"Failed: {status} {resp}"}

    return {"status": "ERROR", "message": "Timed out after all retries"}
