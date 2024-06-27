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


def install_package(package_name: str):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "geopy", "--target", "/tmp"])
    sys.path.append('/tmp')


bedrock_client = boto3.client('bedrock-runtime')
credentials = boto3.Session().get_credentials()
service = 'aoss'
region = getenv("REGION", "us-east-1")
model_id = getenv("CODE_GENERATOR_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0")


code_gen_agent_name = "Code Generator Agent"
code_gen_agent_description = "This Tool consists of method to generate and execute pure python code" 

code_generation_step_rules = """
                    Additional Code Generation Rules
                    1. For charts or graphs use plotly library
                    2. For presentations use python-pptx
                """

code_gen_specs = f"""\
<agent_name>{code_gen_agent_name}</agent_name>
<agent_description>{code_gen_agent_description}</agent_description>
<tool_set>
	<instructions>
    1. You will only generate and execute python code.
    2. You will also pip install any missing dependencies before code execution using
       the install_package method provided in this tool set.
    3. You will always generate syntactically correct python code compatible with python 3.10 .
   </instructions>
	<tool_description>
		<tool_usage>This tool is used to generate pure python code</tool_usage>
		<tool_name>install_package</tool_name>
		<parameters>
			<parameter>
				<name>package_name</name>
				<type>string</type>
				<description>Enter the package name you want to install</description>
			</parameter>
		</parameters>
	</tool_description>
	<tool_description>
		<tool_usage>This tool is used to generate structured python code</tool_usage>
		<tool_name>generate_and_execute_python_code</tool_name>
		<parameters>
			<parameter>
				<name>user_query</name>
				<type>string</type>
				<description>Enter the user query based on which python code will be generated</description>
			</parameter>
		</parameters>
	</tool_description>
	<tool_description>
		<tool_usage>Store any artifacts generated from the execute method on S3 bucket for easier access</tool_usage>
		<tool_name>upload_to_s3</tool_name>
		<parameters>
			<parameter>
				<name>file</name>
				<type>file</type>
				<description>Upload any artifacts generated from the execute method on S3 bucket for easier access</description>
			</parameter>
		</parameters>
	</tool_description>
	<tool_description>
		<tool_usage>Store any artifacts generated from the execute method on a local file path</tool_usage>
		<tool_name>get_file</tool_name>
		<parameters>
			<parameter>
				<name>file</name>
			</parameter>
		</parameters>
	</tool_description>
	</tool_set>
"""


def generate_and_execute_python_code(user_query: str):
    system_prompt = """You will generate structured syntactially correct python code only.
                    You will not generate any text or tags. 
                    You will only generate python code based on user query.
                    You will install missing packages before importing them by calling the install_package(package_name) method.
                    You will use the return_me variable to return the result of your code execution.
                    Example 1:
                        install_package("geopy")
                        import geopy

                    Example 2:
                        install_package("python-pptx")
                        from pptx import Presentation
                   
                    You will only return python code and no other text or tags
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
    
    print(f'Code Gen -> Prmpt template {prompt_template}')
    
    response = bedrock_client.invoke_model(
                body=json.dumps(prompt_template),
                modelId=model_id,
                accept='application/json',
                contentType='application/json'
    )
    llm_output = json.loads(response['body'].read())
    python_code = ''
    data = ''
    if 'content' in llm_output:
        python_code = llm_output['content'][0]['text']
        data = execute_python_code(python_code)
    print(f'Code Gen -> Python Code {python_code}')
    return data


def execute_python_code(function_str: str):
    print(f'execute code function_str -> {function_str}')
    try:
        loc = {}
        exec(function_str, globals(), loc)
        return_workaround = loc['return_me']
        return f"Code executed successfully {return_workaround}"
    except Exception as e:
        return f"Error executing the code : {str(e)}"
    
