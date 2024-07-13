import requests
from bs4 import BeautifulSoup
import requests
from lxml import html
import time
import boto3
import json
from os import getenv
import boto3
import logging
from datetime import datetime, timedelta
from agent_executor_utils import agent_executor


#Begin: Needed by Master orchestrator
ws_agent_name = "Web Search Agent"
# Agent success criteria
ws_agent_stop_conditions = f"This {ws_agent_name} successfully returns summarized results from the web"
# When to use this agent
ws_agent_uses = f""" 
Use the {ws_agent_name} if:
   1. You dont have details about what the user is asking
   2. The question asked by the user is complex
If the user query is seeking additional information then use the {ws_agent_name} to answer the question
"""
# Agent use examples
ws_agent_use_examples = f"""
Is APPL a buy then use the {ws_agent_name}
Is AMZ a buy then use the {ws_agent_name}
Is NVDA a buy then use the {ws_agent_name}     
"""
# Agent Tool information
web_search_specs = f"""\
<agent_name>{ws_agent_name}</agent_name>
<tool_set>
	<instructions>
	  You are an agent that helps users to search the web for accurate results.
      Web Search Agent Rules:
           a. Web Search agent is expensive and should be used as last resort only, if other agents cant satisfy the user question
           b. Clarify the search query if you are not sure about it, before searching the web
           c. Trusted sites for stocks, financial analysis, investing, economics, trading, and forex are:
                https://www.nasdaq.com/
                https://www.moneycontrol.com/
                https://in.investing.com/
    </instructions>
    <tool_description>
        <tool_usage>This tool is used search the web</tool_usage>
        <tool_name>scrape</tool_name>
        <parameters>
            <parameter>  
                <name>chat_history</name>
                <type>string</type>
                <description>The entire chat_history</description>
            </parameter>
        </parameters>
    </tool_description> 
	
	</tool_set>
"""

#End: Needed by Master orchestrator

date = datetime.now()
next_date = datetime.now() + timedelta(days=30)
year = date.year
month = date.month
month_label = date.strftime('%B')
next_month_label = next_date.strftime('%B')
day = date.day


bedrock_client = boto3.client('bedrock-runtime')
credentials = boto3.Session().get_credentials()
service = 'aoss'
region = getenv("REGION", "us-east-1")
model_id = getenv("SUMMARIZER_CONVERSATION_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

duckDuckUrl = 'https://html.duckduckgo.com/html/'
payload = {'q': '{}','b': ''}
headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:84.0) Gecko/20100101 Firefox/84.0'}
bedrock_client = boto3.client('bedrock-runtime')
model_id = getenv("WEBSEARCH_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")

def rewrite_user_query(chat_history):
    print(f'In Query rewrite = {chat_history}')
    system_prompt = f""" You are a query rewriter. Given a user query, Your task is to step back and paraphrase a question to a more generic 
                        step-back question, which is easier to answer. 
                        Remember todays year is {year} and the month is {month_label} and day is {day}.
                        <instructions>
                        The entire chat history is provided to you
                        you should identify the user query from the provided chat history
                        You should then rewrite the user query so we get accurate search results.
                        The rewritten user query should be wrapped in <user-query></user-query> tags.
                        Do not include any other text or tags in the response.
                        </instructions>
                        """
    
    search_query = agent_executor(system_prompt, json.loads(chat_history), "rewritten user query", "<user-query></user-query>", False)
    print(f'reformatted search_query text = {search_query}')
    return search_query



def scrape(chat_history, max_results=10):
    print(f'method=scrape, Searching for = {chat_history}')
    search_query = rewrite_user_query(chat_history)
    text = []
    text.append('<web_search_results>')
    try:
        payload['q'] = payload['q'].format(search_query)
        res = requests.post(duckDuckUrl,data=payload,headers=headers)
        soup = BeautifulSoup(res.text,'html.parser')
        anchors =  soup.find_all('a')
        valid_hrefs = []
        counter=0
        for anc in anchors:
            v_href = anc.get("href")
            if v_href:
                counter=counter + 1
                if not (v_href.startswith('https://duckduckgo.com') or v_href.endswith('.pdf')) \
                    and v_href.startswith('https://'):
                # TODO Get rid of this or make it generic
                # A hack for NSE (as it needs javascript)
                    if 'nseindia' in v_href:
                        if '?' in v_href:
                            q = v_href.split('?')[1]
                            #Add valid hrefs here
                            valid_hrefs.append(f"https://www.nseindia.com/api/equity-meta-info?{q}")
                            valid_hrefs.append(f"https://www.nseindia.com/api/quote-equity?{q}")
                            valid_hrefs.append(f"https://www.nseindia.com/api/quote-equity?{q}")
                        else:
                            valid_hrefs.append("https://www.nseindia.com/api/marketStatus")
                    else:
                        valid_hrefs.append(v_href)
                    if counter >= int(max_results):
                        break
        
        print(f'Valid Links {valid_hrefs}')
        counter=0
        if len(valid_hrefs) > 0:
            # scrape the href content
            for href in valid_hrefs:
                if counter > 4:
                    print('Exit scrapping, we have enough results to proceed')
                    break
                counter = counter + 1
                print(f'Begin scrape, href = {href}')
                try:
                    res = requests.get(href, headers=headers, timeout=5) 
                    print(f'Finish scrape, href = {href}')
                    sub_soup = BeautifulSoup(res.text,'html.parser')
                    text_data = sub_soup.find('body').get_text('|', strip=True)
                    text.append(text_data)
                except requests.exceptions.Timeout:
                    print(f'scrape timed out after 5 seconds, href = {href}')
                
        else:
            text.append('No data found')
    except Exception as e:
        print(e)
        text.append('No data found')    
    text.append('</web_search_results>')

    print(f'Websearch output {text}')
    return summarize_search_results(''.join(text), search_query)


def summarize_search_results(search_data, user_query):
    system_prompt = f""" You are a search results summarizer. Given the search results and a user query,
                        Your task is to provide a concise summary of the search results based on the user query.
                        Remember todays year is {year} and the month is {month_label} and day is {day}.
                        The summary should be no more than 10 sentences.
                        Do not include any other text or tags in the response.
                        The Search results are available in the <web_search_results> tags.
                        Your summarized output should be placed within the <summarize> tags
                        """
    query_list = [
        {
            "role": "user",
            "content": [{"type": "text", "text": search_data},
                        {"type": "text", "text": user_query}
                        ]
        }
    ]
    summarized = agent_executor(system_prompt, query_list, "Summarized Search Results", "<web_search_results></web_search_results>", False)
    return f'<web_search_results_summarized>{summarized}</web_search_results_summarized>'

# if __name__ == '__main__':
#     print(scrape('reliance', 2))