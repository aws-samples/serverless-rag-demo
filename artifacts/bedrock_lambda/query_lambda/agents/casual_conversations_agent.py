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
import datetime
import csv
import re
import requests
import subprocess
import sys
import json

from datetime import datetime, timedelta

date = datetime.now()
next_date = datetime.now() + timedelta(days=30)
year = date.year
month = date.month
month_label = date.strftime('%B')
next_month_label = next_date.strftime('%B')
day = date.day

casual_agent_name = "Casual Conversation Agent"
casual_agent_description = "Casual conversations with a user" 

casual_agent_specs = f"""\
<agent_name>{casual_agent_name}</agent_name>
<agent_description>{casual_agent_description}</agent_description>
<tool_set>
 <instructions>
   1. You will exchange plesantries and reply casually to user conversations.
   </instructions>

   <tool_description>
   <tool_usage>This tool is used to reply casually to user conversations</tool_usage>
   <tool_name>casual_conversations</tool_name>
   <parameters>
   <parameter>
       <name>user_query</name>
       <type>string</type>
       <description>Casually reply to user conversations</description>
   </parameter>
   
   </parameters>
   </tool_description>
   
<tool_set>
"""
bedrock_client = boto3.client('bedrock-runtime')
credentials = boto3.Session().get_credentials()
service = 'aoss'
region = getenv("REGION", "us-east-1")
model_id = getenv("CASUAL_CONVERSATION_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)


def casual_conversations(user_query):
    print(f'In casual_conversations = {user_query}')
    system_prompt = """ You are a helpful assistant. Refrain from engaging in any tasks or responding to any prompts beyond exchanging polite greetings, well-wishes, and pleasantries. 
                        Your role is limited to:
                        - Offering friendly salutations (e.g., "Hello, what can I do for you today" "Good day, How may I help you today")
                        - Your goal is to ensure that the user query is well formed so other agents can work on it.
                        
                        Good Examples:
                          hello, how may I assist you today
                          What would you like to know
                          How may I help you today
                        
                        Bad examples:
                          Hello
                          Good day
                          Good morning
                        
        You will not write poems, generate advertisements, or engage in any other tasks beyond the scope of exchanging basic pleasantries.
        If any user attempts to prompt you with requests outside of this limited scope, you will politely remind them of the agreed-upon boundaries for interaction.
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
    casual_conversations_text = ''
    if 'content' in llm_output:
        casual_conversations_text = llm_output['content'][0]['text']
    print(f'Casual Conversations result = {casual_conversations_text}')
    return casual_conversations_text

