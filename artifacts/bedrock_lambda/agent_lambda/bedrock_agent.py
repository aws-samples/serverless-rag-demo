import boto3
import json
from botocore.exceptions import ClientError
from decimal import Decimal
from agents.stock_price import get_stock_template
from agents.websearch import get_websearch_template

bedrock_agent_client = boto3.client('bedrock-agent')
iam_client = boto3.client('iam')
role_name = "sample-bedrock-agent-role"


def create_agent(event, context):

    ACCOUNT_ID = context.invoked_function_arn.split(":")[4]
    REGION = context.invoked_function_arn.split(":")[3]

    ROLE_ARN = None

    try:
        role_data = iam_client.get_role(RoleName=role_name)
        ROLE_ARN = role_data['Role']['Arn']
        print(f"Role '{role_name}' already exists.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
                # creatre a role
                print(f"Create a bedrock agent role with role name '{role_name}'")
            
                trust_policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "AmazonBedrockAgentBedrockFoundationModelPolicyProd",
                            "Effect": "Allow",
                            "Principal": {
                                "Service": "bedrock.amazonaws.com"
                            },
                            "Action": "sts:AssumeRole",
                            "Condition": {
                                "StringEquals": {
                                    "aws:SourceAccount": f"{ACCOUNT_ID}"
                                },
                                "ArnLike": {
                                    "aws:SourceArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent/*"
                                }
                            }
                        }
                    ]
                }
        
                # Create the role
                try:
                        create_role_response = iam_client.create_role(
                            RoleName=role_name,
                            AssumeRolePolicyDocument=json.dumps(trust_policy)
                        )
                        ROLE_ARN = create_role_response['Role']['Arn']
                        print(f"Role '{role_name}' created successfully.")
                
                        policy_name = "sample-bedrock-agent-policy-v1"
                        policy_document = {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "s3:*",
                                    "s3-object-lambda:*"
                                    
                                ],
                                "Resource": [
                                    "*"
                                ]
                            },
                            {
                             "Effect": "Allow",
                             "Action": "bedrock:InvokeModel",
                             "Resource": [
                               f"arn:aws:bedrock:{REGION}::foundation-model/anthropic.claude-v2"
                              ]   
                            }
                        ]
                        }
             
                        # Create the policy
                        create_policy_response = iam_client.create_policy(
                                PolicyName=policy_name,
                                PolicyDocument=json.dumps(policy_document)
                            )
                        policy_arn = create_policy_response['Policy']['Arn']
                        print(f"Policy '{policy_name}' created successfully. ARN: {policy_arn}")
                        iam_client.attach_role_policy(
                            RoleName=role_name,
                            PolicyArn=policy_arn)
                
                except Exception as e:
                    print(f"Error creating role or policy: {e}")
                    raise e

    agent_info = bedrock_agent_client.create_agent(
        agentName='serverless-agent',  
        foundationModel='',
        agentResourceRoleArn=ROLE_ARN
    )

    if 'agent' in agent_info:
        agent_id = agent_info['agent']['agentId']
        agent_version = agent_info['agent']['agentVersion']
        
        file_name=f"open-api-schema.json"
        data = {}
        f = open(file_name, "r")
        data = f.read()

        bedrock_agent_client.create_agent_action_group(
                actionGroupName='serverless-actions',
                description='Function calling examples with Bedrock Agents',
                agentId=agent_id,
                agentVersion=agent_version,
                actionGroupExecutor={"lambda": context.invoked_function_arn},
                apiSchema={"payload": json.dumps(data)}
        )

def get_weather_template(event):
    pass

def get_stock_report_template(event):
    return get_stock_template(event['queryStringParameters']['company'])
    
def get_web_search_content(event):
    return get_websearch_template(event['queryStringParameters']['search'])


def lambda_handler(event, context):
    
    api_map = {
        'POST/rag/bedrock-agent': lambda x: create_agent(x, context),
        'GET/weather': lambda x: get_weather_template(x),
        'GET/stockreport': lambda x: get_stock_report_template(x),
        'GET/websearch': lambda x: get_web_search_content(x),
    }

    http_method = event['httpMethod'] if 'httpMethod' in event else ''
    api_path = http_method + event['resource']
    try:
        if api_path in api_map:
            print(f"method=handler , api_path={api_path}")
            return respond(None, api_map[api_path](event))
        else:
            print(f"error=api_not_found , api={api_path}")
            return respond(failure_response('api_not_supported'), None)
    except Exception as e:
        print(f"error=error_processing_api, api={api_path}, exception={e}")
        return respond(failure_response('system_exception'), None)



# JSON REST output builder method
def respond(err, res=None):
    return {
        'statusCode': '400' if err else res['statusCode'],
        'body': json.dumps(err) if err else json.dumps(res, cls=CustomJsonEncoder),
        'headers': {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Credentials": "*"
        },
    }


def failure_response(error_message):
    return {"success": False, "errorMessage": error_message, "statusCode": "400"}
   
def success_response(result):
    return {"success": True, "result": result, "statusCode": "200"}

# Hack
class CustomJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            if float(obj).is_integer():
                return int(float(obj))
            else:
                return float(obj)
        return super(CustomJsonEncoder, self).default(obj)

    

