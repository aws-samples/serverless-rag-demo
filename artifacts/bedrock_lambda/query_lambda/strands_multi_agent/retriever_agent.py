import boto3
from os import getenv
from opensearchpy import OpenSearch, RequestsHttpConnection, exceptions
from requests_aws4auth import AWS4Auth
from requests.auth import HTTPBasicAuth
import json
from decimal import Decimal
import logging
import datetime
import requests

import json

from datetime import datetime, timedelta
from strands import Agent, tool
from agent_executor_utils import bedrockModel

date = datetime.now()
next_date = datetime.now() + timedelta(days=30)
year = date.year
month = date.month
month_label = date.strftime('%B')
next_month_label = next_date.strftime('%B')
day = date.day

endpoint = getenv("OPENSEARCH_VECTOR_ENDPOINT", "https://admin:P@@search-opsearch-public-24k5tlpsu5whuqmengkfpeypqu.us-east-1.es.amazonaws.com:443")
credentials = boto3.Session().get_credentials()
service = 'aoss'
region = getenv("REGION", "us-east-1")
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key,
                   region, service, session_token=credentials.token)
embed_model_id = getenv("EMBED_MODEL_ID", "amazon.titan-embed-image-v1")
INDEX_NAME = getenv("VECTOR_INDEX_NAME", "sample-embeddings-store-dev")
is_bedrock_kb = getenv("IS_BEDROCK_KB", "no")
bedrock_embedding_key_name = getenv("BEDROCK_KB_EMBEDDING_KEY", "bedrock-knowledge-base-default-vector")
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
bedrock_client = boto3.client('bedrock-runtime')

ops_client = client = OpenSearch(
        hosts=[{'host': endpoint, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
)

RETRIEVER_SYSTEM_PROMPT = """

You are a helpful retriever agent. You will use the tools to retrieve information from the knowledge base.

Key Responsibilities:
- Use the tools to retrieve information from the knowledge base
- Use the tools to rewrite the user query
- Use the tools to classify the user query
- Use the tools to fetch data from the knowledge base

General Instructions:
- Use only the following tools:
    - query_translation: To translate the user query into english if its in any other language
    - query_rewrite: To rewrite the user query to be more relevant to the knowledge base
    - fetch_data: To fetch data from the knowledge base. This tool needs the user query and the proper nouns in the user query and also if we should do a hybrid search or not.

"""


@tool
def retriever_agent(user_query):
    agent = Agent(system_prompt=RETRIEVER_SYSTEM_PROMPT, model=bedrockModel, tools=[query_translation, query_rewrite, fetch_data])
    agent_response = agent(user_query)
    return agent_response

# As our knowledge base is in English. We should translate the user query into english if its in any other language
@tool
def query_translation(user_query):
    print(f'In Query Translation = {user_query}')
    
    QUERY_TRANSLATION_SYSTEM_PROMPT = """
    You are a helpful query translator. You will translate the user query into english if its in any other language
    It should not contain any other tags or text in the response.
    """

    agent = Agent(system_prompt=QUERY_TRANSLATION_SYSTEM_PROMPT, model=bedrockModel, tools=[])
    agent_response = agent(user_query)
    return agent_response

@tool
def query_rewrite(user_query):
     # rewrite the user query to be more relevant to the knowledge base
     # Step back prompting technique
    print(f'In Query Rewrite = {user_query}')
    QUERY_REWRITE_SYSTEM_PROMPT = f"""
                        You are a query rewriter. Your task is to step back and paraphrase a question to a more generic 
                        step-back question, which is easier to answer. Remember todays year is {year} and the month is {month_label}
                        and day is {day}.
                        Use this information to rewrite the user query to be more relevant to the knowledge base.

                        Example 1:
                        Orginal query : Amazon earnings

                        Rewritten query
                        What are the Amazon earnings over the last 5 years from {year - 5} to {year}?

                        Example 3:
                        Orginal query : Who is the Amazon CEO?
                        Rewritten query : Who are all the CEO's in Amazon
                        
                """

    agent = Agent(system_prompt=QUERY_REWRITE_SYSTEM_PROMPT, model=bedrockModel, tools=[])
    agent_response = agent(user_query)
    return agent_response


# Here we combine the results of Keyword and Semantic search to produce better results
@tool
def fetch_data(user_query, proper_nouns: list, is_hybrid=False):
    global INDEX_NAME
    nearest_neighbours = 10
    result_set_size = 20
    print(f'In Fetch Data = {user_query}')
    context = ''
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
    if 'cohere' in   embed_model_id:
         embedded_search = result.get(embeddings_key)[0]
    else:
        embedded_search = result.get(embeddings_key)
    
    TEXT_CHUNK_FIELD = 'text'
    if is_bedrock_kb == 'yes':
        TEXT_CHUNK_FIELD="AMAZON_BEDROCK_TEXT_CHUNK"
    
    DOC_TYPE_FIELD = 'doc_type'
    vector_query = {
                "size": result_set_size,
                "query": {
                            "bool": {
                                "must": [
                                    {
                                        "knn": {"embedding": {"vector": embedded_search, "k": nearest_neighbours}}              
                                    }     
                                ]
                            }
                        },
                "track_scores": True, 
                "_source": False,
                "fields": [TEXT_CHUNK_FIELD, DOC_TYPE_FIELD]
    }
    
    if is_bedrock_kb == 'yes':
        LOG.info('Connecting to Bedrock KB')
        if not INDEX_NAME.startswith('bedrock'):
            INDEX_NAME = 'bedrock-knowledge-base*'
            vector_query = {
                "size": result_set_size,
                "query":{
                            "bool": {
                                "must": [
                                    {
                                        "knn": {bedrock_embedding_key_name: {"vector": embedded_search, "k": nearest_neighbours}}
                                    }
                                ]
                            }
                        },
                "track_scores": True,    
                "_source": False,
                "fields": [TEXT_CHUNK_FIELD]
            }

    keyword_results = []
    
    # Common for both Bedrock and non-Bedrock collections
    if is_hybrid and len(proper_nouns) > 0:
        # Default operator is OR. To narrow the scope you could change it to 'AND'
        # "minimum_should_match": len(proper_nouns)-1
        # fuzziness handle spelling erros in the query
        KEYWORD_SEARCH = {
            "match": { 
                TEXT_CHUNK_FIELD: { "query": " ".join(proper_nouns), "operator": "or", "analyzer": "english",
                    "fuzziness": "AUTO", "auto_generate_synonyms_phrase_query": False, "zero_terms_query": "all"} 
                }
        }
        
        keyword_search_query = {
                "size": result_set_size,
                "query":{
                            "bool": {
                                "must": [
                                    KEYWORD_SEARCH
                                ]
                            }
                        },
                "track_scores": True,    
                "_source": False,
                "fields": [TEXT_CHUNK_FIELD]
        }
        LOG.info(f'AOSS Keyword search Query {keyword_search_query}')

        
        try:
            response = ops_client.search(body=keyword_search_query, index=INDEX_NAME)
            LOG.info(f'Opensearch response {response}')
            keyword_results.extend(response["hits"]["hits"])
        except Exception as e:
            LOG.error(f'Keyword search query error {e}')
    else:
        # When its just semantic search increase the result set size
        result_set_size=50
        vector_query['size']=result_set_size
        
    LOG.info(f'AOSS Vector search Query {vector_query}')
    semantic_results = []
        
    try:
        response = ops_client.search(body=vector_query, index=INDEX_NAME)
        LOG.info(f'Opensearch response {response}')
        semantic_results.extend(response["hits"]["hits"])
    except Exception as e:
                LOG.error(f'Vector Index query error {e}')
    
    all_results = keyword_results + semantic_results
    all_results = sorted(all_results, key=lambda x: x['_score'], reverse=True)
    for data in all_results:
        if context == '':
            context = data['fields'][TEXT_CHUNK_FIELD][0]
        else:
            context += data['fields'][TEXT_CHUNK_FIELD][0] + ' '

    return context.strip()


# if __name__ == "__main__":
#     print(retriever_agent(" Kya hai captial France Ka batao ?"))