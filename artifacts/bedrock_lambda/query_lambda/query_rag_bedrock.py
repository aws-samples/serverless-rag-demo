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


def query_data(event):
    query = None
    behaviour = None
    global DEFAULT_SYSTEM_PROMPT
    global embed_model_id
    global bedrock_client
    if event['queryStringParameters'] and 'query' in event['queryStringParameters']:
        query = event['queryStringParameters']['query']
    if event['queryStringParameters'] and 'behaviour' in event['queryStringParameters']:
        behaviour = event['queryStringParameters']['behaviour']
        prompt = DEFAULT_PROMPT
        if behaviour in ['english', 'hindi', 'thai', 'spanish', 'bengali']:
            prompt = DEFAULT_PROMPT + \
                f'. You will always reply in {behaviour} language only.'
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
    except Exception as e:
        return failure_response(f'Do you have Titan-Embed Model Access {e.info["error"]["reason"]}')

    vector_query = {
        "size": 10,
        "query": {"knn": {"embedding": {"vector": embedded_search, "k": 2}}},
        "_source": False,
        "fields": ["text", "doc_type"]
    }
    content = None
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
        content = " "

    try:
        response = None
        if event['queryStringParameters'] and 'model' in event['queryStringParameters']:
            model_id = event['queryStringParameters']['model_id']

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
                prompt_template = prepare_prompt_template(model_id, prompt, query)
                print(prompt_template)
                response = query_bedrock_models(model_id, prompt_template)
            else:
                print('Defaulting to Amazon Titan(titan-text-lite-v1) model, Model_id not passed.')
                prompt_template = prepare_prompt_template('amazon.titan-text-lite-v1', prompt, query)
                print(prompt_template)
                response = query_bedrock_models('amazon.titan-text-lite-v1', prompt_template)

        return success_response(response)

    except Exception as e:
        print(f'Exception {e}')
        return failure_response(f'Exception occured when querying LLM: {e}')


def query_bedrock_models(model, prompt):
    response = bedrock_client.invoke_model(
        body=json.dumps({"inputText": prompt}),
        modelId=model,
        accept='application/json',
        contentType='application/json'
    )
    return json.loads(response['body'].read())


def prepare_prompt_template(model, prompt, query):
    prompt_template = {"inputText": f"""{prompt}
                            {query}
                            """}
    if model_id in ['anthropic.claude-v1', 'anthropic.claude-instant-v1', 'anthropic.claude-v2']:
        prompt_template = {"prompt": f"""Human:{prompt}
                      Assistant:"""}
    elif model_id == 'cohere.command-text-v14':
        prompt_template = {"prompt": f"""{prompt}
                              {query}"""}
    elif model_id == 'amazon.titan-text-express-v1':
        prompt_template = {"inputText": f"""{prompt}
                            {query}
                            """}
    elif model_id in ['ai21.j2-ultra-v1', 'ai21.j2-mid-v1']:
        prompt_template = {
            "prompt": f"""{prompt}
                            {query}
                            """
        }
    return prompt_template


def handler(event, context):
    LOG.info(
        "---  Amazon Opensearch Serverless vector db example with Amazon Bedrock Models ---")

    api_map = {
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
