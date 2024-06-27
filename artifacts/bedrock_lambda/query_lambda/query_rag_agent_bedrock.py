import boto3
from os import getenv
from opensearchpy import OpenSearch, RequestsHttpConnection, exceptions
from requests_aws4auth import AWS4Auth
import requests
from requests.auth import HTTPBasicAuth
import os
import json
from decimal import Decimal
import logging
import base64
import datetime
import csv
import re

from agents.retriever_agent import fetch_data, classify_and_translation_request
from prompt_utils import get_system_prompt, agent_execution_step, rag_chat_bot_prompt, AGENT_RULE_MAP, casual_prompt

bedrock_client = boto3.client('bedrock-runtime')
embed_model_id = getenv("EMBED_MODEL_ID", "amazon.titan-embed-image-v1")
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
endpoint = getenv("OPENSEARCH_VECTOR_ENDPOINT",
                  "https://admin:P@@search-opsearch-public-24k5tlpsu5whuqmengkfpeypqu.us-east-1.es.amazonaws.com:443")

SAMPLE_DATA_DIR = getenv("SAMPLE_DATA_DIR", "/var/task")
INDEX_NAME = getenv("VECTOR_INDEX_NAME", "sample-embeddings-store-dev")
wss_url = getenv("WSS_URL", "WEBSOCKET_URL_MISSING")
rest_api_url = getenv("REST_ENDPOINT_URL", "REST_URL_MISSING")
is_rag_enabled = getenv("IS_RAG_ENABLED", 'yes')
s3_bucket_name = getenv("S3_BUCKET_NAME", "S3_BUCKET_NAME_MISSING")
websocket_client = boto3.client('apigatewaymanagementapi', endpoint_url=wss_url)
lambda_client = boto3.client('lambda')

credentials = boto3.Session().get_credentials()
service = 'aoss'
region = getenv("REGION", "us-east-1")
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key,
                   region, service, session_token=credentials.token)

# Agent code start
list_of_tools_specs = []
tool_names = []
tool_descriptions = []

def query_rag_no_agent(user_input, connect_id):
    chat_input = json.loads(base64.b64decode(user_input))
    print(f'Chat history {chat_input}')

    if 'role' in chat_input[-1] and 'user' == chat_input[-1]['role']:
        classify_translate_json = classify_and_translation_request(user_input)

        for text_inputs in chat_input[-1]['content']:
            if text_inputs['type'] == 'text':
                if '<user-question>' not in text_inputs['text']:
                    text_inputs['text'] =  f'<user-question> {text_inputs["text"]} </user-question>'
                if 'QUERY_TYPE' in  classify_translate_json and classify_translate_json['QUERY_TYPE'] == 'RETRIEVAL':
                    if 'TRANSLATED_QUERY' in classify_translate_json:
                        user_input = classify_translate_json['TRANSLATED_QUERY']
                    context = fetch_data(user_input)
                    text_inputs['text'] = f"""<context> {context} </context> 
                                              {text_inputs['text']} """
                elif 'QUERY_TYPE' in  classify_translate_json and classify_translate_json['QUERY_TYPE'] == 'CASUAL':
                    rag_chat_bot_prompt = rag_chat_bot_prompt + casual_prompt
                break

        prompt_template = {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 10000,
                        "system": rag_chat_bot_prompt,
                        "messages": chat_input
        }
        print(f'chat prompt_template {prompt_template}')
        invoke_model(0, prompt_template, connect_id, True)
                    

def query_agents(agent_type, user_input, connect_id):
    chat_input = json.loads(base64.b64decode(user_input))
    # fetch last element from a list
    if 'role' in chat_input[-1] and 'user' == chat_input[-1]['role']:
            for text_inputs in chat_input[-1]['content']:
                if text_inputs['type'] == 'text' and '<user-request>' not in text_inputs['text']:
                    text_inputs['text'] =  f'What is the first step in order to solve this problem?  <user-request> {text_inputs["text"]} </user-request>'
                    break

    print(f'Agent Chat history {chat_input}')

    system_prompt = get_system_prompt(agent_type)

    prompt_template= {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 10000,
                        "system": system_prompt,
                        "messages": chat_input
                    }
    
    
    prompt_flow = []
    prompt_flow.extend(chat_input)

    # Try to solve a user query in 5 steps
    for i in range(5):
        print(f"prompt_template {prompt_template}, iteration : {i}")
        output = invoke_model(i, prompt_template, connect_id, False)
        print(f'Step {i} output {output}')
        done, human_prompt, assistant_prompt, agent_name = agent_execution_step(i, output)
        if agent_name in AGENT_RULE_MAP:
            system_prompt = system_prompt + AGENT_RULE_MAP[agent_name]
        
        prompt_flow.append({"role":"assistant", "content": assistant_prompt })
        if not done and human_prompt is not None:
            prompt_flow.append({"role":"user", "content":  human_prompt })
        # To be displayed in StackTrace
        websocket_send(connect_id, {"prompt_flow": prompt_flow, "done": done})

        if not done:
            print(f'{assistant_prompt}')
        else:
            print('Final answer from LLM:\n'+f'{assistant_prompt}')
            return assistant_prompt
            #break

        prompt_template= {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 10000,
                        "system": system_prompt,
                        "messages": prompt_flow
                    }
    if not done:
        prompt_flow.append({"role":"assistant", "content": {type: "text", "text": "I apologize but I cant answer this question"} })
        websocket_send(connect_id, {"prompt_flow": prompt_flow, "done": True})

def invoke_model(step_id, prompt, connect_id, send_on_socket=False):
    modelId = "anthropic.claude-3-sonnet-20240229-v1:0"
    #modelId = "anthropic.claude-3-haiku-20240307-v1:0"
    result = query_bedrock_claude3_model(step_id, modelId, prompt, connect_id, send_on_socket)
    return ''.join(result)


def query_bedrock_claude3_model(step_id, model, prompt, connect_id, send_on_socket=False):
    '''
       StepId and ConnectId can be used to stream data over the  socket
    '''
    cnk_str = []
    response = bedrock_client.invoke_model_with_response_stream(
        body=json.dumps(prompt),
        modelId=model,
        accept='application/json',
        contentType='application/json'
    )
    counter=0
    sent_ack = False
    for evt in response['body']:
        counter = counter + 1
        if 'chunk' in evt:
            chunk = evt['chunk']['bytes']
            chunk_json = json.loads(chunk.decode("UTF-8"))

            if chunk_json['type'] == 'content_block_delta' and chunk_json['delta']['type'] == 'text_delta':
                cnk_str.append(chunk_json['delta']['text'])
                if chunk_json['delta']['text'] and len((chunk_json['delta']['text']).split()) > 0:
                    if send_on_socket:
                        websocket_send(connect_id, { "text": chunk_json['delta']['text'] } )
        else:
            cnk_str.append(evt)
            break
        
        if 'internalServerException' in evt:
            result = evt['internalServerException']['message']
            websocket_send(connect_id, { "text": result } )
            break
        elif 'modelStreamErrorException' in evt:
            result = evt['modelStreamErrorException']['message']
            websocket_send(connect_id, { "text": result } )
            break
        elif 'throttlingException' in evt:
            result = evt['throttlingException']['message']
            websocket_send(connect_id, { "text": result } )
            break
        elif 'validationException' in evt:
            result = evt['validationException']['message']
            websocket_send(connect_id, { "text": result } )
            break

    if send_on_socket:
        websocket_send(connect_id, { "text": "ack-end-of-msg" } )

    return cnk_str


def store_image_in_s3(event):
    payload = json.loads(event['body'])
    file_encoded_data = payload['content']
    content_id = payload['id']
    file_extension = extract_file_extension(file_encoded_data)
    file_encoded_data = file_encoded_data[file_encoded_data.find(",") + 1:]
    file_content = base64.b64decode(file_encoded_data)
    s3_client = boto3.client('s3')
    s3_key = f"bedrock/data/{content_id}.{file_extension}"
    s3_client.put_object(Body=file_content, Bucket=s3_bucket_name, Key=s3_key)
    return http_success_response({'file_extension': file_extension, 'file_id': content_id, 'message': 'stored successfully'})


def extract_file_extension(base64_encoded_file):
    if base64_encoded_file.find(';') > -1:
        extension = base64_encoded_file.split(';')[0]
        return extension[extension.find('/') + 1:]
    # default to PNG if we are not able to extract extension or string is not bas64 encoded
    return 'png'

def handler(event, context):
    global region
    global websocket_client
    LOG.info(
        "---  Amazon Opensearch Serverless vector db example with Amazon Bedrock Models ---")
    print(f'event - {event}')

    if 'httpMethod' not in event and 'requestContext' in event:
    # this is a websocket request
        stage = event['requestContext']['stage']
        api_id = event['requestContext']['apiId']
        domain = f'{api_id}.execute-api.{region}.amazonaws.com'
        websocket_client = boto3.client('apigatewaymanagementapi', endpoint_url=f'https://{domain}/{stage}')

        connect_id = event['requestContext']['connectionId']
        routeKey = event['requestContext']['routeKey']

        if routeKey != '$connect':
            if 'body' in event:
                input_to_llm = json.loads(event['body'], strict=False)
                print('input_to_llm: ', input_to_llm)
                query = input_to_llm['query']
                behaviour = input_to_llm['behaviour']
                if behaviour == 'advanced-agent':
                    query_agents(behaviour, query, connect_id)
                else:
                    query_rag_no_agent(query, connect_id)
        elif routeKey == '$connect':
            # TODO Add authentication of access token
            return {'statusCode': '200', 'body': 'Bedrock says hello' }
            
    elif 'httpMethod' in event:
        api_map = {
            'POST/rag/file_data': lambda x: store_image_in_s3(x)
        }
        http_method = event['httpMethod'] if 'httpMethod' in event else ''
        api_path = http_method + event['resource']
        try:
            if api_path in api_map:
                LOG.debug(f"method=handler , api_path={api_path}")
                return respond(None, api_map[api_path](event))
            else:
                LOG.info(f"error=api_not_found , api={api_path}")
                return respond(http_failure_response('api_not_supported'), None)
        except Exception:
            LOG.exception(f"error=error_processing_api, api={api_path}")
            return respond(http_success_response('system_exception'), None)

    return {'statusCode': '200', 'body': 'Bedrock says hello' }


def http_failure_response(error_message):
    return {"success": False, "errorMessage": error_message, "statusCode": "400"}

def http_success_response(result):
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

def failure_response(connect_id, error_message):
    global websocket_client
    err_msg = {"success": False, "errorMessage": error_message, "statusCode": "400"}
    websocket_send(connect_id, err_msg)


def extract_query_image_values(query):
    image_id = []
    user_query = []
    user_queries_data = json.loads(base64.b64decode(query))
    for user_query_type in user_queries_data:
        if 'type' in user_query_type and user_query_type['type'] == 'text':
            user_query.append(user_query_type['data'])
        elif 'type' in user_query_type and user_query_type['type'] == 'image':
            image_id.append(user_query_type['data'])
    return ' '.join(user_query), image_id


def get_contents(file_extension, file_bytes):
    content = ' '
    try:
        if file_extension in ['pdf']:
            textract_client = boto3.client('textract')
            response = textract_client.detect_document_text(Document={'Bytes': file_bytes})
            for block in response['Blocks']:
                if block['BlockType'] == 'LINE':
                    content = content + ' ' + block['Text']

        else:
            #file_extension in ['sql', 'txt', 'json', 'csv']:
            #if file_extension in ['csv', 'xls', 'xlsx']:
            content = file_bytes.decode()
    except Exception as e:
        print(f'Exception reading contents from file {e}')
    print(f'file-content {content}')
    return content

def get_file_from_s3(s3bucket, key):
    s3 = boto3.resource('s3')
    obj = s3.Object(s3bucket, key)
    file_bytes = obj.get()['Body'].read()
    print(f'returns S3 encoded object from key {s3bucket}/{key}')
    return file_bytes

def success_response(connect_id, result):
    success_msg = {"success": True, "result": result, "statusCode": "200"}
    websocket_send(connect_id, success_msg)

def websocket_send(connect_id, message):
    global websocket_client
    global wss_url
    print(f'WSS URL {wss_url}, connect_id {connect_id}')
    response = websocket_client.post_to_connection(
                Data=base64.b64encode(json.dumps(message, indent=4).encode('utf-8')),
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

