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
from prompt_builder import generate_claude_3_ocr_prompt, generate_claude_3_title_prompt
import time
from boto3.dynamodb.conditions import Key, Attr
import time
import re
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
# http endpoint for your cluster (opensearch required for vector index usage)
# Self managed or cluster based OPENSEARCH
endpoint = getenv("OPENSEARCH_VECTOR_ENDPOINT", "https://admin:P@@search-opsearch-public-24k5tlpsu5whuqmengkfpeypqu.us-east-1.es.amazonaws.com:443")
SAMPLE_DATA_DIR=getenv("SAMPLE_DATA_DIR", "sample_data")
INDEX_NAME = getenv("VECTOR_INDEX_NAME", "sample-embeddings-store-dev")
s3_bucket_name = getenv("S3_BUCKET_NAME", "S3_BUCKET_NAME_MISSING")
embed_model_id = getenv("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
ocr_model_id = getenv("OCR_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
dynamodb_table_name = getenv("INDEX_DYNAMO_TABLE_NAME", "rag-llm-index-table-dev")

credentials = boto3.Session().get_credentials()

service = 'aoss'
region = getenv("REGION", "us-east-1")
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key,
                   region, service, session_token=credentials.token)

bedrock_client = boto3.client('bedrock-runtime')
dynamodb_client = boto3.resource('dynamodb')
table = dynamodb_client.Table(dynamodb_table_name)

ops_client = OpenSearch(
        hosts=[{'host': endpoint, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
)

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
                        "dimension": 1024,
                        "method": {
                            "name":"hnsw",
                            "engine":"faiss",
                            "space_type": "l2",
                            "parameters": {
                                "ef_construction": 512,
                                "m": 16
                          }
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
    email_id = payload['email_id']
    s3_source = payload['s3_source']

    text_splitter = RecursiveCharacterTextSplitter(
    # Set a really small chunk size, just to show.
    chunk_size = 500,
    chunk_overlap  = 10)

    texts = text_splitter.create_documents([text_val])

    if texts is not None and len(texts) > 0:
        create_index()
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_generate_embeddings_and_index,chunk_text, title, s3_source, email_id) for chunk_text in texts]
            for future in as_completed(futures):
                result = future.result()
                if result['statusCode'] != "200":
                    result['errorMessage']
                    return result
                
    return {"statusCode": "200", "message": "Documents indexed successfully"}


def _generate_embeddings_and_index(chunk_text, title, s3_source, email_id):
        body = json.dumps({"inputText": chunk_text.page_content})
        
        try:
            embeddings_key='embedding'
            if 'cohere' in   embed_model_id:
                response = bedrock_client.invoke_model(
                body=json.dumps({"texts": [chunk_text.page_content], "input_type": 'search_document', "embedding_types":["int8"]}),
                modelId=embed_model_id,
                accept='application/json',
                contentType='application/json'
                )
                embeddings_key="embeddings"
            else:
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
                
            embeddings = result.get(embeddings_key)
        except Exception as e:
            return failure_response(f'Do you have access to embed model {embed_model_id}. Error {e.info["error"]["reason"]}')
        doc = {
            'embedding' : embeddings,
            'text': chunk_text.page_content,
            'timestamp': datetime.today().replace(tzinfo=timezone.utc).isoformat(),
            'meta': {
                'title': title,
                's3_source': s3_source,
                'email_id': email_id
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
    REQUEST_TIMEOUT_VAL =300
    delete_body = []
    # AOSS doesnt support custom doc ID neither does it support delete_by_query
    # Workaround -> Search for the docs and then delete_by_id
    search_query= { 
        "query": { 
            "match": { 
                "s3_source_uri": s3_source
                }
        },
        "size": 50,
        "_source": { "exclude": [ "*" ] }
    }

    while True:
        try:
            search_response = ops_client.search( body=search_query, index=INDEX_NAME)
            LOG.info(f"Response of {search_query} for {INDEX_NAME} is - {search_response}")
            if search_response['hits']['total']['value'] == 0:
                LOG.warn(f"No documents found for s3_source {s3_source}")
                break
            else:
                for doc in search_response['hits']['hits']:
                    _id = doc["_id"]
                    _index = doc["_index"]
                    action = {"delete": {"_index": _index, "_id": _id}}
                    delete_body.append(action)
        except Exception as e:
            LOG.error(f"An exception occurred while processing the 'delete_by_query' request - {str(e)}")
            break
        if len(delete_body) > 0:
            try:
                response = ops_client.bulk(
                    body=delete_body,
                    index=INDEX_NAME,
                    request_timeout=REQUEST_TIMEOUT_VAL
                    )
                LOG.info(f"method=delete_documents_by_s3_uri, delete_response={response}")
            except Exception as e:
                LOG.error(f'method=delete_documents_by_s3_uri, delete_query={delete_body}, error={e}')
                
            delete_body = []
            time.sleep(30)
            LOG.info('Sleep for 30 seconds')
                                        
    return success_response(f'vectorized content for file {s3_source} deleted successfully')


def connect_tracker(event):
    return success_response('Successfully connection')


def create_presigned_post(event):
    # Generate a presigned S3 POST URL
    query_params = {}
    if 'queryStringParameters' in event:
        query_params = event['queryStringParameters']
    email_id = "empty_email_id"
    if 'requestContext' in event and 'authorizer' in event['requestContext']:
            if 'claims' in event['requestContext']['authorizer']:
                email_id = event['requestContext']['authorizer']['claims']['email']
    
    if 'file_extension' in query_params and 'file_name' in query_params:
        extension = query_params['file_extension']
        file_name = query_params['file_name']
        # Usecase could be index or ocr
        usecase_type = 'index'
        if 'type' in query_params and query_params['type'] in ['index', 'ocr']:
            usecase_type = query_params['type']
        # remove special characters from file name
        file_name = re.sub(r'[^a-zA-Z0-9_\-\.]','',file_name)

        session = boto3.Session()
        s3_client = session.client('s3', region_name=region)
        file_name = file_name.replace(' ', '_')

        # s3_client = boto3.client('s3')
        if usecase_type == 'index':
            now = datetime.now()
            date_time = now.strftime("%Y-%m-%d-%H-%M-%S")
            s3_key = f"{usecase_type}/data/{file_name}_{date_time}.{extension}"
        else:
            s3_key = f"{usecase_type}/data/{file_name}.{extension}"
        # response = s3_client.generate_presigned_post(Bucket=s3_bucket_name,
        #                                       Key=s3_key,
        #                                       Fields=None,
        #                                       Conditions=[]
        #                                   )
        utc_now = now_utc_iso8601()
        response = s3_client.generate_presigned_post(Bucket=s3_bucket_name,
                                            Key=s3_key,
                                            Fields={'x-amz-meta-email_id': email_id, 
                                                     'x-amz-meta-uploaded_at': utc_now
                                                    },
                                            Conditions=[{'x-amz-meta-email_id': email_id},
                                                        {'x-amz-meta-uploaded_at': utc_now}
                                                        ]
                                        )
        
        # 'x-amz-meta-email_id': email_id, 
        # The response contains the presigned URL and required fields
        return success_response(response)
    else:
        return failure_response('Missing file_extension field cannot generate signed url')

# Deletes single files from S3 triggering a deleting from Opensearch too
def delete_file(event):
    LOG.debug(f'method=delete_file, event={event}')
    # Delete the file from S3
    payload = json.loads(event['body'])
    if 's3_key' in payload:
        s3_key = payload['s3_key']
        s3_source = f'https://{s3_bucket_name}/{s3_key}'
        # delete a file from S3 by key and bucket name
        s3_client = boto3.client('s3')
        metadata = get_file_attributes(s3_key)
        email_id = 'no-id-set'
        if 'email_id' in metadata and 'uploaded_at' in metadata:
            email_id = metadata['email_id']
            utc_now = metadata['uploaded_at']
            index_audit_update(email_id, s3_source, s3_key, FILE_UPLOAD_STATUS._DELETED, utc_now, 'File deleted successfully')
            s3_client.delete_object(Bucket=s3_bucket_name, Key=s3_key)
        else:
            LOG.error(f'UTC/Email not found in Metadata of file email: {email_id}, utc: {utc_now}')
            return failure_response(f"UTC/Email not found in Metadata of file email: {email_id}, utc: {utc_now}")
        
        if 'email_id' in metadata and 'uploaded_at' in metadata:
            email_id = metadata['email_id']
            utc_now = metadata['uploaded_at']
            index_audit_update(email_id, s3_source, s3_key, FILE_UPLOAD_STATUS._INDEX_DELETE, utc_now, 'File index deleted successfully')
        
        LOG.info(f'method=delete_file, s3_key={s3_key}, message=complete')
        return success_response("deleted file successfully")
    else:
        return failure_response('Missing s3_key')



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
            if record['eventName'] == 'ObjectCreated:Post' and "index/" in record["s3"]["object"]["key"]:
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
                email_id = 'no-id-set'
                utc_now = ''
                if 'email_id' in metadata:
                    email_id = metadata['email_id']
                elif 'userIdentity' in record:
                    principal_id = record['userIdentity']['principalId']
                    email_id = principal_id.replace('AWS:', '').replace(':', '-')
                if 'upload_utc' in metadata:
                    utc_now = metadata['upload_utc']
                else:
                    utc_now = now_utc_iso8601()
                index_audit_insert(email_id, s3_source, s3_key, utc_now)
                
                try:
                    response = {}
                    index_success=True
                    if file_extension.lower() in ['pdf']:
                            reader = PdfReader(BytesIO(content))
                            LOG.debug(f'method=process_file_upload, num_of_pages={len(reader.pages)}')
                            for page in reader.pages:
                                text_value = None
                                # Read Text on Page
                                text_value = page.extract_text()
                                LOG.debug(f'method=process_file_upload, file_type=pdf-text, content={content}')
                                response = generate_title_and_index_doc(event, page.page_number, text_value, s3_source, email_id)
                                if 'statusCode' in response and response['statusCode'] != '200':
                                    LOG.error(f'Failed to index pdf {s3_key} on page {page.page_number}, error={response}')
                                    index_success=False
                                    index_audit_update(email_id, s3_source, s3_key, FILE_UPLOAD_STATUS._FAILURE, utc_now, response['errorMessage'])
                                    
                                # Read Image on Page
                                for image_file_object in page.images:
                                    # Extract through low cost LLM (Claude3-Haiku)
                                    ocr_prompt = generate_claude_3_ocr_prompt(image_file_object.data)
                                    text_value = query_bedrock(ocr_prompt, ocr_model_id)
                                    LOG.debug(f'method=process_file_upload, file_type=pdf-image, content={text_value}')
                                    response = generate_title_and_index_doc(event, page.page_number, text_value, s3_source, email_id)
                                    if 'statusCode' in response and response['statusCode'] != '200':
                                        LOG.error(f'Failed to index image on pdf {s3_key} on page {page.page_number}, error={response}')
                                        index_success=False
                                        index_audit_update(email_id, s3_source, s3_key, FILE_UPLOAD_STATUS._FAILURE, utc_now, response['errorMessage'])
        
                    elif file_extension.lower() in ['png', 'jpg']:
                        # Extract through low cost LLM (Claude3-Haiku)
                        LOG.debug(f'method=process_file_upload, message=File is an image, record={record}')
                        ocr_prompt = generate_claude_3_ocr_prompt(content)
                        text_value = query_bedrock(ocr_prompt, ocr_model_id)
                        LOG.debug(f'method=process_file_upload, file_type=image-text, content={text_value}')
                        response = generate_title_and_index_doc(event, 1, text_value, s3_source, email_id)
                        if 'statusCode' in response and response['statusCode'] != '200':
                            LOG.error(f'Failed to index image {s3_key}, error={response["errorMessage"]}')
                            index_success=False
                            index_audit_update(email_id, s3_source, s3_key, FILE_UPLOAD_STATUS._FAILURE, utc_now, response['errorMessage'])
                        
                    else:
                        decoded_txt = content.decode()
                        LOG.debug(f'method=process_file_upload, decoded_txt={decoded_txt}')
                        response = generate_title_and_index_doc(event, 1, decoded_txt, s3_source, email_id)
                        if 'statusCode' in response and response['statusCode'] != '200':
                            LOG.error(f'Failed to index file {s3_key}, error={response["errorMessage"]}')
                            index_success=False
                            index_audit_update(email_id, s3_source, s3_key, FILE_UPLOAD_STATUS._FAILURE, utc_now, response['errorMessage'])
                    
                    if index_success:
                        index_audit_update(email_id, s3_source, s3_key, FILE_UPLOAD_STATUS._SUCCESS, utc_now)
                except Exception as e:
                    LOG.error(f'Indexing failed for file {s3_source}, error={e}')
                    index_audit_update(email_id, s3_source, s3_key, FILE_UPLOAD_STATUS._FAILURE, utc_now)
            
            
            elif record['eventName'] == 'ObjectRemoved:Delete' and "index/" in record["s3"]["object"]["key"]:
                s3_source=''
                s3_key=''
                if 's3' in record:
                    s3_key = record['s3']['object']['key']
                    s3_bucket = record['s3']['bucket']['name']
                    s3_source = f'https://{s3_bucket}/{s3_key}'
                    LOG.info(f'Delete document from Index triggered for s3_key {s3_key}')
                    delete_documents_by_s3_uri(s3_source)
                       
    return success_response(f'File process complete for event {event}')

def generate_title_and_index_doc(event, page_number, text_value, s3_source, email_id):
    if text_value:
        if page_number <2:
            title_value = generate_title(text_value)
        text_value = f'Page Number: {page_number}, content: {text_value}'
        event['body'] = json.dumps({"text": text_value, "title": title_value, 's3_source': s3_source, 'email_id': email_id})
        response = index_documents(event)
        return response

 
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
    LOG.debug(f"method=query_bedrock, prompt={prompt}, model_id={model_id}, response={response_body}")
    return final_text


def get_file_from_s3(s3_key):
    s3_client = boto3.client('s3')
    
    response = s3_client.get_object(Bucket=s3_bucket_name, Key=s3_key)
    file_bytes = response['Body'].read()
    LOG.debug(f'method=get_file_from_s3,  bucket_key={s3_bucket_name}/{s3_key}, response={response}')
    return file_bytes, response['Metadata']

def get_file_attributes(s3_key):
    s3_client = boto3.client('s3')
    metadata = {}
    try:
        response = s3_client.head_object(
            Bucket=s3_bucket_name,
            Key=s3_key)
        LOG.info(f'method=get_file_attributes, bucket_key={s3_bucket_name}/{s3_key}, response={response}')
        if 'Metadata' in response:
            return response['Metadata']
        else:
            LOG.error(f'No metadata found for {s3_key}, response={response}')
    except Exception as e:
        LOG.error(f'Error getting metadata for {s3_key}, error={e}')
    return {}

def handler(event, context):
    LOG.info("---  Amazon Opensearch Serverless vector db example with Amazon Bedrock Models ---")
    LOG.info(f"--- Event {event} --")
    
    # This comes from S3 event notification
    if 'Records' in event:
            event['httpMethod']= 'POST'
            event['resource']='s3-upload-file'
    
    if 'httpMethod' in event:
        api_map = {
            'POST/rag/index-documents': lambda x: index_documents(x),
            'DELETE/rag/index-documents': lambda x: delete_index(x),
            'GET/rag/connect-tracker': lambda x: connect_tracker(x),
            'GET/rag/get-presigned-url': lambda x: create_presigned_post(x),
            'GET/rag/del-file': lambda x: delete_file(x),
            'GET/rag/get-indexed-files-by-user': lambda x: get_indexed_files_by_user(x),
            'POSTs3-upload-file': lambda x: process_file_upload(x),
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

# Store the indexing metadata information in a dynamodb table
# Triggered when a file is uploaded to S3
def index_audit_insert(email_id, s3_uri, file_id, utc_now, error_message='None'):
    LOG.info(f'method=index_audit_insert, email_id={email_id}, s3_uri={s3_uri}')
    record = {
        INDEX_KEYS._EMAIL_ID: email_id,
        INDEX_KEYS._S3_SOURCE: s3_uri,
        INDEX_KEYS._FILE_ID: file_id,
        INDEX_KEYS._UPLOAD_TIMESTAMP: utc_now,
        INDEX_KEYS._INDEX_TIMESTAMP: utc_now,
        INDEX_KEYS._UPLOAD_STATUS: FILE_UPLOAD_STATUS._INPROGRESS,
        INDEX_KEYS._ERROR_MESSAGE: error_message,
        INDEX_KEYS._UPDATE_EPOCH: int(time.time())
    }

    if all(key in record for key in ([INDEX_KEYS._EMAIL_ID, INDEX_KEYS._S3_SOURCE, INDEX_KEYS._FILE_ID, INDEX_KEYS._UPLOAD_TIMESTAMP, INDEX_KEYS._UPLOAD_STATUS])):
        try:
            record[INDEX_KEYS._PRIMARY_KEY]='INDEX'
            record[INDEX_KEYS._SORT_KEY]=generate_sort_key(record[INDEX_KEYS._EMAIL_ID], record[INDEX_KEYS._FILE_ID])
            table.put_item(Item=record)
        except Exception as e:
            LOG.error(f'error=failed_to_store_index_audit, error={e}, record={record}')
            return failure_response(f'Failed to store index audit {e}')
    else:
        LOG.error(f'failure=index_audit_insert, email_id={email_id}, s3_uri={s3_uri}, utc_now={utc_now}')
        return failure_response(f"Invalid input , required inputs - {INDEX_KEYS._EMAIL_ID, INDEX_KEYS._S3_SOURCE, INDEX_KEYS._FILE_ID, INDEX_KEYS._UPLOAD_TIMESTAMP, INDEX_KEYS._UPLOAD_STATUS}")
    LOG.info(f'success=index_audit_insert, email_id={email_id}, s3_uri={s3_uri}, utc_now={utc_now}')
    return success_response(f"Inserted index audit for email_id={email_id}, utc_now={utc_now}, file_id={file_id}")
    

def index_audit_update(email_id, s3_uri, file_id, file_index_status, utc_now, error_message="None"):
    LOG.info(f'method=index_audit_update, email_id={email_id}, s3_uri={s3_uri}, file_id={file_id}, index_status={file_index_status}, utc_now={utc_now}, error_message={error_message}')
    try:
        table.update_item(
                    Key={
                        INDEX_KEYS._PRIMARY_KEY: 'INDEX',
                        INDEX_KEYS._SORT_KEY: generate_sort_key(email_id, file_id)
                    },
                    UpdateExpression=f"set {INDEX_KEYS._UPLOAD_STATUS}=:s, {INDEX_KEYS._ERROR_MESSAGE}=:errm ",
                    ExpressionAttributeValues={
                        ':s': file_index_status,
                        ':errm': error_message
                    }
        )
    except Exception as e:
        LOG.error(f'error=failed_to_update_index_audit, email_id={email_id}, s3_uri={s3_uri}, utc_now={utc_now}, error={e}')
        return failure_response(f"Error updating dynamodb table, email_id={email_id}, utc_now={utc_now}, file_id={file_id}, error={e}")
    return success_response(f"Updated index audit for email_id={email_id}, utc_now={utc_now}, file_id={file_id}")


def get_indexed_files_by_user(event):
    query_params = {}
    if 'queryStringParameters' in event:
        query_params = event['queryStringParameters']
    if 'requestContext' in event and 'authorizer' in event['requestContext']:
            if 'claims' in event['requestContext']['authorizer']:
                email_id = event['requestContext']['authorizer']['claims']['email']
                LOG.info(f'method=get_indexed_files_by_user, user_id={email_id}')
                try:
                    response = table.query(
                        KeyConditionExpression=Key(INDEX_KEYS._PRIMARY_KEY).eq('INDEX') 
                                    & Key(INDEX_KEYS._SORT_KEY)\
                                    .begins_with(get_sort_key_beginswith_user_id(email_id)),
                        ScanIndexForward=False
                    )
                
                    items = response['Items']
                    while 'LastEvaluatedKey' in response:
                        response = table.query(ExclusiveStartKey=response['LastEvaluatedKey'])
                        items.extend(response['Items'])
                    return success_response(items)
                except Exception as e:
                    LOG.error(f'error=failed_to_get_indexed_files_by_user, error={e}, user_id={email_id}')
                    return failure_response(f'Failed to get indexed files for user {email_id}')
    else:
        return failure_response(f'Unauthorized request. Email_id not found')
    
    
def get_sort_key_beginswith_user_id(email_id):
    return f'user-{email_id}-'

def generate_sort_key(user_id, file_id):
    return f'user-{user_id}-fileid-{file_id}'

def sanitize_s3_key(s3_key):
    s3_key
    return s3_key.replace('/', '')
def now_utc_iso8601():
    return datetime.utcnow().isoformat()[:-3] + 'Z'

class INDEX_KEYS():
    _PRIMARY_KEY: str = 'prim_key'
    _SORT_KEY: str = 'sort_key'
    _EMAIL_ID: str = 'email_id'
    _S3_SOURCE: str = 's3_source'
    _FILE_ID: str = 'file_id'
    _UPLOAD_TIMESTAMP: str = 'upload_timestamp'
    _INDEX_TIMESTAMP: str = 'index_timestamp'
    _UPDATE_EPOCH: str = 'update_epoch'
    _UPLOAD_STATUS: str = 'file_index_status'
    _ERROR_MESSAGE: str = 'idx_err_msg'

class FILE_UPLOAD_STATUS():
    _SUCCESS: str = 'success_index_create'
    _INPROGRESS: str = 'inprogress'
    _FAILURE: str = 'failure'
    _DELETED: str = 'success_file_delete'
    _INDEX_DELETE: str = 'success_index_delete'

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