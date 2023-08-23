import json
import re
import os
from os import getenv

env = getenv('ENVIRONMENT', 'dev')
def handler(event, context):
    # TODO implement
    print(event)
    print(context)
    runtime_region = os.environ['AWS_REGION']
    htmlFile = open('content/rag_llm.html', 'r')
    apiGatewayUrl = 'https://' + event['requestContext']['apiId'] + '.execute-api.' + runtime_region + '.amazonaws.com' + event['requestContext']['path']

    #Read contents of sample html file
    htmlContent = htmlFile.read()
    htmlContent = re.sub('<apiGatewayUrl>', apiGatewayUrl, htmlContent)
    return {
        'statusCode': 200,
        'headers': {"Content-Type":"text/html"},
        'body':htmlContent
    }
