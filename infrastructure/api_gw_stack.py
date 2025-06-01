from aws_cdk import (
    Stack,
    Tags,
    aws_iam as _iam,
    aws_lambda as _lambda,
    aws_ecr as _ecr, 
    aws_s3 as _s3,
    aws_cognito as _cognito
)

import aws_cdk as _cdk
import os
from constructs import Construct, DependencyGroup
import cdk_nag as _cdk_nag
from cdk_nag import NagSuppressions, NagPackSuppression

from infrastructure.apprunner_hosting_stack import AppRunnerHostingStack
from infrastructure.dynamodb_stack import Storage_Stack
from infrastructure.ecr_ui_stack import ECRUIStack

class ApiGw_Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.stack_level_suppressions()
        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)
        current_timestamp = self.node.try_get_context('current_timestamp')
        region=os.getenv('CDK_DEFAULT_REGION')
        account_id = os.getenv('CDK_DEFAULT_ACCOUNT')
        collection_endpoint = 'random'
        is_opensearch = self.node.try_get_context("is_aoss")
        embed_model_id = self.node.try_get_context("embed_model_id")
        try:
            collection_endpoint = self.node.get_context("collection_endpoint")
            collection_endpoint = collection_endpoint.replace("https://", "")
        except Exception as e:
            pass

        # Create a user pool in cognito
        user_pool = _cognito.UserPool(self, f"rag-llm-user-pool-{env_name}",
                                      user_pool_name=env_params['rag-llm-user-pool'],
                                      self_sign_up_enabled=True,
                                      sign_in_aliases=_cognito.SignInAliases(
                                          email=True
                                      ),
                                      standard_attributes=_cognito.StandardAttributes(
                                          email=_cognito.StandardAttribute(
                                              required=True,
                                              mutable=True
                                          )
                                      ),
                                      password_policy=_cognito.PasswordPolicy(
                                          min_length=8,
                                          require_digits=True,
                                          require_lowercase=True,
                                          require_uppercase=True,
                                          require_symbols=True
                                      )
                                      )
        
        user_pool.from_user_pool_id
        # for the user pool created above create a application client
        user_pool_client = _cognito.UserPoolClient(self, f"rag-llm-user-pool-client-{env_name}",
                                                    user_pool=user_pool,
                                                    user_pool_client_name=f"rag-llm-user-pool-client-{env_name}",
                                                    generate_secret=False,
                                                    auth_flows=_cognito.AuthFlow(
                                                       user_password=True,
                                                       # TODO validate this
                                                       user_srp=True
                                                    ),
                                                    id_token_validity=_cdk.Duration.days(1)
                                                   )
        
        

        # create an api gateway authorizer with the cognito user pool above
        cognito_authorizer = _cdk.aws_apigateway.CognitoUserPoolsAuthorizer(self, f"rag-llm-cognito-authrzr-{env_name}",
                                                                            cognito_user_pools=[user_pool], 
                                                                            authorizer_name=env_params["rag-llm-cognito"])

        print(f'Collection_endpoint={collection_endpoint}')
        bucket_name = f'{env_params["s3_images_data"]}-{account_id}-{region}'
        html_header_name = 'Amazon Bedrock'        

        # Define API's
        # Base URL
        api_description = "RAG with Opensearch Serverless"

        rag_llm_root_api = _cdk.aws_apigateway.RestApi(
            self,
            f"rag-llm-api-{env_name}",
            deploy=True,
            endpoint_types=[_cdk.aws_apigateway.EndpointType.REGIONAL],
            deploy_options={
                "stage_name": env_name,
                "throttling_rate_limit": 1000,
                "description": env_name + " stage deployment",
            },
            description=api_description,
            # default_method_options= _cdk.aws_apigateway.MethodOptions(authorizer=cognito_authorizer,
            #                                                           authorization_type=_cdk.aws_apigateway.AuthorizationType.COGNITO  
            #                                                         )
        )

        
            
        parent_path='rag'
        rag_llm_api = rag_llm_root_api.root.add_resource(parent_path)
        rest_endpoint_url = f'https://{rag_llm_root_api.rest_api_id}.execute-api.{region}.amazonaws.com/{env_name}/{parent_path}/'
        cors_s3_link = f'https://{rag_llm_root_api.rest_api_id}.execute-api.{region}.amazonaws.com'
        print(rest_endpoint_url)
        
        method_responses = [
            # Successful response from the integration
            {
                "statusCode": "200",
                # Define what parameters are allowed or not
                "responseParameters": {
                    "method.response.header.Content-Type": True,
                    "method.response.header.Access-Control-Allow-Origin": True,
                    "method.response.header.Access-Control-Allow-Credentials": True,
                },
            }
        ]

        
        custom_lambda_role = _iam.Role(self, f'llm_rag_role_{env_name}', 
                    role_name= env_params['lambda_role_name'] + '_' + region,
                    assumed_by= _iam.ServicePrincipal('lambda.amazonaws.com'),
                    managed_policies= [
                        _iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
                    ]
                )

        lambda_function = None
        bedrock_query_lambda_integration = None
        bedrock_index_lambda_integration = None
        wss_url=''
        
        # These are created in buildspec-bedrock.yml file.
        addtional_libs_layer = _lambda.LayerVersion.from_layer_version_arn(self, f'additional-libs-layer-{env_name}',
                                                   f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["addtional_libs_layer_name"]}:1')
        # This is created in buildspec-bedrock.yml file.
        addtional_libs_layer_x86 = _lambda.LayerVersion.from_layer_version_arn(self, f'additional-libs-layer-x86-{env_name}',
                                                   f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["addtional_libs_layer_name"]}-x86:1')
        
        # This is created in buildspec-bedrock.yml file.
        agentic_libs_layer_name = _lambda.LayerVersion.from_layer_version_arn(self, f'strands-layer-name-{env_name}',
                                                   f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["strands_layer_name"]}:1')
        
        agentic_tools_layer_name = _lambda.LayerVersion.from_layer_version_arn(self, f'agentic-tools-layer-{env_name}',
                                                   f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["agents_tools_layer_name"]}:1')
            
        langchainpy_layer = _lambda.LayerVersion.from_layer_version_arn(self, f'langchain-layer-{env_name}',
                                                   f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["langchainpy_layer_name"]}:1')
        
        langchainpy_layer_x86 = _lambda.LayerVersion.from_layer_version_arn(self, f'langchain-layer-x86-{env_name}',
                                                   f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["langchainpy_layer_name"]}-x86:1')
        # This is created in buildspec-bedrock.yml file.
        pdfpy_layer_x86 = _lambda.LayerVersion.from_layer_version_arn(self, f'pdfpy-layer-x86-{env_name}',
                                                   f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["pypdf_layer"]}-x86:1')
        
        pdfpy_layer = _lambda.LayerVersion.from_layer_version_arn(self, f'pdfy-layer-{env_name}',
                                                   f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["pypdf_layer"]}:1')
        print('--- Amazon Bedrock Deployment ---')
        
        
        bedrock_indexing_lambda_function = _lambda.Function(self, f'llm-bedrock-index-{env_name}',
                              function_name=env_params['bedrock_indexing_function_name'],
                              code = _cdk.aws_lambda.Code.from_asset(os.path.join(os.getcwd(), 'artifacts/bedrock_lambda/index_lambda/')),
                              runtime=_lambda.Runtime.PYTHON_3_12,
                              architecture=_lambda.Architecture.X86_64,
                              handler="index.handler",
                              role=custom_lambda_role,
                              timeout=_cdk.Duration.seconds(600),
                              description="Create embeddings in Amazon Bedrock",
                              environment={ 'VECTOR_INDEX_NAME': env_params['index_name'],
                                            'OPENSEARCH_VECTOR_ENDPOINT': collection_endpoint,
                                            'REGION': region,
                                            'S3_BUCKET_NAME': bucket_name,
                                            'EMBED_MODEL_ID': embed_model_id,
                                            'INDEX_DYNAMO_TABLE_NAME': env_params['index_dynamo_table_name']
                              },
                              memory_size=3000,
                              layers= [addtional_libs_layer_x86, langchainpy_layer_x86, pdfpy_layer_x86])
        multi_agent_model = 'anthropic.claude-3-7-sonnet-20250219-v1:0'
        model_region = region.split('-')[0]
        inference_profile_id = f"{model_region}.{multi_agent_model}"
        print(f'Inference Profile ID: {inference_profile_id}')
        lambda_function = bedrock_indexing_lambda_function
        bedrock_querying_lambda_function = _lambda.Function(self, f'llm-bedrock-query-{env_name}',
                              function_name=env_params['bedrock_querying_function_name'],
                              code = _cdk.aws_lambda.Code.from_asset(os.path.join(os.getcwd(), 'artifacts/bedrock_lambda/query_lambda/')),
                              runtime=_lambda.Runtime.PYTHON_3_12,
                              architecture=_lambda.Architecture.ARM_64,
                              handler="query_rag_bedrock.handler",
                              role=custom_lambda_role,
                              timeout=_cdk.Duration.seconds(300),
                              description="Query Models in Amazon Bedrock",
                              environment={ 'VECTOR_INDEX_NAME': env_params['index_name'],
                                            'OPENSEARCH_VECTOR_ENDPOINT': collection_endpoint,
                                            'REGION': region,
                                            'REST_ENDPOINT_URL': rest_endpoint_url,
                                            'IS_RAG_ENABLED': is_opensearch,
                                            'S3_BUCKET_NAME': bucket_name,
                                            'EMBED_MODEL_ID': embed_model_id,
                                            'IS_BEDROCK_KB': 'no',
                                            'CONVERSATIONS_DYNAMO_TABLE_NAME': env_params['conversations_dynamo_table_name'],
                                            'MULTI_AGENT_MODEL': inference_profile_id
                              },
                              memory_size=3000,
                            layers= [addtional_libs_layer, agentic_libs_layer_name, agentic_tools_layer_name, pdfpy_layer]
                            #   layers= [addtional_libs_layer, langchainpy_layer, pdfpy_layer]
                            )
        
        websocket_api = _cdk.aws_apigatewayv2.CfnApi(self, f'bedrock-streaming-response-{env_name}',
                                    protocol_type='WEBSOCKET',
                                    name=f'Bedrock-streaming-{env_name}',
                                    route_selection_expression='$request.body.action'
                                    )
        
        print(f'Bedrock streaming wss url {websocket_api.attr_api_endpoint}')
        wss_url = websocket_api.attr_api_endpoint
        bedrock_oss_policy = _iam.PolicyStatement(
            actions=[
                "aoss:ListCollections", "aoss:BatchGetCollection", "aoss:APIAccessAll", "lambda:InvokeFunction",
                "apigateway:GET", "apigateway:DELETE", "apigateway:PATCH", "apigateway:POST", "apigateway:PUT",
                "execute-api:InvalidateCache", "execute-api:Invoke", "execute-api:ManageConnections",
                "bedrock:ListFoundationModelAgreementOffers", "bedrock:ListFoundationModels","bedrock:GetFoundationModel",
                "bedrock:GetFoundationModelAvailability", "bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
                "iam:ListUsers", "iam:ListRoles", "s3:*", "dynamodb:*"],
            resources=["*"],
        )

        bedrock_querying_lambda_function.add_to_role_policy(bedrock_oss_policy)
        
        bedrock_indexing_lambda_function.add_to_role_policy(bedrock_oss_policy)
        
        bucket_name = f'{env_params["s3_images_data"]}-{account_id}-{region}'
        
        
        s3_principal = _iam.ServicePrincipal('s3.amazonaws.com', conditions={ 
            "ArnLike": { 
                "aws:SourceArn": f"arn:aws:s3:::{bucket_name}" 
                },
                "StringEquals": {
                    "aws:SourceAccount": account_id
                    }
        })
        
        bedrock_indexing_lambda_function.grant_invoke(s3_principal)
        
        bedrock_querying_lambda_function.add_environment('WSS_URL', wss_url + '/' + env_name)
        
        bedrock_index_lambda_integration = _cdk.aws_apigateway.LambdaIntegration(
        bedrock_indexing_lambda_function, proxy=True, allow_test_invoke=True)
        
        bedrock_query_lambda_integration = _cdk.aws_apigateway.LambdaIntegration(
        bedrock_querying_lambda_function, proxy=True, allow_test_invoke=True)
        
        apigw_role = _iam.Role(self, f'bedrock-lambda-invoke-{env_name}', assumed_by=_iam.ServicePrincipal('apigateway.amazonaws.com'))
        apigw_role.add_to_policy(_iam.PolicyStatement(effect=_iam.Effect.ALLOW,
                            actions=["lambda:InvokeFunction"],
                            resources=[bedrock_querying_lambda_function.function_arn, bedrock_indexing_lambda_function.function_arn], 
                            ))
        
        websocket_integrations = _cdk.aws_apigatewayv2.CfnIntegration(self, f'bedrock-websocket-integration-{env_name}',
                                            api_id=websocket_api.ref,
                                            integration_type="AWS_PROXY",
                                            integration_uri="arn:aws:apigateway:" + region + ":lambda:path/2015-03-31/functions/" + bedrock_querying_lambda_function.function_arn + "/invocations",
                                            credentials_arn=apigw_role.role_arn
                                            )
        
        # Query Lambda Connect websocket route
        websocket_connect_route = _cdk.aws_apigatewayv2.CfnRoute(self, f'bedrock-connect-route-{env_name}',
                                        api_id=websocket_api.ref, route_key="$connect",
                                        authorization_type="NONE",
                                        target="integrations/"+ _cdk.aws_apigatewayv2.CfnIntegration(self, f"bedrock-socket-conn-integration-{env_name}",
                                                                                                     api_id= websocket_api.ref,
                                                                                                     integration_type="AWS_PROXY",
                                                                                                     integration_uri="arn:aws:apigateway:" + region + ":lambda:path/2015-03-31/functions/" + bedrock_querying_lambda_function.function_arn + "/invocations",
                                                                                                     credentials_arn= apigw_role.role_arn).ref
        )

        
        dependencygrp = DependencyGroup()
        dependencygrp.add(websocket_connect_route)
        # Query Lambda Disconnect websocket route
        websocket_disconnect_route = _cdk.aws_apigatewayv2.CfnRoute(self, f'bedrock-disconnect-route-{env_name}',
                                        api_id=websocket_api.ref, route_key="$disconnect",
                                        authorization_type="NONE",
                                        target="integrations/" + websocket_integrations.ref)
        # Query Lambda Default websocket route
        websocket_default_route = _cdk.aws_apigatewayv2.CfnRoute(self, f'bedrock-default-route-{env_name}',
                                        api_id=websocket_api.ref, route_key="$default",
                                        authorization_type="NONE",
                                        target="integrations/" + websocket_integrations.ref)
        # Query Lambda Bedrock websocket route
        websocket_bedrock_route = _cdk.aws_apigatewayv2.CfnRoute(self, f'bedrock-route-{env_name}',
                                        api_id=websocket_api.ref, route_key="bedrock",
                                        authorization_type="NONE",
                                        target="integrations/" + websocket_integrations.ref)
        
        
        deployment = _cdk.aws_apigatewayv2.CfnDeployment(self, f'bedrock-streaming-deploy-{env_name}', api_id=websocket_api.ref)
        deployment.add_dependency(websocket_connect_route)
        deployment.add_dependency(websocket_disconnect_route)
        deployment.add_dependency(websocket_bedrock_route)
        deployment.add_dependency(websocket_default_route)
        
        websocket_stage = _cdk.aws_apigatewayv2.CfnStage(self, f'bedrock-streaming-stage-{env_name}', 
                                           api_id=websocket_api.ref,
                                           auto_deploy=True,
                                           deployment_id= deployment.ref,
                                           stage_name= env_name) 
    
        html_generation_function = _cdk.aws_lambda.Function(self, f'llm_html_function_{env_name}',
                                            function_name=f'llm-html-generator-{env_name}',
                                            runtime=_cdk.aws_lambda.Runtime.PYTHON_3_9,
                                            memory_size=128,
                                            handler='llm_html_generator.handler',
                                            timeout=_cdk.Duration.minutes(1),
                                            code=_cdk.aws_lambda.Code.from_asset(os.path.join(os.getcwd(), 'artifacts/html_lambda/')),
                                            environment={ 'ENVIRONMENT': env_name,
                                                          'LLM_MODEL_NAME': html_header_name,
                                                          'WSS_URL': wss_url + '/' + env_name,
                                                          'IS_RAG_ENABLED': is_opensearch
                                                        })        
    
        oss_policy = _iam.PolicyStatement(
            actions=[
                "aoss:*",
                "sagemaker:*",
                "iam:ListUsers",
                "iam:ListRoles",
                "apigateway:*"
            ],
            resources=["*"],
        )

        lambda_function.add_to_role_policy(oss_policy)
        

        lambda_integration = _cdk.aws_apigateway.LambdaIntegration(
            lambda_function, proxy=True, allow_test_invoke=True
        )

        html_generation_lambda_integration = _cdk.aws_apigateway.LambdaIntegration(
            html_generation_function, proxy=True, allow_test_invoke=True
        )

        rag_llm_api.add_method("GET",
                                html_generation_lambda_integration, operation_name="HTML file",
                                method_responses=method_responses)
        
        query_api = rag_llm_api.add_resource("query")
        index_docs_api = rag_llm_api.add_resource("index-documents")
        get_presigned_url_api = rag_llm_api.add_resource("get-presigned-url")
        del_file_api = rag_llm_api.add_resource("del-file")
        file_data_api = rag_llm_api.add_resource("file_data")
        connect_tracker_api = rag_llm_api.add_resource("connect-tracker")
        get_indexed_files_by_user_api = rag_llm_api.add_resource('get-indexed-files-by-user')
        
        
        index_docs_api.add_method(
                "POST",
                bedrock_index_lambda_integration,
                authorizer=cognito_authorizer,
                authorization_type=_cdk.aws_apigateway.AuthorizationType.COGNITO,
                operation_name="index document",
                method_responses=method_responses,
                api_key_required=False
            )
        index_docs_api.add_method(
                "DELETE",
                bedrock_index_lambda_integration,
                authorizer=cognito_authorizer,
                authorization_type=_cdk.aws_apigateway.AuthorizationType.COGNITO,
                operation_name="delete document index",
                method_responses=method_responses,
                api_key_required=False
            )
        
        get_presigned_url_api.add_method(
            "GET",
            lambda_integration,
            authorizer=cognito_authorizer,
            authorization_type=_cdk.aws_apigateway.AuthorizationType.COGNITO,
            operation_name="Get Presigned Post URL",
            api_key_required=False,
            method_responses=method_responses,
        )

        del_file_api.add_method(
            "POST",
            lambda_integration,
            authorizer=cognito_authorizer,
            authorization_type=_cdk.aws_apigateway.AuthorizationType.COGNITO,
            operation_name="Get Presigned Delete URL",
            api_key_required=False,
            method_responses=method_responses,
        )

        get_indexed_files_by_user_api.add_method(
            "GET",
            lambda_integration,
            authorizer=cognito_authorizer,
            authorization_type=_cdk.aws_apigateway.AuthorizationType.COGNITO,
            operation_name="Get Indexed Files by User",
            method_responses=method_responses,
        )

        file_data_api.add_method(
            "POST",
            bedrock_query_lambda_integration,
            authorizer=cognito_authorizer,
            authorization_type=_cdk.aws_apigateway.AuthorizationType.COGNITO,
            operation_name="Store documents",
            method_responses=method_responses,
            api_key_required=False
        )
        
        connect_tracker_api.add_method(
                "GET",
                bedrock_index_lambda_integration,
                authorizer=cognito_authorizer,
                authorization_type=_cdk.aws_apigateway.AuthorizationType.COGNITO,
                operation_name="Websocket rate limiter",
                method_responses=method_responses,
                api_key_required=False
            )
        
        self.add_cors_options(file_data_api)
        self.add_cors_options(connect_tracker_api)
        self.add_cors_options(get_presigned_url_api)
        self.add_cors_options(del_file_api)
        self.add_cors_options(index_docs_api)
        self.add_cors_options(query_api)
        self.add_cors_options(get_indexed_files_by_user_api)

        
        user_pool_client_id = user_pool_client.user_pool_client_id
        user_pool_id = user_pool.user_pool_id
        
        _cdk.CfnOutput(self, f"rag-llm-user-poolid-output-{env_name}", value=user_pool_id,
                       export_name="user-pool-id"
                    )
        _cdk.CfnOutput(self, f"rag-llm-auth-clientid-output-{env_name}", value=user_pool_client_id,
                       export_name="client-id"
                    )
        
        ecr_ui_stack = ECRUIStack(self, f"ECRUI{env_name}Stack", user_pool_id, user_pool_client_id, rest_endpoint_url, wss_url + '/' + env_name) 
        self.tag_my_stack(ecr_ui_stack)

        storage_stack = Storage_Stack(self, f"Storage{env_name}Stack")
        self.tag_my_stack(storage_stack)
        
        

    def tag_my_stack(self, stack):
        tags = Tags.of(stack)
        tags.add("project", "llms-with-serverless-rag")

    def add_cors_options(self, apiResource: _cdk.aws_apigateway.IResource):
        apiResource.add_method(
            "OPTIONS",
            _cdk.aws_apigateway.MockIntegration(
                integration_responses=[
                    {
                        "statusCode": "200",
                        "responseParameters": {
                            "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent'",
                            "method.response.header.Access-Control-Allow-Origin": "'*'",
                            "method.response.header.Access-Control-Allow-Credentials": "'false'",
                            "method.response.header.Access-Control-Allow-Methods": "'OPTIONS,GET,PUT,POST,DELETE'",
                        },
                    }
                ],
                passthrough_behavior=_cdk.aws_apigateway.PassthroughBehavior.NEVER,
                request_templates={"application/json": '{"statusCode": 200}'},
            ),
            method_responses=[
                {
                    "statusCode": "200",
                    "responseParameters": {
                        "method.response.header.Access-Control-Allow-Headers": True,
                        "method.response.header.Access-Control-Allow-Methods": True,
                        "method.response.header.Access-Control-Allow-Credentials": True,
                        "method.response.header.Access-Control-Allow-Origin": True,
                    },
                }
            ],
            authorization_type=_cdk.aws_apigateway.AuthorizationType.NONE
        )
    
    def stack_level_suppressions(self):
        NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id='AwsSolutions-IAM5', reason='Its a basic lambda execution role, only has access to create/write to a cloudwatch stream'),
            _cdk_nag.NagPackSuppression(id='AwsSolutions-IAM4', reason='Its a basic lambda execution role, only has access to create/write to a cloudwatch stream'),
            _cdk_nag.NagPackSuppression(id='AwsSolutions-APIG4', reason='Remediated, we are using API keys for access control'),
            _cdk_nag.NagPackSuppression(id='AwsSolutions-APIG1', reason='Logging is expensive for websocket streaming responses coming in from LLMs'),
            _cdk_nag.NagPackSuppression(id='AwsSolutions-COG4', reason='Remediated, we are using API keys for access control')
        ])