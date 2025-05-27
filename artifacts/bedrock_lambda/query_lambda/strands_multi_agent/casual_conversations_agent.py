import boto3
from os import getenv
import json
import logging
import datetime
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

GENERAL_CONVERSATION_SYSTEM_PROMPT = """
You are a helpful casual assistant. You can help with general knowlegdge, maths, physics, philosophy,
and creative writing.

Good Examples:
  hello, how may I assist you today
  What would you like to know
  How may I help you today

Bad Examples:
  Hello
  Good day
  Good morning
  How are you
"""

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)


@tool
def general_assistant_agent(user_query):
    print(f'In casual_conversations = {user_query}')
    agent = Agent(system_prompt=GENERAL_CONVERSATION_SYSTEM_PROMPT, model=bedrockModel, tools=[])
    agent_response = agent(user_query)
    return agent_response
