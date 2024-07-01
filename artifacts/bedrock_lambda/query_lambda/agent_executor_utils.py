import boto3
import json
from os import getenv
import boto3
import logging

region = getenv("REGION", "us-east-1")
bedrock_client = boto3.client('bedrock-runtime')
model_id = getenv("WEBSEARCH_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

def agent_executor(system_prompt, chat_input, output, output_tags="<agent_output></agent_output>") :
    LOG.info(f'method=agent_executor, sys_prompt={system_prompt}, user_query={chat_input}, output_tags={output_tags}')
    system_prompt = f""" {system_prompt}.
                        <instructions> 
                        You will wrap the {output} in {output_tags} tags only
                        </instructions>
                     """
    output_start_tag = output_tags.split('><')[0] + '>'
    output_end_tag = '<' + output_tags.split('><')[1]
    
    prompt_template= {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 10000,
                        "system": system_prompt,
                        "messages": chat_input
                    }
    
    response = bedrock_client.invoke_model(
                    body=json.dumps(prompt_template),
                    modelId=model_id,
                    accept='application/json',
                    contentType='application/json'
    )
    llm_output = json.loads(response['body'].read())
    
    LOG.info(f'method=agent_executor, LLM_output={llm_output}')
    
    query_results = ''
    if 'content' in llm_output:
        query_results = llm_output['content'][0]['text']
        if output_start_tag in query_results and output_end_tag in query_results:
            query_results = query_results.split(output_end_tag)[0]
            query_results = query_results.split(output_start_tag)[1]
    
    LOG.info(f'method=agent_executor, agent_output= {query_results}')
    return query_results