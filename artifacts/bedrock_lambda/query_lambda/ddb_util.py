import boto3
from os import getenv
from datetime import datetime

#create DynamoDB Client
dynamodb = boto3.resource('dynamodb')
conversation_table_name = getenv("CONVERSATIONS_DYNAMO_TABLE_NAME", "rag-llm-conversations-table-dev")

def push_to_dynamodb(pk, sk, content):
    table = dynamodb.Table(conversation_table_name)
    response = table.put_item(
        Item={
            'prim_key': pk,
            'sort_key': sk + '#' + str(int(round(datetime.now().timestamp()))), 
            'content': content
        }
    )
    
def updateLableToChat(pk, sk, label):
    table = dynamodb.Table(conversation_table_name)
    response = table.put_item(
        Item={
            'prim_key': pk,
            'sort_key': sk + '_' + str(int(round(datetime.now().timestamp()))), 
            'label': label
        }
    )
    
def getDataBysortKeyBeginsWith(pk, sk):
    table = dynamodb.Table(conversation_table_name)
    response = table.query(
        KeyConditionExpression=Key('prim_key').eq(pk) & Key('sort_key').begins_with(sk)
    )
    return response['Items']