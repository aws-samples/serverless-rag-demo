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
from datetime import datetime
import csv
import re
from ddb_util import push_to_dynamodb


from prompt_utils import get_system_prompt, agent_execution_step, rag_chat_bot_prompt

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

DEFAULT_PROMPT = """You are a helpful, respectful and honest assistant.
                    Always answer as helpfully as possible, while being safe.
                    Please ensure that your responses are socially unbiased and positive in nature.
                    If a question does not make any sense, or is not factually coherent,
                    explain why instead of answering something not correct.
                    If you don't know the answer to a question,
                    please don't share false information. """


if is_rag_enabled == 'yes':
    ops_client = client = OpenSearch(
        hosts=[{'host': endpoint, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )

bedrock_client = boto3.client('bedrock-runtime')


def query_data(query, behaviour, model_id, query_vectordb, connect_id):
    global DEFAULT_PROMPT
    global embed_model_id
    global bedrock_client
    prompt = DEFAULT_PROMPT
    if behaviour in ['english', 'hindi', 'thai', 'spanish', 'french', 'german', 'bengali', 'tamil', 'arabic', 'italian']:
        prompt = f''' Output Rules :
                       {DEFAULT_PROMPT}
                       You will always reply in {behaviour.upper()} language only. Do not forget this line
                  '''
    elif behaviour == 'sentiment':
        prompt =  '''You are a Sentiment analyzer named Irra created by FSTech. Your goal is to analyze sentiments from a user question.
                     You will classify the sentiment as either positive, neutral or negative.
                     You will share a confidence level between 0-100, a lower value corresponds to negative and higher value towards positive
                     You will share the words that made you think its overall a positive or a negative or neutral sentiment
                     You will also share any improvements recommended in the review
                     You will structure the sentiment analysis in a json as below
                      where sentiment can be positive, neutral, negative.
                      confidence score can be a value from 0 to 100
                      reasons would contain an array of words, sentences that made you think its overall a positive or a negative or neutral sentiment
                      improvements would contain an array of improvements recommended in the review

                     {
                      "sentiment": "positive",
                      "confidence_score: 90.5,
                      "reasons": [ ],
                      "improvements": [ ]
                     }
                     '''

    elif behaviour == 'pii':
        prompt = '''
                    You are a PII(Personally identifiable information) data detector named Ira created by FSTech.
                    Your goal is to identify PII data in the user question.
                    You will structure the PII data in a json array as below
                    where type is the type of PII data, and value is the actual value of PII data.
                    [{
                     "type": "address",
                     "value": "123 Main St"
                    }]
                    '''
    elif behaviour == 'redact':
        prompt = '''You will serve to protect user data and redact any PII information observed in the user statement.
                    You will swap any PII with the term REDACTED.
                    You will then only share the REDACTED user statement
                    You will not explain yourself.
                '''
    elif behaviour == 'chat':
        prompt = rag_chat_bot_prompt
    else:
        prompt = DEFAULT_PROMPT

    context = ''
    user_query = ''

    if query_vectordb == 'yes' and query is not None and len(query.split()) > 0 and behaviour not in ['sentiment', 'pii', 'redact']:
        try:

            user_query, img_ids =extract_query_image_values(query)
            print(f'Extracted Query {user_query}')
            embeddings_key="embedding"
            if 'cohere' in   embed_model_id:
                response = bedrock_client.invoke_model(
                body=json.dumps({"texts": [user_query], "input_type": 'search_query'}),
                modelId=embed_model_id,
                accept='application/json',
                contentType='application/json'
                )
                embeddings_key="embeddings"
            else:
                print(f'In here')
                # Get the query embedding from amazon-titan-embed model
                response = bedrock_client.invoke_model(
                    body=json.dumps({"inputText": user_query}),
                    modelId=embed_model_id,
                    accept='application/json',
                    contentType='application/json'
                )
                
            result = json.loads(response['body'].read())
            finish_reason = result.get("message")
            if finish_reason is not None:
                    print(f'Embed Error {finish_reason}')
            embedded_search = result.get(embeddings_key)

            vector_query = {
                "size": 10,
                "query": {"knn": {"embedding": {"vector": embedded_search, "k": 5}}},
                "_source": False,
                "fields": ["text", "doc_type"]
            }
            print(f'Search for context from Opensearch serverless vector collections {vector_query}')

            try:
                response = ops_client.search(body=vector_query, index=INDEX_NAME)
                for data in response["hits"]["hits"]:
                    if context == '':
                        context = data['fields']['text'][0]
                    else:
                        context = context + ' ' + data['fields']['text'][0]
            except Exception as e:
                print('Vector Index does not exist. Please index some documents')

        except Exception as e:
            return failure_response(connect_id, f'{e.info["error"]["reason"]}')


    try:
        response = None
        LOG.debug(f'LLM Model ID -> {model_id}')
        model_list = ['anthropic.claude-3','meta.llama2-']

        if model_id.startswith(tuple(model_list)):
            prompt_template = prepare_prompt_template(prompt, context, query, connect_id)
            query_bedrock_models(model_id, prompt_template, connect_id, behaviour)
        else:
            return failure_response(connect_id, f'Model not available on Amazon Bedrock {model_id}')

    except Exception as e:
        print(f'Exception {e}')
        return failure_response(connect_id, f'Exception occured when querying LLM: {e}')



def query_bedrock_models(model, prompt, connect_id, behaviour):
    print(f'Bedrock prompt {prompt}')
    response = bedrock_client.invoke_model_with_response_stream(
        body=json.dumps(prompt),
        modelId=model,
        accept='application/json',
        contentType='application/json'
    )
    assistant_chat = ''
    counter=0
    sent_ack = False
    for evt in response['body']:
        counter = counter + 1
        print(dir(evt))
        chunk_str = None
        if 'chunk' in evt:
            sent_ack = False
            chunk = evt['chunk']['bytes']
            chunk_json = json.loads(chunk.decode("UTF-8"))
            print(f'Chunk JSON {json.loads(str(chunk, "UTF-8"))}' )
            if 'claude-3-' in model:
                if chunk_json['type'] == 'content_block_delta' and chunk_json['delta']['type'] == 'text_delta':
                    chunk_str = chunk_json['delta']['text']
            else:
                chunk_str = chunk_json['completion']
            print(f'chunk string {chunk_str}')
            if chunk_str is not None:
                websocket_send(connect_id, { "text": chunk_str } )
                assistant_chat = assistant_chat + chunk_str
            if behaviour == 'chat' and counter%100 == 0:
                # send ACK to UI, so it print the chats
                websocket_send(connect_id, { "text": "ack-end-of-string" } )
                sent_ack = True
               
            #websocket_send(connect_id, { "text": result } )            #TODO:: this is bedrock response (final)
        elif 'internalServerException' in evt:
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

    if behaviour == 'chat' and not sent_ack:
            sent_ack = True
            websocket_send(connect_id, { "text": "ack-end-of-string" } )

     # save to DB
    assisntant_messages =  {"role": "assistant", "content": str(assistant_chat)}
    push_to_dynamodb("", connect_id,  assisntant_messages)
    
# Agent code start
list_of_tools_specs = []
tool_names = []
tool_descriptions = []


def query_agents(agent_type, user_input, connect_id):
    format_prompt_invoke_function(agent_type, user_input, connect_id)

def format_prompt_invoke_function(agent_type, user_input, connect_id):
    chat_history_list = json.loads(base64.b64decode(user_input))
    if len(chat_history_list) > 0:
        if 'role' in chat_history_list[0] and 'user' == chat_history_list[0]['role']:
            for text_inputs in chat_history_list[0]['content']:
                if text_inputs['type'] == 'text' and '<user-request>' not in text_inputs['text']:
                    text_inputs['text'] =  f'What is the first step in order to solve this problem?  <user-request> {text_inputs["text"]} </user-request>'
                    break
                if '<special_char>' in text_inputs['text']:
                    text_inputs['text'] = re.sub('<special_char>.*</special_char>', '', text_inputs['text'])

    print(f'Agent Chat history {chat_history_list}')

    system_prompt = get_system_prompt(agent_type)

    prompt_template= {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 10000,
                        "system": system_prompt,
                        "messages": chat_history_list
                    }

    prompt_flow = []
    prompt_flow.extend(chat_history_list)

    # Try to solve a user query in 5 steps
    for i in range(5):
        output = invoke_model(i, prompt_template, connect_id)
        print(f'Step {i} output {output}')
        done, human_prompt, assistant_prompt = agent_execution_step(i, output)
        prompt_flow.append({"role":"assistant", "content": assistant_prompt })
        if human_prompt is not None:
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


def invoke_model(step_id, prompt, connect_id):
    modelId = "anthropic.claude-3-sonnet-20240229-v1:0"
    result = query_bedrock_claude3_model(step_id, modelId, prompt, connect_id)
    return ''.join(result)


def query_bedrock_claude3_model(step_id, model, prompt, connect_id):
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
    for evt in response['body']:
        if 'chunk' in evt:
            chunk = evt['chunk']['bytes']
            chunk_json = json.loads(chunk.decode("UTF-8"))

            if chunk_json['type'] == 'content_block_delta' and chunk_json['delta']['type'] == 'text_delta':
                cnk_str.append(chunk_json['delta']['text'])
        else:
            cnk_str.append(evt)
            break
    return cnk_str


# Agent code end

# Focus is only on Claude and Messages API builder
def prepare_prompt_template(system_prompt, context, query, connect_id):
    prompt_template_arr = claude3_prompt_builder_for_images_and_text(query, context)
    user_messages =  {"role": "user", "content": prompt_template_arr}  #TODO::  this is user message
    #save conversation
    push_to_dynamodb('', connect_id, user_messages)
    
    prompt_template= {"anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 10000,
                        "system": system_prompt,
                        "messages": [user_messages]
                    }
    return prompt_template


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
                if 'agent' not in behaviour:
                    query_vectordb = input_to_llm['query_vectordb'] if 'query_vectordb' in input_to_llm else 'no'
                    model_id = input_to_llm['model_id']
                    query_data(query, behaviour, model_id, query_vectordb, connect_id)
                else:
                    query_agents(behaviour, query, connect_id)
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


def claude3_prompt_builder_for_images_and_text(query, context):
    prompt_content = []
    user_queries_data = json.loads(base64.b64decode(query))
    # TODO Add previous chat history from dynamodb
    for user_query_type in user_queries_data:
        if  user_query_type['type'] == 'text':
            pmt_template = f"""Here is the context: {context} .
                               Here is the user's question <question>{user_query_type['data']}<question>
                            """
            prompt_content.append({ "type": "text", "text": pmt_template})

        elif user_query_type['type'] == 'image':
            if 'data' in user_query_type and 'file_extension' in user_query_type:
                s3_key = f"bedrock/data/{user_query_type['data']}.{user_query_type['file_extension']}"
                encoded_file = base64.b64encode(get_file_from_s3(s3_bucket_name, s3_key))
                prompt_content.append({ "type": "image", "source":
                                       { "type": "base64", "media_type": "image/jpeg", "data": encoded_file.decode('utf-8')}
                                })
        elif user_query_type['type'] == 'other':
            if 'data' in user_query_type and 'file_extension' in user_query_type:
                s3_key = f"bedrock/data/{user_query_type['data']}.{user_query_type['file_extension']}"
                text_data_from_file = ''
                text_data_from_file = get_contents(user_query_type['file_extension'], get_file_from_s3(s3_bucket_name, s3_key))
                prompt_content.append({ "type": "text", "text": f"""This is additional data {text_data_from_file}. Provide useful insights"""})


    return prompt_content


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

