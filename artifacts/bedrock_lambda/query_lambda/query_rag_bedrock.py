import boto3
from os import getenv
from opensearchpy import OpenSearch, RequestsHttpConnection, exceptions
from requests_aws4auth import AWS4Auth
import os
import json
from decimal import Decimal
import logging

bedrock_client = boto3.client('bedrock-runtime')
embed_model_id = 'amazon.titan-embed-text-v1'
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
endpoint = getenv("OPENSEARCH_ENDPOINT",
                  "https://admin:P@@search-opsearch-public-24k5tlpsu5whuqmengkfpeypqu.us-east-1.es.amazonaws.com:443")
SAMPLE_DATA_DIR = getenv("SAMPLE_DATA_DIR", "/var/task")
INDEX_NAME = getenv("INDEX_NAME", "sample-embeddings-store-dev")
wss_url = getenv("WSS_URL", "WEBSOCKET_URL_MISSING")
websocket_client = boto3.client('apigatewaymanagementapi', endpoint_url=wss_url)

credentials = boto3.Session().get_credentials()
service = 'aoss'
region = getenv("REGION", "us-east-1")
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key,
                   region, service, session_token=credentials.token)

DEFAULT_PROMPT = """You are a helpful, respectful and honest assistant.
                    Always answer as helpfully as possible, while being safe.
                    Please ensure that your responses are socially unbiased and positive in nature.
                    If a question does not make any sense, or is not factually coherent,
                    explain why instead of answering something not correct.
                    If you don't know the answer to a question,
                    please don't share false information. """

ops_client = client = OpenSearch(
    hosts=[{'host': endpoint, 'port': 443}],
    http_auth=awsauth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
    timeout=300
)

bedrock_client = boto3.client('bedrock-runtime')


def query_data(query, behaviour, model_id, connect_id):
    global DEFAULT_SYSTEM_PROMPT
    global embed_model_id
    global bedrock_client
    prompt = DEFAULT_PROMPT
    if behaviour in ['english', 'hindi', 'thai', 'spanish', 'bengali']:
        prompt = f'{DEFAULT_PROMPT}. You will always reply in {behaviour} language only.'
    elif behaviour == 'sentiment':
        prompt = DEFAULT_PROMPT + '. You will identify the sentiment of the below context.'
    elif behaviour == 'legal':
        prompt = ''' You are an Advocate, you shall refuse to represent any client who insists on using unfair or improper means. An advocate shall excise his own judgment in such matters. You shall not blindly follow the instructions of the client. He shall be dignified in use of his language in correspondence and during arguments in court. He shall not scandalously damage the reputation of the parties on false grounds during pleadings. You shall not use unparliamentary language during arguments in the court.
            You should appear in court at all times only in the dress prescribed under the Bar Council of India Rules and his appearance should always be presentable.
            You should not enter appearance, act, plead or practice in any way before a judicial authority if the sole or any member of the bench is related to the advocate as father, grandfather, son, grandson, uncle, brother, nephew, first cousin, husband, wife, mother, daughter, sister, aunt, niece, father-in-law, mother-in-law, son-in-law, brother-in-law daughter-in-law or sister-in-law.
            During the presentation of your case and also while acting before a court, you should act in a dignified manner. You should at all times conduct himself with self-respect. However, whenever there is proper ground for serious complaint against a judicial officer, You have a right and duty to submit your grievance to proper authorities.
            '''
    elif behaviour == 'pii':
        prompt = DEFAULT_PROMPT + '. You will identify PII data from the below given context'
    else:
        prompt = DEFAULT_PROMPT
    
    context = None
    if query is not None and len(query.split()) > 0:
        try:
            # Get the query embedding from amazon-titan-embed model
            response = bedrock_client.invoke_model(
                body=json.dumps({"inputText": query}),
                modelId=embed_model_id,
                accept='application/json',
                contentType='application/json'
            )
            result = json.loads(response['body'].read())
            embedded_search = result.get('embedding')

            vector_query = {
                "size": 10,
                "query": {"knn": {"embedding": {"vector": embedded_search, "k": 2}}},
                "_source": False,
                "fields": ["text", "doc_type"]
            }
            
            print('Search for context from Opensearch serverless vector collections')
            try:
                response = ops_client.search(body=vector_query, index=INDEX_NAME)
                #print(response["hits"]["hits"])
                for data in response["hits"]["hits"]:
                    if context is None:
                        context = data['fields']['text'][0]
                    else:
                        context = context + ' ' + data['fields']['text'][0]
                query = query + '. Answer based on the above context only'
                #print(f'context -> {context}')
            except Exception as e:
                print('Vector Index does not exist. Please index some documents')

        except Exception as e:
            return failure_response(connect_id, f'{e.info["error"]["reason"]}')

    else:
        query = ''
    
    if context is None:
        print('Set a default context')
        context = " "

    try:
        response = None
        print(f'LLM Model ID -> {model_id}')
        if model_id in ['amazon.titan-text-lite-v1',
                            'amazon.titan-text-express-v1',
                            'amazon.titan-text-agile-v1',
                            'anthropic.claude-v2',
                            'anthropic.claude-v1',
                            'anthropic.claude-instant-v1',
                            'cohere.command-text-v14',
                            'amazon.titan-text-express-v1',
                            'ai21.j2-ultra-v1',
                            'ai21.j2-mid-v1']:
            context = f'\n\ncontext: {context} \n\n query: {query}'
            prompt_template = prepare_prompt_template(model_id, prompt, context)
            print(prompt_template)
            query_bedrock_models(model_id, prompt_template, connect_id)
        else:
            print('Defaulting to Amazon Titan(titan-text-lite-v1) model, Model_id not passed.')
            prompt_template = prepare_prompt_template('amazon.titan-text-lite-v1', prompt, query)
            print(prompt_template)
            query_bedrock_models('amazon.titan-text-lite-v1', prompt_template, connect_id)
                
    except Exception as e:
        print(f'Exception {e}')
        return failure_response(f'Exception occured when querying LLM: {e}')



def query_bedrock_models(model, prompt, connect_id):
    response = bedrock_client.invoke_model_with_response_stream(
        body=json.dumps(prompt),
        modelId=model,
        accept='application/json',
        contentType='application/json'
    )

    for evt in json.loads(response['body'].read()):
        print('---- evt ----')
        print(dir(evt))
        chunk = evt['chunk']['bytes']
        print(f'chunk {bytes}')
        result = parse_response(chunk)
        websocket_send(connect_id, { "text": result } )
        # call websocket here

def parse_response(model_id, response): 
    print(f'parse_response {response}')
    result = ''
    if model_id in ['anthropic.claude-v1', 'anthropic.claude-instant-v1', 'anthropic.claude-v2']:
        result = response['completion']
    elif model_id == 'cohere.command-text-v14':
        text = ''
        for token in response['generations']:
            text = text + token['text']
        result = text
    elif model_id == 'amazon.titan-text-express-v1':
        #TODO set the response for this model
        result = response
    elif model_id in ['ai21.j2-ultra-v1', 'ai21.j2-mid-v1']:
        result = response
    print('parse_response_final_result' + result)
    return result

def prepare_prompt_template(model_id, prompt, query):
    prompt_template = {"inputText": f"""{prompt}\n{query}"""}
    if model_id in ['anthropic.claude-v1', 'anthropic.claude-instant-v1', 'anthropic.claude-v2']:
        prompt_template = {"prompt":f"Human:{prompt}. \n{query}\n\nAssistant:", "max_tokens_to_sample": 900}
    elif model_id == 'cohere.command-text-v14':
        prompt_template = {"prompt": f"""{prompt}\n
                              {query}"""}
    elif model_id == 'amazon.titan-text-express-v1':
        prompt_template = {"inputText": f"""{prompt}\n
                            {query}
                            """}
    elif model_id in ['ai21.j2-ultra-v1', 'ai21.j2-mid-v1']:
        prompt_template = {
            "prompt": f"""{prompt}\n
                            {query}
                            """
        }
    return prompt_template


def handler(event, context):
    LOG.info(
        "---  Amazon Opensearch Serverless vector db example with Amazon Bedrock Models ---")
    print(f'event - {event}')
    connect_id = event['requestContext']['connectionId']
    routeKey = event['requestContext']['routeKey']
    
    if routeKey != '$connect': 
        if 'body' in event:
            query = event['body']['query']
            behaviour = event['body']['behaviour']
            model_id = event['body']['model_id']
            query_data(query, behaviour, model_id, connect_id)

    

def failure_response(connect_id, error_message):
    global websocket_client
    err_msg = {"success": False, "errorMessage": error_message, "statusCode": "400"}
    websocket_send(connect_id, err_msg)
    

def success_response(connect_id, result):
    success_msg = {"success": True, "result": result, "statusCode": "200"}
    websocket_send(connect_id, success_msg)

def websocket_send(connect_id, message):
    response = websocket_client.post_to_connection(
                Data=str.encode(json.dumps(message, indent=4)),
                ConnectionId=connect_id
            )


class CustomJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            if float(obj).is_integer():
                return int(float(obj))
            else:
                return float(obj)
        return super(CustomJsonEncoder, self).default(obj)

