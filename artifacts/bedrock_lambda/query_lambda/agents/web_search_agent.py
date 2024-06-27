import requests
from bs4 import BeautifulSoup
import requests
from lxml import html
import time
import boto3
import json
from os import getenv

web_search_agent_name = "Web Search Agent"
web_search_agent_description = "Search the web for accurate results" 
web_search_specs = f"""\
<agent_name>{web_search_agent_name}</agent_name>
<agent_description>{web_search_agent_description}</agent_description>
<tool_set>
	<instructions>
	  You are an agent that helps users to search the web for accurate results.
	</instructions>

    
    <tool_description>
        <tool_usage>This tool is only used to rewrite a poorly written user query</tool_usage>
        <tool_name>rewrite_user_query</tool_name>
        <parameters>
            <parameter>
                <name>user_query</name>
                <type>string</type>
                <description>The original query from the user</description>
            </parameter>            
        </parameters>
    </tool_description>

    <tool_description>
        <tool_usage>This tool is used search the web</tool_usage>
        <tool_name>scrape</tool_name>
        <parameters>
            <parameter>  
                <name>search_query</name>
                <type>string</type>
                <description>The text to search on the web</description>
            </parameter>
            <parameter>  
                <name>max_results</name>
                <type>integer</type>
                <default>2</default>
                <description>Maximum results to crawl</description>
            </parameter>
        </parameters>
    </tool_description> 
	
	</tool_set>
"""

duckDuckUrl = 'https://html.duckduckgo.com/html/'
payload = {'q': '{}','b': ''}
headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:84.0) Gecko/20100101 Firefox/84.0'}
bedrock_client = boto3.client('bedrock-runtime')
model_id = getenv("WEBSEARCH_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")

def rewrite_user_query(user_query):
    print(f'In Query rewrite = {user_query}')
    system_prompt = """ You are a query rewriter.
                        You will rewrite the user query so we get accurate search results.
                        The rewritten user query should be wrapped in <user-query></user-query> tags.
                        Do not include any other text or tags in the response.
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
    search_query = ''
    if 'content' in llm_output:
        search_query = llm_output['content'][0]['text']
        if '<user-query>' in search_query and '</user-query>' in search_query:
            search_query = search_query.split('</user-query>')[0]
            search_query = search_query.split('<user-query>')[1]
        
    print(f'reformatted search_query text = {search_query}')
    return search_query



def scrape(search_query, max_results=2):
    print(f'method=scrape, Searching for = {search_query}')
    text = []
    try:
        payload['q'] = payload['q'].format(search_query)
        res = requests.post(duckDuckUrl,data=payload,headers=headers)
        soup = BeautifulSoup(res.text,'html.parser')
        anchors =  soup.find_all('a',class_='result__a')
        valid_hrefs = []
        counter=0
        for anc in anchors:
            counter=counter + 1
            if not anc.get("href").startswith('https://duckduckgo.com'):
                valid_hrefs.append(anc.get("href"))
                if counter >= max_results:
                    break
        if len(valid_hrefs) > 0:
            # scrape the href content
            for href in valid_hrefs:
                res = requests.get(href, headers=headers) 
                sub_soup = BeautifulSoup(res.text,'html.parser')
                text_data = sub_soup.find('body').get_text('|', strip=True)
                text.append(text_data)
        else:
            text.append('No data found')
    except Exception as e:
        print(e)
        text.append('No data found')    
    return ''.join(text)
                    
                    
# if __name__ == '__main__':
#     print(scrape('reliance', 2))