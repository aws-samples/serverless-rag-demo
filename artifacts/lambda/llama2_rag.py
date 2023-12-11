from os import getenv
from sentence_transformers import SentenceTransformer
from opensearchpy import OpenSearch, RequestsHttpConnection, exceptions
from requests_aws4auth import AWS4Auth
import os
import json
from decimal import Decimal
import logging
import boto3

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
# http endpoint for your cluster (opensearch required for vector index usage)
# Self managed or cluster based OPENSEARCH
endpoint = getenv("OPENSEARCH_ENDPOINT", "https://admin:P@@search-opsearch-public-24k5tlpsu5whuqmengkfpeypqu.us-east-1.es.amazonaws.com:443")
sagemaker_endpoint=getenv("SAGEMAKER_ENDPOINT", "llama2-7b-endpoint")
SAMPLE_DATA_DIR=getenv("SAMPLE_DATA_DIR", "/var/task")
path = os.environ['MODEL_PATH']
LLM_MODEL_ID = getenv("LLM_MODEL_ID", "llama-2-7b")
tokens = int(getenv("MAX_TOKENS", "1000"))
temperature = float(getenv("TEMPERATURE", "0.9"))
top_p = float(getenv("TOP_P", "0.6"))
top_k = int(getenv("TOP_K", "10"))

ANSWER_BASED_ON_PROVIDED_CONTEXT = getenv("ANSWER_BASED_ON_PROVIDED_CONTEXT",".Answer strictly based on above provided context only")
embed_model_st = SentenceTransformer(path)

client = boto3.client('opensearchserverless')
credentials = boto3.Session().get_credentials()
service = 'aoss'
region = getenv("REGION", "us-east-1")
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key,
                   region, service, session_token=credentials.token)
ops_client = client = OpenSearch(
        hosts=[{'host': endpoint, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )
INDEX_NAME = getenv("INDEX_NAME", "sample-embeddings-store-dev")
DEFAULT_PROMPT = """You are a helpful, respectful and honest assistant.
                    Always answer as helpfully as possible, while being safe.
                    Please ensure that your responses are socially unbiased and positive in nature.
                    If a question does not make any sense, or is not factually coherent,
                    explain why instead of answering something not correct.
                    If you don't know the answer to a question,
                    please don't share false information. """
DEFAULT_SYSTEM_PROMPT = DEFAULT_PROMPT

FALCON_PROMPT = """ Answer the question truthfully using the provided text, and if the answer is not contained within the text below, say "I don't know """
DEFAULT_FALCON_PROMPT = FALCON_PROMPT

BEHAVIOUR = getenv("DEFAULT_SYSTEM_PROMPT", '')
BEHAVIOUR_OVERRIDE = getenv("BEHAVIOUR_OVERRIDE", "False")

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
                        "dimension": 384,
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
    embeddings = embed_model_st.encode(text_val)
    doc = {
           'embedding' : embeddings,
           'text': text_val
        }
    
    try:
        create_index()
        # Index the document
        ops_client.index(index=INDEX_NAME, body=doc)
    except Exception as e:
        print(e.info["error"]["reason"])
        return failure_response(f'error indexing documents {e.info["error"]["reason"]}')
    return success_response('Documents indexed successfully')

def query_falcon(encoded_json):
    client = boto3.client("runtime.sagemaker")
    print(f' Invoke Falcon with Payload -> {encoded_json}')
    response = client.invoke_endpoint(
        EndpointName=sagemaker_endpoint, ContentType="application/json", Body=encoded_json
    )
    model_predictions = json.loads(response["Body"].read().decode("utf8"))
    print(f'Falcon response -> {model_predictions}')
    txt = model_predictions[0]["generated_text"]
    return txt
    
def query_data(event):
    query = None
    behaviour = None
    global DEFAULT_SYSTEM_PROMPT
    if event['queryStringParameters'] and 'query' in event['queryStringParameters']:
        query = event['queryStringParameters']['query']
    if event['queryStringParameters'] and 'behaviour' in event['queryStringParameters']:
        behaviour = event['queryStringParameters']['behaviour']
        if behaviour == 'pirate':
            if 'False' in BEHAVIOUR_OVERRIDE:
                DEFAULT_SYSTEM_PROMPT='You are a daring and brutish Pirate. Always answer as a Pirate do not share the context when answering.' + BEHAVIOUR
                DEFAULT_FALCON_PROMPT="Answer the question as a daring and brutish Pirate, and if the answer is not contained within the context below, politely reply 'I dont know' " + BEHAVIOUR
            else:
                DEFAULT_SYSTEM_PROMPT = BEHAVIOUR
                DEFAULT_FALCON_PROMPT = BEHAVIOUR
        elif behaviour == 'jarvis':
            if 'False' in BEHAVIOUR_OVERRIDE:
                DEFAULT_SYSTEM_PROMPT='You are a sophisticated artificial intelligence assistant. Reply as an AI assistant' + BEHAVIOUR
                DEFAULT_FALCON_PROMPT="Answer the question as a sophisticated artificial intelligence assistant, if the answer is not contained within the context below, politely decline to comment " + BEHAVIOUR
            else:
                DEFAULT_SYSTEM_PROMPT = BEHAVIOUR
                DEFAULT_FALCON_PROMPT = BEHAVIOUR
        else:
            if 'False' in BEHAVIOUR_OVERRIDE:
                DEFAULT_SYSTEM_PROMPT = DEFAULT_PROMPT + BEHAVIOUR
                DEFAULT_FALCON_PROMPT = FALCON_PROMPT + BEHAVIOUR
            else:
                DEFAULT_SYSTEM_PROMPT = BEHAVIOUR
                DEFAULT_FALCON_PROMPT = BEHAVIOUR
    
    # query = input("What are you looking for? ") 
    embedded_search = embed_model_st.encode(query)
    vector_query = {
        "size": 4,
        "query": {"knn": {"embedding": {"vector": embedded_search, "k": 2}}},
        "_source": False,
        "fields": ["text", "doc_type"]
    }
    # Modify the Query here to answer only based on provided context
    query = query + ANSWER_BASED_ON_PROVIDED_CONTEXT
    content=None
    print('Search for context from Opensearch serverless vector collections')
    try:
        response = ops_client.search(body=vector_query, index=INDEX_NAME)
        print(response["hits"]["hits"])
        for data in response["hits"]["hits"]:
            if content is None:
                content = data['fields']['text'][0]
            else: 
                content = content + ' ' + data['fields']['text'][0]
        print(f'content -> {content}')
    except Exception as e:
        print('Vector Index does not exist. Please index some documents')
    
    if content is None:
        print('Set a default context')
        content=" "
    
    try:
        if  'llama' in LLM_MODEL_ID:
            payload = {
                "inputs": f"<|prompter|>{'Behaviour: ' + DEFAULT_SYSTEM_PROMPT}<|endoftext|><|prompter|>{'context: '+ content}<|endoftext|><|prompter|>{query + ' ?'}<|endoftext|><|assistant|>",  
                "parameters": {"max_new_tokens": tokens, "top_p": top_p, "temperature": temperature, "return_full_text": False, "repetition_penalty": 1.03, "stop": ["<|endoftext|>"]}
            }
            response_list = []
            result = query_endpoint(payload)[0]
            resp = {
                result['generation']['role'].capitalize(): result['generation']['content']
            }
            response_list.append(resp)
            print(f'Response from Llama2 llm : {response_list}')
            return success_response(response_list)
        elif 'falcon' in LLM_MODEL_ID:
            query = query
            template = f"<|prompter|>{'Behaviour: ' + DEFAULT_FALCON_PROMPT}<|endoftext|><|prompter|>{'context: '+ content}<|endoftext|><|prompter|>{query + ' ?'}<|endoftext|><|assistant|>",  
            params = {"max_new_tokens": tokens, "top_p": top_p, "temperature": temperature, "top_k": top_k, "num_return_sequences": 1, "repetition_penalty": 1.03, "stop": ["<|endoftext|>"]}
            response_list = []
            result = query_falcon(json.dumps({"inputs": template , "parameters": params}).encode("utf-8"))
            resp = {
                "Assistant" : result
            }
            response_list.append(resp)
            return success_response(response_list)
    except Exception as e:
        print(f'Exception {e}')
        return failure_response(f'Exception occured when querying LLM: {e}')
    

def query_endpoint(payload):
    client = boto3.client("sagemaker-runtime")
    print(f' Invoke Llama2 with Payload -> {payload}')
            
    response = client.invoke_endpoint(
        EndpointName=sagemaker_endpoint,
        ContentType="application/json",
        Body=json.dumps(payload),
        CustomAttributes="accept_eula=true",
    )
    response = response["Body"].read().decode("utf8")
    print(f'Llama2 Output {response}')
    response = json.loads(response)
    return response
    

def delete_index(event):
    try:
        res = ops_client.indices.delete(index=INDEX_NAME)
        print(res)
    except Exception as e:
        return failure_response(f'error deleting index. {e.info["error"]["reason"]}')
    return success_response('Index deleted successfully')

def handler(event, context):
    LOG.info("---  Amazon Opensearch Serverless vector db example with Llama2 / Falcon models ---")

    api_map = {
        'POST/rag/index-sample-data': lambda x: index_sample_data(x),
        'POST/rag/index-documents': lambda x: index_documents(x),
        'DELETE/rag/index-documents': lambda x: delete_index(x),
        'GET/rag/query': lambda x: query_data(x)
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