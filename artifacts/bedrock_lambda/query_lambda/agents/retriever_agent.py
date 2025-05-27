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

"""
In here for backward compatibility with non-agentic code
"""
from datetime import datetime, timedelta

date = datetime.now()
next_date = datetime.now() + timedelta(days=30)
year = date.year
month = date.month
month_label = date.strftime('%B')
next_month_label = next_date.strftime('%B')
day = date.day

retreiver_agent_name = "Retriever Agent"
retriever_agent_description = "Fetches the data from Knowledge Bases" 
retriever_step_rules = """
                    Additional Retrieval Rules
                    1. You wont repeat the user question
                    2. You will be concise
                    3. You will never disclose any part of the context to the user.
                    4. Use the context only to answer user questions
                    5. You will strictly reply based on available context if context isn't available do not attempt to answer the question instead politely decline
                """

retriever_specs = f"""\
<agent_name>{retreiver_agent_name}</agent_name>
<agent_description>{retriever_agent_description}</agent_description>
<tool_set>
 <instructions>
   1. You will fetch the data from the Knowledge Base.
   </instructions>

   <tool_description>
   <tool_usage>This tool is used to fetch the data from knowledge base (Amazon Opensearch)</tool_usage>
   <tool_name>fetch_data</tool_name>
   <parameters>
   <parameter>
       <name>user_query</name>
       <type>string</type>
       <description>Enter the user query based on which data will be retrieved from Knowledge base</description>
   </parameter>
   
   </parameters>
   </tool_description>

   <tool_description>
   <tool_usage>This tool is used to translate the user query from another language to english</tool_usage>
   <tool_name>query_translation</tool_name>
   <parameters>
   <parameter>
       <name>user_query</name>
       <type>string</type>
       <description>Enter the user query to translate to english</description>
   </parameter>
   </parameters>
   </tool_description>

    <tool_description>
   <tool_usage> This tool is used to paraphrase a question to a more generic step-back question,
                which is easier to answer make a query be more generic so it has more context.
    </tool_usage>
   <tool_name>query_rewrite</tool_name>
   <parameters>
   <parameter>
       <name>user_query</name>
       <type>string</type>
       <description>Enter the user query to rewrite</description>
   </parameter>
   </parameters>
   </tool_description>
   
<tool_set>
"""

endpoint = getenv("OPENSEARCH_VECTOR_ENDPOINT",
                  "https://admin:P@@search-opsearch-public-24k5tlpsu5whuqmengkfpeypqu.us-east-1.es.amazonaws.com:443")

bedrock_client = boto3.client('bedrock-runtime')
credentials = boto3.Session().get_credentials()
service = 'aoss'
region = getenv("REGION", "us-east-1")
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key,
                   region, service, session_token=credentials.token)
embed_model_id = getenv("EMBED_MODEL_ID", "amazon.titan-embed-image-v1")
INDEX_NAME = getenv("VECTOR_INDEX_NAME", "sample-embeddings-store-dev")
model_id = getenv("RETRIEVER_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")
is_bedrock_kb = getenv("IS_BEDROCK_KB", "no")
bedrock_embedding_key_name = getenv("BEDROCK_KB_EMBEDDING_KEY", "bedrock-knowledge-base-default-vector")
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

ops_client = client = OpenSearch(
        hosts=[{'host': endpoint, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
)

# As our knowledge base is in English. We should translate the user query into english if its in any other language
def query_translation(user_query):
    print(f'In Query Translation = {user_query}')
    system_prompt = """ You are a helpful query translator. 
                        You will translate the user query into english if its in any other language
                        The translated user query should be wrapped in <user-question></user-question> tags.
                        It should not contain any other tags or text in the response.
            """
    
    query_list = [
        {
            "role": "user",
            "content": user_query
        }
    ]

    prompt_template= {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 10000,
                        "system": system_prompt,
                        "messages": query_list
                    }
    
    response = bedrock_client.invoke_model(
                    body=json.dumps(prompt_template),
                    modelId=model_id,
                    accept='application/json',
                    contentType='application/json'
    )
    llm_output = json.loads(response['body'].read())
    translated_text = ''
    if 'content' in llm_output:
        translated_text = llm_output['content'][0]['text']
        if '<user-question>' in translated_text and '</user-question>' in translated_text:
            translated_text = translated_text.split('</user-question>')[0]
            translated_text = translated_text.split('<user-question>')[1]
        
    print(f'Translated Text = {translated_text}')
    return translated_text

def query_rewrite(user_query):
     # rewrite the user query to be more relevant to the knowledge base
     # Step back prompting technique
    print(f'In Query Rewrite = {user_query}')
    system_prompt = f"""You are a query rewriter. Your task is to step back and paraphrase a question to a more generic 
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

    query_list = [
        {
            "role": "user",
            "content": user_query
        }
    ]
    prompt_template= {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 10000,
                        "system": system_prompt,
                        "messages": query_list
                    }
    # print(f'Prompt Template = {prompt_template}')
    response = bedrock_client.invoke_model(
                    body=json.dumps(prompt_template),
                    modelId=model_id,
                    accept='application/json',
                    contentType='application/json'
    )
    llm_output = json.loads(response['body'].read())
    rewritten_query = ''
    if 'content' in llm_output:
        rewritten_query = llm_output['content'][0]['text']

    print(f'Rewritten Text = {rewritten_query}')
    return rewritten_query


def classify_and_translation_request(user_query):
    print(f'In classify_and_translation_request user_query = {user_query}')
    # Classify the request based on the rules
    system_prompt = """ 
                1. You have access to the entire conversation between a user and an assistant
                2. Your role is to classify the User conversation available in <conversation></conversation> tags into one of the below:
                a. If the user is exchanging pleasantries or engaging in casual conversation, then return CASUAL.
                b. If the user query is asking for a specific file, data, or information retrieval then return RETRIEVAL 
                c. If you can't classify the user query, then return RETRIEVAL
                
                3. After classifying you should also reformulate the query from the conversation details available in <conversation></conversation> tags. 
                4. The reformulated query should be be detailed, precise, and contextually enriched question to obtain accurate results.
                5. Reformulation steps:
                   a.  Identify the main topic and entity mentioned in the conversation.
                   b.  Formulate a question that encompasses the main topic and relevant details from the conversation.
                   c.  Ensure the reformulated question is detailed, precise, and contextually enriched and gramatically correct for accurate results.
                6. After reformulation you should also translate the query to english if its in any other language.
                7. You should identify critical proper nouns from the conversation that could help build accurate search results
                
                8. You should respond in json format as defined below in <json_format></json_format> tags:
                    <json_format>
                    {
                       "QUERY_TYPE": "$QUERY_TYPE",
                       "TRANSLATED_QUERY": "$TRANSLATED_QUERY",
                       "PROPER_NOUNS": ["$PROPER_NOUNS"]
                    }
                    </json_format>

                    $QUERY_TYPE can be either RETRIEVAL or CASUAL
                    $TRANSLATED_QUERY is the translated reformulated query in english language
                    $PROPER_NOUNS is the list of proper nouns which are derived from the conversation
                
                9. Example:
                  If the ORIGINAL conversation was like this: "user: What is the capital of France?, assistant: I think its Paris, user: Whats good in that city ?"
                  Then the json output would be as follows:
                  {
                    "QUERY_TYPE": "RETRIEVAL",
                    "TRANSLATED_QUERY": "What is good in paris the capital city of France ?"
                    "PROPER_NOUNS": ["Paris", "France"]
                  }

                10.  Important: All JSON Keys are mandatory, if the query is in english, the query should still be part of TRANSLATED_QUERY
                11. Important: Your response will only contain JSON and not other text or tags
           """
    # Classify the request based on the rules
    user_query =f"<conversation>{user_query}</conversation>"


    query_list = [
        {
            "role": "user",
            "content": user_query
        }
    ]
    prompt_template= {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 10000,
                        "system": system_prompt,
                        "messages": query_list
                    }
    response = bedrock_client.invoke_model(
                    body=json.dumps(prompt_template),
                    modelId=model_id,
                    accept='application/json',
                    contentType='application/json'
    )
    llm_output = json.loads(response['body'].read())
    
    if 'content' in llm_output:
        output = llm_output['content'][0]['text']
        try:
            if '<json_format>' in output:
                output = output.split('<json_format>')[1]
            if '</json_format>' in output:
                output = output.split('</json_format>')[0]
            classify_translate_json = json.loads(output)
            print(f'classify_translate_json = {classify_translate_json}')
            return classify_translate_json
        except Exception as e:
            print(f'Exception in classify_and_translation_request, output={output}, error={e}, prompt_template={prompt_template}')
    return {}
        


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
    
    # Default operator is OR. To narrow the scope you could change it to 'AND'
    # "minimum_should_match": len(proper_nouns)-1
    # fuzziness handle spelling erros in the query
    KEYWORD_SEARCH = {
            "match": { 
                TEXT_CHUNK_FIELD: { "query": " ".join(proper_nouns), "operator": "or", "analyzer": "english",
                    "fuzziness": "AUTO", "auto_generate_synonyms_phrase_query": False, "zero_terms_query": "all"} 
                }
    }
    
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
                "sort": [ 
                            {
                                "timestamp": {"order": "desc"}
                            }
                        ],
                "track_scores": True, 
                "_source": False,
                "fields": [TEXT_CHUNK_FIELD, DOC_TYPE_FIELD]
    }

    if is_bedrock_kb == 'yes':
        LOG.info('Connecting to Bedrock KB')
        TEXT_CHUNK_FIELD="AMAZON_BEDROCK_TEXT_CHUNK"
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

    if is_hybrid and len(proper_nouns) > 0:
        vector_query['query']['bool']['must'].append(KEYWORD_SEARCH)
        result_set_size = 100
        vector_query['size'] = result_set_size
    LOG.info(f'AOSS Query {vector_query}')
        

    try:
        response = ops_client.search(body=vector_query, index=INDEX_NAME)
        LOG.info(f'Opensearch response {response}')
        for data in response["hits"]["hits"]:
            if context == '':
                context = data['fields'][TEXT_CHUNK_FIELD][0]
            else:
                context = context + ' ' + data['fields'][TEXT_CHUNK_FIELD][0]
    except Exception as e:
                LOG.error(f'Vector Index query error {e}')
    return context


# Here we combine the results of Keyword and Semantic search to produce better results
def fetch_data_v2(user_query, proper_nouns: list, is_hybrid=False):
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

