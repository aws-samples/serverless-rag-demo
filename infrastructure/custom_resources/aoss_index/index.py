"""Lambda handler to create an OpenSearch Serverless index.

Invoked by deploy.sh via `aws lambda invoke` after the AOSS stack deploys.
The Lambda role is pre-authorized in the AOSS data access policy.
"""

import json
import os
import re
import time
import hashlib
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Both of these arrive in the invocation payload and are concatenated into a URL
# that is then fetched with the Lambda's own SigV4 credentials, so they are
# validated rather than trusted: an arbitrary endpoint would make this a signed
# request to wherever the caller chose.
AOSS_ENDPOINT = re.compile(
    r"^https://[a-z0-9-]+\.[a-z0-9-]+\.aoss\.amazonaws\.com$")
INDEX_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,254}$")


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

    endpoint = collection_endpoint.rstrip("/")
    if not AOSS_ENDPOINT.match(endpoint):
        return {"status": "ERROR", "message": "CollectionEndpoint is not an AOSS endpoint"}
    if not isinstance(index_name, str) or not INDEX_NAME.match(index_name):
        return {"status": "ERROR", "message": "IndexName is not a valid index name"}
    if not 1 <= vector_dims <= 16000:
        return {"status": "ERROR", "message": "VectorDimensions is out of range"}

    index_url = f"{endpoint}/{index_name}"
    # Belt and braces: the two patterns above should make this unreachable, but
    # the request is signed, so confirm the host one more time before it is sent.
    if urlparse(index_url).hostname != urlparse(endpoint).hostname:
        return {"status": "ERROR", "message": "Refusing to build a cross-host URL"}

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
