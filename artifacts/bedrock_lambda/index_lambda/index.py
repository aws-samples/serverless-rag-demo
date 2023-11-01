from os import getenv
from opensearchpy import OpenSearch, RequestsHttpConnection, exceptions
from requests_aws4auth import AWS4Auth
import os
import json
from decimal import Decimal
import logging
import boto3
from langchain.text_splitter import RecursiveCharacterTextSplitter
from concurrent.futures import ThreadPoolExecutor, as_completed

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
# http endpoint for your cluster (opensearch required for vector index usage)
# Self managed or cluster based OPENSEARCH
endpoint = getenv("OPENSEARCH_ENDPOINT", "https://admin:P@@search-opsearch-public-24k5tlpsu5whuqmengkfpeypqu.us-east-1.es.amazonaws.com:443")
SAMPLE_DATA_DIR=getenv("SAMPLE_DATA_DIR", "sample_data")
INDEX_NAME = getenv("INDEX_NAME", "sample-embeddings-store-dev")
credentials = boto3.Session().get_credentials()

service = 'aoss'
region = getenv("REGION", "us-east-1")
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key,
                   region, service, session_token=credentials.token)

bedrock_client = boto3.client('bedrock-runtime')

ops_client = OpenSearch(
        hosts=[{'host': endpoint, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )


def index_sample_data(event):
    print(f'In index_sample_data {event}')
    payload = json.loads(event['body'])
    type = payload['type']
    create_index()
    for i in range(1, 5):
        try:    
            file_name=f"{SAMPLE_DATA_DIR}/{type}_doc_{i}.txt"
            f = open(file_name, "r")
            data = f.read()
            if data is not None:
                index_documents({"body": json.dumps({"text": data}) })
        except Exception as e:
            print(f'Error indexing sample data {file_name}, exception={e}')
            return failure_response('Sample data could not be indexed')
    return success_response('Sample Documents Indexed Successfully')
    

def create_index() :
    print(f'In create index')
    if not ops_client.indices.exists(index=INDEX_NAME):
    # Create indicies
        settings = {
            "settings": {
                "index": {
                    "knn": True,
                }
            },
            "mappings": {
                "properties": {
                    "id": {"type": "integer"},
                    "text": {"type": "text"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 1536,
                    },
                }
            },
        }
        res = ops_client.indices.create(index=INDEX_NAME, body=settings, ignore=[400])
        print(res)

def index_documents(event):
    print(f'In index documents {event}')
    payload = json.loads(event['body'])
    text_val = payload['text']

    text_splitter = RecursiveCharacterTextSplitter(
    # Set a really small chunk size, just to show.
    chunk_size = 1000,
    chunk_overlap  = 100)

    texts = text_splitter.create_documents([text_val])

    if texts is not None and len(texts) > 0:
        create_index()
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_generate_embeddings_and_index,chunk_text) for chunk_text in texts]
            for future in as_completed(futures):
                result = future.result()
                if result['statusCode'] != "200":
                    return failure_response(result['errorMessage'])
                else:
                    print(result)
                    
    return success_response('Documents indexed successfully')


def _generate_embeddings_and_index(chunk_text):
        body = json.dumps({"inputText": chunk_text.page_content})
        model_id = 'amazon.titan-embed-text-v1'
        try:
            response = bedrock_client.invoke_model(
                    body = body,
                    modelId = model_id,
                    accept = 'application/json',
                    contentType = 'application/json'
            )
            result = json.loads(response['body'].read())
            embeddings = result.get('embedding')
        except Exception as e:
            return failure_response(f'Do you have Titan-Embed Model Access {e.info["error"]["reason"]}')
        doc = {
            'embedding' : embeddings,
            'text': chunk_text.page_content
        }
        try:
            # Index the document
            ops_client.index(index=INDEX_NAME, body=doc)
            return success_response('Documents Indexed Successfully')
        except Exception as e:
            print(e.info["error"]["reason"])
            return failure_response(f'error indexing documents {e.info["error"]["reason"]}')
        


def delete_index(event):
    try:
        res = ops_client.indices.delete(index=INDEX_NAME)
        print(res)
    except Exception as e:
        return failure_response(f'error deleting index. {e.info["error"]["reason"]}')
    return success_response('Index deleted successfully')

def connect_tracker(event):
    return success_response('Successfully connection')


def handler(event, context):
    LOG.info("---  Amazon Opensearch Serverless vector db example with Amazon Bedrock Models ---")

    api_map = {
        'POST/rag/index-sample-data': lambda x: index_sample_data(x),
        'POST/rag/index-documents': lambda x: index_documents(x),
        'DELETE/rag/index-documents': lambda x: delete_index(x),
        'GET/rag/connect-tracker': lambda x: connect_tracker(x)
    }
    
    http_method = event['httpMethod'] if 'httpMethod' in event else ''
    api_path = http_method + event['resource']
    try:
        if api_path in api_map:
            LOG.debug(f"method=handler , api_path={api_path}")
            return respond(None, api_map[api_path](event))
        else:
            LOG.info(f"error=api_not_found , api={api_path}")
            return respond(failure_response('api_not_supported'), None)
    except Exception:
        LOG.exception(f"error=error_processing_api, api={api_path}")
        return respond(failure_response('system_exception'), None)


def failure_response(error_message):
    return {"success": False, "errorMessage": error_message, "statusCode": "400"}
   
def success_response(result):
    return {"success": True, "result": result, "statusCode": "200"}

# Hack
class CustomJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            if float(obj).is_integer():
                return int(float(obj))
            else:
                return float(obj)
        return super(CustomJsonEncoder, self).default(obj)

# JSON REST output builder method
def respond(err, res=None):
    return {
        'statusCode': '400' if err else res['statusCode'],
        'body': json.dumps(err) if err else json.dumps(res, cls=CustomJsonEncoder),
        'headers': {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Credentials": "*"
        },
    }