import boto3
import json
from os import getenv
import boto3
import logging
import json
from datetime import datetime

region = getenv("REGION", "us-east-1")
bedrock_client = boto3.client('bedrock-runtime')
s3_client = boto3.client("s3")
model_id = getenv("WEBSEARCH_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
s3_bucket_name = getenv("S3_BUCKET_NAME", "S3_BUCKET_NAME_MISSING")


def agent_executor(system_prompt, chat_input, output, output_tags="<agent_output></agent_output>", custom_impl=False) :
    LOG.info(f'method=agent_executor, sys_prompt={system_prompt}, user_query={chat_input}, output= {output}, output_tags={output_tags}, custom_impl={custom_impl}')
    system_prompt = f""" {system_prompt}. """
    output_start_tag=""
    output_end_tag=""
    # If Custom_implementation then we ignore whats sent in output and output tags
    if not custom_impl:
        system_prompt = system_prompt + f"""<instructions> You will wrap the {output} in {output_tags} tags only. 
                        If the {output} can't be found, you will return an empty string within {output_tags} tags.
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
        if not custom_impl and output_start_tag in query_results and output_end_tag in query_results:
            query_results = query_results.split(output_end_tag)[0]
            query_results = query_results.split(output_start_tag)[1]
        
    LOG.info(f'method=agent_executor, agent_output={query_results}')
    return query_results


def upload_object_to_s3(artifact, file_extension, content_type):
    try:
        now = datetime.now()
        date_time = now.strftime("%Y-%m-%d-%H-%M-%S")
        s3_key = f"{file_extension}/sample_{date_time}.{file_extension}"
        s3_client.put_object(Body=artifact, Bucket=s3_bucket_name, Key=s3_key, ContentType=content_type)
        s3_presigned = generate_presigned_url(s3_key)
        if s3_presigned is not None:
            return True, s3_presigned
        return True, s3_key
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return False, f'Error {e}'
    
def upload_file_to_s3(file_name, file_extension):
    try:
        now = datetime.now()
        date_time = now.strftime("%Y-%m-%d-%H-%M-%S")
        s3_key = f"{file_extension}/sample_{date_time}.{file_extension}"
        s3_client.upload_file(file_name, s3_bucket_name, s3_key)
        s3_presigned = generate_presigned_url(s3_key)
        if s3_presigned is not None:
            return True, s3_presigned
        return True, s3_key
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return False, f'Error {e}'

# Generate a presigned get url for s3 file
def generate_presigned_url(s3_key):
    try:
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': s3_bucket_name,
                'Key': s3_key
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )
        return presigned_url
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return None