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

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
# http endpoint for your cluster (opensearch required for vector index usage)
# Self managed or cluster based OPENSEARCH
endpoint = getenv("OPENSEARCH_VECTOR_ENDPOINT", "https://admin:P@@search-opsearch-public-24k5tlpsu5whuqmengkfpeypqu.us-east-1.es.amazonaws.com:443")
SAMPLE_DATA_DIR=getenv("SAMPLE_DATA_DIR", "sample_data")
INDEX_NAME = getenv("VECTOR_INDEX_NAME", "sample-embeddings-store-dev")
s3_bucket_name = getenv("S3_BUCKET_NAME", "S3_BUCKET_NAME_MISSING")
embed_model_id = getenv("EMBED_MODEL_ID", "amazon.titan-embed-image-v1")

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
        res = ops_client.indices.create(index=INDEX_NAME, body=settings, ignore=[400])
        print(res)

def index_documents(event):
    print(f'In index documents {event}')
    payload = json.loads(event['body'])
    text_val = payload['text']

    text_splitter = RecursiveCharacterTextSplitter(
    # Set a really small chunk size, just to show.
    chunk_size = 1000,
    chunk_overlap  = 50)

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
            'timestamp': datetime.today().replace(tzinfo=timezone.utc).isoformat()
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


def create_presigned_post(event):
    # Generate a presigned S3 POST URL
    query_params = {}
    if 'queryStringParameters' in event:
        query_params = event['queryStringParameters']
    
    if 'file_extension' in query_params:
        extension = query_params['file_extension']
        session = boto3.Session()
        s3_client = session.client('s3', region_name=region)

        # s3_client = boto3.client('s3')
        now = datetime.now()
        date_time = now.strftime("%Y-%m-%d-%H-%M-%S")
        s3_key = f"index/data/{date_time}.{extension}"
        response = s3_client.generate_presigned_post(Bucket=s3_bucket_name,
                                              Key=s3_key,
                                              Fields=None,
                                              Conditions=[]
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

def get_job_status(event):
    query_params = {}
    
    if 'queryStringParameters' in event:
        query_params = event['queryStringParameters']
    if all(key in query_params for key in (['jobId'])):
        return success_response(isJobCompleted(query_params['jobId']))
    else:
        return failure_response('jobId is missing')
    
def detect_text_index(event):
    payload = json.loads(event['body'])
    s3_key = payload['s3_key']
    file_extension = 'txt'
    if '.' in s3_key:
        file_extension = s3_key[s3_key.rindex('.')+1:]
    
    if file_extension.lower() in ['pdf']:
            job_id = start_pdf_text_detection_job(s3_key)
            # t1 = threading.Thread(target=async_indexing(file_extension, event, job_id))
            return success_response({'jobId': job_id})
    else:
        content = get_contents(file_extension, get_file_from_s3(s3_key), None)
        event['body'] = json.dumps({"text": content})
        # Directly index as the content is readable through normal decoding
        # TODO Integrate wrangler for xls files
        return index_documents(event)


def get_file_from_s3(s3_key):
    s3 = boto3.resource('s3')
    obj = s3.Object(s3_bucket_name, s3_key)
    file_bytes = obj.get()['Body'].read()
    print(f'returns S3 encoded object from key {s3_bucket_name}/{s3_key}')
    return file_bytes


def index_file_in_aoss(event):
    '''
    This function is called for PDF files which passed through Textract
    Once the PDF job is complete we retrieve the contents based on JobID
    and initiate the indexing
    '''
    payload = json.loads(event['body'])
    jobId = payload['jobId']
    content = get_contents('pdf', None, None, jobId)
    event['body'] = json.dumps({"text": content})
    print('Asynchronous Indexing of data')
    return index_documents(event)

# def async_indexing(file_extension, event, job_id):
#     content = get_contents(file_extension, None, None, job_id)
#     event['body'] = json.dumps({"text": content})
#     print('Asynchronous Indexing of data')
#     return index_documents(event)

def getJobResults(jobId):

    pages = []
    response = textract_client.get_document_text_detection(JobId=jobId)
    
    pages.append(response)
    print("Resultset page recieved: {}".format(len(pages)))
    nextToken = None
    if('NextToken' in response):
        nextToken = response['NextToken']

    while(nextToken):
        response = textract_client.get_document_text_detection(JobId=jobId, NextToken=nextToken)

        pages.append(response)
        print("Resultset page recieved: {}".format(len(pages)))
        nextToken = None
        if('NextToken' in response):
            nextToken = response['NextToken']
    return pages

def isJobCompleted(jobId):
    response = textract_client.get_document_text_detection(JobId=jobId)
    status = response["JobStatus"]
    print("Job status: {}".format(status))
    return True if status == "SUCCEEDED" else False
    

def isJobComplete(jobId):
    response = textract_client.get_document_text_detection(JobId=jobId)
    status = response["JobStatus"]
    print("Job status: {}".format(status))

    while(status == "IN_PROGRESS"):
        time.sleep(3)
        response = textract_client.get_document_text_detection(JobId=jobId)
        status = response["JobStatus"]
        print("Job status: {}".format(status))

    return status

def startJob(s3BucketName, objectName):
    response = None
    response = textract_client.start_document_text_detection(
    DocumentLocation={
        'S3Object': {
            'Bucket': s3BucketName,
            'Name': objectName
        }
    })

    return response["JobId"]

def start_pdf_text_detection_job(s3_key):
    jobId = startJob(s3_bucket_name, s3_key)
    print("Started job with id: {}".format(jobId))
    return jobId

def get_contents(file_extension: str, file_bytes=None, s3_key=None, jobId=None):
    content = ' '
    try:
        if file_extension.lower() in ['pdf']:
            if(isJobComplete(jobId)):
                response = getJobResults(jobId)
                # Print detected text
                for resultPage in response:
                    for item in resultPage["Blocks"]:
                        if item["BlockType"] == "LINE":
                            content = content + ' ' + item["Text"]
        elif file_extension.lower() in ['png', 'jpg', 'jpeg']:
            response = textract_client.detect_document_text(Document={'Bytes': file_bytes})
            for block in response['Blocks']:
                if block['BlockType'] == 'LINE':
                    content = content + ' ' + block['Text']
        else: 
            content = file_bytes.decode()
    except Exception as e:
        print(f'Exception reading contents from file {e}')
    # print(f'file-content {content}')
    return content



    pass
def handler(event, context):
    LOG.info("---  Amazon Opensearch Serverless vector db example with Amazon Bedrock Models ---")

    api_map = {
        'POST/rag/index-sample-data': lambda x: index_sample_data(x),
        'POST/rag/index-documents': lambda x: index_documents(x),
        'DELETE/rag/index-documents': lambda x: delete_index(x),
        'GET/rag/connect-tracker': lambda x: connect_tracker(x),
        'POST/rag/detect-text': lambda x: detect_text_index(x),
        'POST/rag/index-files': lambda x: index_file_in_aoss(x),
        'GET/rag/get-presigned-url': lambda x: create_presigned_post(x),
        'GET/rag/get-job-status': lambda x: get_job_status(x)
        
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