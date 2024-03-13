from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_iam as _iam
)
from constructs import Construct
import os
import aws_cdk as _cdk

# This stack creates the bedrock Agents Lambda
class BedrockAgentsStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)
        region=os.getenv('CDK_DEFAULT_REGION')
        account_id = os.getenv('CDK_DEFAULT_ACCOUNT')

        custom_lambda_role = _iam.Role(self, f'llm_rag_role_{env_name}', 
                    role_name= env_params['lambda_role_name'] + '_' + region,
                    assumed_by= _iam.ServicePrincipal('lambda.amazonaws.com'),
                    managed_policies= [
                        _iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
                    ]
        )
        
        boto3_bedrock_layer = _lambda.LayerVersion.from_layer_version_arn(self, f'boto3-bedrock-layer-{env_name}',
                                                       f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["boto3_bedrock_layer"]}:1')
        opensearchpy_layer = _lambda.LayerVersion.from_layer_version_arn(self, f'opensearchpy-layer-{env_name}',
                                                       f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["opensearchpy_layer"]}:1')
            
        aws4auth_layer = _lambda.LayerVersion.from_layer_version_arn(self, f'aws4auth-layer-{env_name}',
                                                       f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["aws4auth_layer"]}:1')
            
        langchainpy_layer = _lambda.LayerVersion.from_layer_version_arn(self, f'langchain-layer-{env_name}',
                                                       f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["langchainpy_layer_name"]}:1')
            
        bedrock_agents_lambda_function = _lambda.Function(self, f'bedrock-agents-{env_name}',
                                      function_name=env_params['bedrock_agents_function_name'],
                                      code = _cdk.aws_lambda.Code.from_asset(os.path.join(os.getcwd(), 'artifacts/bedrock_lambda/agent_lambda/')),
                                      runtime=_lambda.Runtime.PYTHON_3_10,
                                      handler="bedrock_agent.lambda_handler",
                                      role=custom_lambda_role,
                                      timeout=_cdk.Duration.seconds(300),
                                      description="Amazon Bedrock agents",
                                      memory_size=2048,
                                      layers= [boto3_bedrock_layer , opensearchpy_layer, aws4auth_layer, langchainpy_layer]
                                    )
        
        bedrock_oss_policy = _iam.PolicyStatement(
                actions=[
                    "aoss:ListCollections", "aoss:BatchGetCollection", "aoss:APIAccessAll",
                    "apigateway:GET", "apigateway:DELETE", "apigateway:PATCH", "apigateway:POST", "apigateway:PUT",
                    "execute-api:InvalidateCache", "execute-api:Invoke", "execute-api:ManageConnections",
                    "bedrock:*", "s3:*",
                    "iam:ListUsers", "iam:ListRoles"],
                resources=["*"],
            )
        bedrock_agents_lambda_function.add_to_role_policy(bedrock_oss_policy)
