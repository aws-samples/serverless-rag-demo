from io import BytesIO
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
import base64
from datetime import datetime, timezone
import time
import threading
from pypdf import PdfReader
import PIL
from prompt_builder import generate_claude_3_ocr_prompt, generate_claude_3_title_prompt

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
# http endpoint for your cluster (opensearch required for vector index usage)
# Self managed or cluster based OPENSEARCH
endpoint = getenv("OPENSEARCH_VECTOR_ENDPOINT", "https://admin:P@@search-opsearch-public-24k5tlpsu5whuqmengkfpeypqu.us-east-1.es.amazonaws.com:443")
SAMPLE_DATA_DIR=getenv("SAMPLE_DATA_DIR", "sample_data")
INDEX_NAME = getenv("VECTOR_INDEX_NAME", "sample-embeddings-store-dev")
s3_bucket_name = getenv("S3_BUCKET_NAME", "S3_BUCKET_NAME_MISSING")
embed_model_id = getenv("EMBED_MODEL_ID", "amazon.titan-embed-image-v1")
ocr_model_id = getenv("OCR_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

credentials = boto3.Session().get_credentials()

service = 'aoss'
region = getenv("REGION", "us-east-1")
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key,
                   region, service, session_token=credentials.token)

bedrock_client = boto3.client('bedrock-runtime')
textract_client = boto3.client('textract')

ops_client = OpenSearch(
        hosts=[{'host': endpoint, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )
wss_url = getenv("WSS_INDEX_NOTIFY_URL", "WEBSOCKET_URL_MISSING")
wss_url=wss_url.replace('wss:', 'https:')
if wss_url.endswith('/'):
    wss_url = wss_url[:-1]
websocket_client = boto3.client('apigatewaymanagementapi', endpoint_url=wss_url)

def create_index() :
    LOG.debug(f'method=create_index')
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
                        "method": {
                            "name":"hnsw",
                            "engine":"nmslib",
                            "space_type": "cosinesimil"
                        }
                    },
                }
            },
        }
        LOG.debug(f'method=create_index, index_settings={settings}')
        res = ops_client.indices.create(index=INDEX_NAME, body=settings, ignore=[400])
        LOG.debug(f'method=create_index, index_creation_response={res}')

def index_documents(event):
    LOG.info(f'method=index_documents, event={event}')
    payload = json.loads(event['body'])
    text_val = payload['text']
    title = payload['title']
    s3_source = payload['s3_source']
    connect_id = payload['connect_id']

    text_splitter = RecursiveCharacterTextSplitter(
    # Set a really small chunk size, just to show.
    chunk_size = 200,
    chunk_overlap  = 10)

    texts = text_splitter.create_documents([text_val])

    if texts is not None and len(texts) > 0:
        create_index()
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_generate_embeddings_and_index,chunk_text, title, s3_source) for chunk_text in texts]
            for future in as_completed(futures):
                result = future.result()
                if result['statusCode'] != "200":
                    return failure_response(result['errorMessage'])
                else:
                    print(result)
            websocket_send(connect_id, {"success": True, "message": "Index complete", "statusCode": "200"})
                    
    return success_response('Documents indexed successfully')


def _generate_embeddings_and_index(chunk_text, title, s3_source):
        body = json.dumps({"inputText": chunk_text.page_content, "embeddingConfig": {"outputEmbeddingLength": 384}})
        
        try:
            response = bedrock_client.invoke_model(
                    body = body,
                    modelId = embed_model_id,
                    accept = 'application/json',
                    contentType = 'application/json'
            )
            result = json.loads(response['body'].read())

            finish_reason = result.get("message")
            if finish_reason is not None:
                print(f'Embed Error {finish_reason}')
                
            embeddings = result.get("embedding")
        except Exception as e:
            return failure_response(f'Do you have access to embed model {embed_model_id}. Error {e.info["error"]["reason"]}')
        doc = {
            'embedding' : embeddings,
            'text': chunk_text.page_content,
            'timestamp': datetime.today().replace(tzinfo=timezone.utc).isoformat(),
            'meta': {
                'title': title,
                's3_source': s3_source
            },
            's3_source_uri': s3_source
        }

        try:
            # Index the document
            ops_client.index(index=INDEX_NAME, body=doc)
            return success_response('Documents Indexed Successfully')
        except Exception as e:
            LOG.error(f'method=_generate_embeddings_and_index, error={e.info["error"]["reason"]}')
            return failure_response(f'Error indexing documents {e.info["error"]["reason"]}')
        

def delete_index(event):
    try:
        res = ops_client.indices.delete(index=INDEX_NAME)
        LOG.debug(f"method=delete_index, delete_response={res}")
    except Exception as e:
        LOG.error(f"method=delete_index, error={e.info['error']['reason']}")
        return failure_response(f'Error deleting index. {e.info["error"]["reason"]}')
    return success_response('Index deleted successfully')


def delete_documents_by_s3_uri(s3_source: str):
    delete_query= { 
        "query": { 
            "match": { 
                "s3_source_uri": s3_source
                }
        }
    }
    
    try:
        res = ops_client.indices.delete_by_query(index=INDEX_NAME, body=delete_query)
        LOG.debug(f"method=delete_documents_by_s3_uri, delete_response={res}")
    except Exception as e:
        LOG.error(f'method=delete_documents_by_s3_uri, delete_query={delete_query}')
        LOG.error(f"method=delete_documents_by_s3_uri, error={e.info['error']['reason']}")
        return failure_response(f'Error deleting by query. {e.info["error"]["reason"]}')
    return success_response(f'vectorized content for file {s3_source} deleted successfully')


def connect_tracker(event):
    return success_response('Successfully connection')


def create_presigned_post(event):
    # Generate a presigned S3 POST URL
    query_params = {}
    if 'queryStringParameters' in event:
        query_params = event['queryStringParameters']
    
    if 'file_extension' in query_params and 'file_name' in query_params:
        extension = query_params['file_extension']
        file_name = query_params['file_name']
        connect_id = 'none'
        if 'connect_id' in query_params:
            connect_id = query_params['connect_id']
        session = boto3.Session()
        s3_client = session.client('s3', region_name=region)
        file_name = file_name.replace(' ', '_')

        # s3_client = boto3.client('s3')
        now = datetime.now()
        date_time = now.strftime("%Y-%m-%d-%H-%M-%S")
        s3_key = f"index/data/{file_name}_{date_time}.{extension}"
        # response = s3_client.generate_presigned_post(Bucket=s3_bucket_name,
        #                                       Key=s3_key,
        #                                       Fields=None,
        #                                       Conditions=[]
        #                                   )
        response = s3_client.generate_presigned_post(Bucket=s3_bucket_name,
                                            Key=s3_key,
                                            Fields={'x-amz-meta-connect_id': connect_id},
                                            Conditions=[{'x-amz-meta-connect_id': connect_id}]
                                        )
        


        # The response contains the presigned URL and required fields
        return success_response(response)
    else:
        return failure_response('Missing file_extension field cannot generate signed url')


def extract_file_extension(base64_encoded_file):
    if base64_encoded_file.find(';') > -1:
        extension = base64_encoded_file.split(';')[0]
        return extension[extension.find('/') + 1:]
    # default to PNG if we are not able to extract extension or string is not bas64 encoded
    return 'png'

"""{
  "Records": [
    {
      "eventVersion": "2.1",
      "eventSource": "aws:s3",
      "awsRegion": "us-east-1",
      "eventTime": "2024-06-18T10:26:52.692Z",
      "eventName": "ObjectRemoved:Delete",
      "userIdentity": {
        "principalId": "AWS:AROAWO3F73T2G7EGZUV5V:fraseque-Isengard"
      },
      "requestParameters": {
        "sourceIPAddress": "10.107.97.237"
      },
      "responseElements": {
        "x-amz-request-id": "V2B093Q3C8EM8HYQ",
        "x-amz-id-2": "yM1VS0B+uudubjZhOxtVCjzh/pKL/4Yq8VNsOa8mZfHcRPiKun0n9bgQqAKpuMdySrSdpsqVywDTlQI05JJrHC2OAQbxHNSf9gaaj9GYkys="
      },
      "s3": {
        "s3SchemaVersion": "1.0",
        "configurationId": "invoke_lambda",
        "bucket": {
          "name": "bedrockstore-dev-444206144756-us-east-1",
          "ownerIdentity": {
            "principalId": "A39XEE2Y21D328"
          },
          "arn": "arn:aws:s3:::bedrockstore-dev-444206144756-us-east-1"
        },
        "object": {
          "key": "index/Screenshot+2024-06-17+at+12.12.12%E2%80%AFPM.png",
          "sequencer": "00667160ECAB054C4A"
        }
      }
    }
  ]
}"""

def process_file_upload(event):
    if 'Records' in event:
        for record in event['Records']:
            if record['eventName'] == 'ObjectCreated:Post':
                s3_source=''
                s3_key=''
                file_extension = 'txt'
                if 's3' in record:
                    s3_key = record['s3']['object']['key']
                    s3_bucket = record['s3']['bucket']['name']
                    s3_source = f'https://{s3_bucket}/{s3_key}'
                if '.' in s3_key:
                    file_extension = s3_key[s3_key.rindex('.')+1:]
                content, metadata = get_file_from_s3(s3_key)
                print(f'Metadata -> {metadata}')
                if file_extension.lower() in ['pdf']:
                    try:
                        reader = PdfReader(BytesIO(content))
                        LOG.debug(f'method=process_file_upload, num_of_pages={len(reader.pages)}')
                        for page in reader.pages:
                            text_value = None
                            # Read Text on Page
                            text_value = page.extract_text()
                            LOG.debug(f'method=process_file_upload, file_type=pdf-text, content={content}')
                            generate_title_and_index_doc(event, page.page_number, text_value, s3_source, metadata)
                            # Read Image on Page
                            for image_file_object in page.images:
                                # Extract through low cost LLM (Claude3-Haiku)
                                ocr_prompt = generate_claude_3_ocr_prompt(image_file_object.data)
                                text_value = query_bedrock(ocr_prompt, ocr_model_id)
                                print(f'Image PDF: Text value {text_value}')
                                LOG.debug(f'method=process_file_upload, file_type=pdf-image, content={text_value}')
                                generate_title_and_index_doc(event, page.page_number, text_value, s3_source, metadata)
    
                        
                    except Exception as e:
                        print(f'Error reading PDF {e}')
                        return failure_response('PDF could not be read')
                elif file_extension.lower() in ['png', 'jpg']:
                    # Extract through low cost LLM (Claude3-Haiku)
                    print(f'File is an image {record}')
                    ocr_prompt = generate_claude_3_ocr_prompt(content)
                    text_value = query_bedrock(ocr_prompt, ocr_model_id)
                    LOG.debug(f'method=process_file_upload, file_type=image-text, content={text_value}')
                    generate_title_and_index_doc(event, 1, text_value, s3_source, metadata)
                    
                else:
                    decoded_txt = content.decode()
                    print(f'Decoded txt {decoded_txt}')
                    generate_title_and_index_doc(event, 1, decoded_txt, s3_source, metadata)
                # TODO Websocket notify
                # TODO -> Store this information in dynamoDB so its easier to delete the vector if the file no longer exists in s3    
            elif record['eventName'] == 'ObjectRemoved:Delete':
                s3_source=''
                s3_key=''
                if 's3' in record:
                    s3_key = record['s3']['object']['key']
                    s3_bucket = record['s3']['bucket']['name']
                    s3_source = f'https://{s3_bucket}/{s3_key}'
                    delete_documents_by_s3_uri(s3_source)
                    # TODO Websocket notify
    
    return success_response(f'No files to read {event}')

def generate_title_and_index_doc(event, page_number, text_value, s3_source, metadata):
    if text_value:
        if page_number <2:
            title_value = generate_title(text_value)
        text_value = f'Page Number: {page_number}, content: {text_value}'
        event['body'] = json.dumps({"text": text_value, "title": title_value, 's3_source': s3_source})
        if 'x-amz-meta-connect_id' in metadata:
            connect_id = metadata['x-amz-meta-connect_id']
            websocket_send(connect_id, {"success": True, "message": "Index in progress", "statusCode": "200"})
            event['body']['connect_id']=connect_id
        index_documents(event)

def generate_title(text_snippet):
    title_prompt = generate_claude_3_title_prompt(text_snippet)
    title_value = query_bedrock(title_prompt, ocr_model_id)
    return title_value

def query_bedrock(prompt, model_id): 
    response = bedrock_client.invoke_model(
        body=json.dumps(prompt),
        modelId=model_id,
        accept='application/json',
        contentType='application/json'
    )
    response_body = json.loads(response.get('body').read())
    texts = []
    if 'content' in response_body:
        for content in response_body['content']:
            if 'text' in content:
                text = content['text']
                try:
                    text = json.loads(content['text'])['text']
                except Exception as e:
                    print(f'Error parsing JSON {e}')
                texts.append(text)

    final_text = ' \n '.join(texts)
    print(response_body)
    return final_text


def get_file_from_s3(s3_key):
    s3_client = boto3.client('s3')
    
    response = s3_client.get_object(Bucket=s3_bucket_name, Key=s3_key)
    file_bytes = response['Body'].read()
    print(f'returns S3 encoded object from key {s3_bucket_name}/{s3_key}')
    return file_bytes, response['Metadata']

def websocket_send(connect_id, message):
    global websocket_client
    global wss_url
    print(f'WSS URL {wss_url}, connect_id {connect_id}')
    response = websocket_client.post_to_connection(
                Data=json.dumps(message, indent=4).encode('utf-8'),
                ConnectionId=connect_id
    )

def handler(event, context):
    LOG.info("---  Amazon Opensearch Serverless vector db example with Amazon Bedrock Models ---")
    LOG.info(f"--- Event {event} --")
    global websocket_client

    if 'httpMethod' not in event and 'requestContext' in event:
        # This is a websocket request
        stage = event['requestContext']['stage']
        api_id = event['requestContext']['apiId']
        domain = f'{api_id}.execute-api.{region}.amazonaws.com'
        websocket_client = boto3.client('apigatewaymanagementapi', endpoint_url=f'https://{domain}/{stage}')

        connect_id = event['requestContext']['connectionId']
        routeKey = event['requestContext']['routeKey']

        if routeKey != '$connect':
            if 'body' in event:
                index_request_check = json.loads(event['body'], strict=False)
                print(f'index_request_check: {index_request_check}')
                if 'request' in index_request_check and index_request_check['request'] == 'connect_id':
                    message = {"success": True, "connect_id": connect_id, "statusCode": "200"}
                    websocket_send(connect_id, message)
                else:
                    message = {"success": True, "connect_id": connect_id, "statusCode": "200"}
                    websocket_send(connect_id, message)
                
        elif routeKey == '$connect':
            # TODO Add authentication of access token
            return {'statusCode': '200', 'body': 'Bedrock says hello' }
    
    elif 'httpMethod' in event:
        # This comes from S3 event notification
        if 'Records' in event:
            event['httpMethod']= 'POST'
            event['resource']='s3-upload-file'
    
        api_map = {
            'POST/rag/index-documents': lambda x: index_documents(x),
            'DELETE/rag/index-documents': lambda x: delete_index(x),
            'GET/rag/connect-tracker': lambda x: connect_tracker(x),
            'GET/rag/get-presigned-url': lambda x: create_presigned_post(x),
            'POSTs3-upload-file': lambda x: process_file_upload(x)   
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