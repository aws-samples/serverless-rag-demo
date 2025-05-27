import requests
import requests
from os import getenv
import logging
from datetime import datetime, timedelta
from agent_executor_utils import bedrockModel
from strands import Agent, tool
from strands_tools import http_request


LOG = logging.getLogger("web_search_agent")
LOG.setLevel(logging.INFO)

WEB_SEARCH_SYSTEM_PROMPT = """
You are a web search agent. Your task is to search the web for information based on the user query.

You have access to the following tools:
- search_ddg: To search the DuckDuckGo for instant answers
- search_wiki: To search Wikipedia for information on a specific topic
- search_yahoo_finance: To search Yahoo Finance for stock market information
- summarize_search_results: To summarize the search results
- rewrite_user_query: To rewrite the user query
- http_request: To make HTTP requests to the web incase other tools are not able to provide the information

Key Responsibilities:
- Rewrite the user query if needed
- Search the web for information
- Summarize the search results

"""

date = datetime.now()
next_date = datetime.now() + timedelta(days=30)
year = date.year
month = date.month
month_label = date.strftime('%B')
next_month_label = next_date.strftime('%B')
day = date.day


def callback_handler(**kwargs):
    tool_use_ids = []
    if "data" in kwargs:
        # Log the streamed data chunks
        print(kwargs["data"])
    elif "current_tool_use" in kwargs:
        tool = kwargs["current_tool_use"]
        if tool["toolUseId"] not in tool_use_ids:
            # Log the tool use
            print(f"\n[Using tool: {tool.get('name')}]")
            tool_use_ids.append(tool["toolUseId"])


@tool
def web_search_agent(user_query):
    agent = Agent(system_prompt=WEB_SEARCH_SYSTEM_PROMPT, model=bedrockModel,
                tools=[ rewrite_user_query, summarize_search_results, search_ddg, search_wiki, search_yahoo_finance, http_request ]
                )
    agent_response = agent(user_query)
    return agent_response

@tool
def search_ddg(query):
    url = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json"}
    response = requests.get(url, params=params)
    return response.json()

@tool
def search_wiki(query):
    url = "https://en.wikipedia.org/w/api.php"
    params = {"action": "query", "format": "json", "list": "search", "srsearch": query}
    response = requests.get(url, params=params)
    return response.json()

@tool
def search_yahoo_finance(query):
    url = "https://query2.finance.yahoo.com/v8/finance/chart/"
    params = {"q": query, "interval": "1d", "range": "1d"}
    response = requests.get(url, params=params)
    return response.json()


@tool
def summarize_search_results(search_data, user_query):
    summarizer_system_prompt = f""" You are a search results summarizer. Given the search results and a user query,
                        Your task is to provide a concise summary of the search results based on the user query.
                        Remember todays year is {year} and the month is {month_label} and day is {day}.
                        The summary should be no more than 60 sentences.
                        Do not include any other text or tags in the response.
                        The search results are available in the <web_search_results> tags.
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

    summarizer_agent = Agent(system_prompt=summarizer_system_prompt, model=bedrockModel)
    summarized = summarizer_agent(query_list)
    
    return summarized


@tool
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
    
    agent = Agent(system_prompt=system_prompt, model=bedrockModel)
    rewritten_query = agent(chat_history)
    print(f'reformatted search_query text = {rewritten_query}')
    return rewritten_query


# if __name__ == '__main__':
#     print(web_search_agent(' Amazon '))
