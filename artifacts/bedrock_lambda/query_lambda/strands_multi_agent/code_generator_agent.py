import boto3
from os import getenv
import json
from strands import Agent, tool
from os import getenv
from datetime import datetime
from agent_executor_utils import bedrockModel

CODE_GENERATOR_SYSTEM_PROMPT = """
You are a code generator agent. Your task is to generate code based on the user query.

Key Responsibilities:
- Generate code based on the user query
- Use the tool upload_object_to_s3 to upload the generated code to S3
- The upload_object_to_s3 tool returns the presigned S3 url where the code is uploaded.
- You should use this S3 url to display the code to the user.

General Instructions:
- Use only the following tools:
    - upload_object_to_s3: To upload the generated code to S3
- You will generate structured syntactially correct HTML code only based on User query.
- You will always generate syntactically correct single page HTML/Javascript/JQuery/CSS code.
- The CSS/HTML/Javascript/JQuery code should be part of a single file within the <html></html> tags.
- If the code is not generated, return "Code generation failed"
- If the user query is not clear, return "User query is not clear"
- If the user query is not valid, return "User query is not valid"
- You should pass on the presigned S3 url of the code to the user so it renders on the UI.
"""

s3_client = boto3.client('s3')
s3_bucket_name = getenv("S3_BUCKET_NAME", "S3_BUCKET_NAME_MISSING")

@tool
def code_generator_agent(user_query: str):
    agent = Agent(system_prompt=CODE_GENERATOR_SYSTEM_PROMPT, model=bedrockModel, tools=[upload_object_to_s3])
    agent_response = agent(user_query)
    upload_object_to_s3(agent_response)
    return agent_response

@tool
def upload_object_to_s3(artifact, file_extension="html", content_type="text/html"):
    try:
        now = datetime.now()
        artifact = artifact.replace("\n", "")
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
      
# if __name__ == "__main__":
#     print(code_generator("Generate a simple HTML page with a header and a footer"))