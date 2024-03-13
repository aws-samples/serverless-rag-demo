import json
import re
import os
from os import getenv

env = getenv('ENVIRONMENT', 'dev')
html_header = getenv('LLM_MODEL_NAME', 'Llama2-7B')
bedrock_streaming_socket =  getenv('WSS_URL', 'Not Set')
is_rag_enabled = getenv('IS_RAG_ENABLED', 'yes')

def handler(event, context):
    # TODO implement
    print(event)
    print(context)
    runtime_region = os.environ['AWS_REGION']
    htmlFile = open('content/rag_llm.html', 'r')
    if html_header == 'Amazon Bedrock':
        htmlFile = open('content/rag_bedrock.html', 'r')    
    
    apiGatewayUrl = 'https://' + event['requestContext']['apiId'] + '.execute-api.' + runtime_region + '.amazonaws.com' + event['requestContext']['path']

    #Read contents of sample html file
    htmlContent = htmlFile.read()
    htmlContent = re.sub('<apiGatewayUrl>', apiGatewayUrl, htmlContent)
    htmlContent = re.sub('<htmlheader>', html_header, htmlContent)
    htmlContent = re.sub('<websocketUrl>', bedrock_streaming_socket, htmlContent)
    htmlContent = re.sub('<isRagEnabled>', is_rag_enabled, htmlContent)
    return {
        'statusCode': 200,
        'headers': {"Content-Type":"text/html"},
        'body':htmlContent
    }
