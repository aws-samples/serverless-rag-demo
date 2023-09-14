from aws_cdk import (
    Stack,
    NestedStack,
    aws_iam as _iam,
    aws_lambda as _lambda,
    aws_ecr as _ecr,
)

import aws_cdk as _cdk
import os
from constructs import Construct


class ApiGw_Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        env_name = self.node.try_get_context("environment_name")
        current_timestamp = self.node.try_get_context('current_timestamp')
        region=os.getenv('CDK_DEFAULT_REGION')
        collection_endpoint = 'random'
        llm_model_id = 'random'
        html_header_name = 'Llama2-7B'
        try:
            collection_endpoint = self.node.get_context("collection_endpoint")
            collection_endpoint = collection_endpoint.replace("https://", "")
            llm_model_id = self.node.get_context("llm_model_id")
        except Exception as e:
            pass
        env_params = self.node.try_get_context(env_name)
        print(f'Collection_endpoint= {collection_endpoint}.')
        print(f'LLM_Model_Id= {llm_model_id}')
        
        sagemaker_endpoint_name=env_params['sagemaker_endpoint']
        if 'llama-2-7b' in llm_model_id:
            sagemaker_endpoint_name=env_params['llama2_7b_sagemaker_endpoint']
            html_header_name = 'Llama2-7B'
        elif 'llama-2-13b' in llm_model_id:
            sagemaker_endpoint_name=env_params['llama2_13b_sagemaker_endpoint']
            html_header_name = 'Llama2-13B'
        elif 'llama-2-70b' in llm_model_id:
            sagemaker_endpoint_name=env_params['llama2_70b_sagemaker_endpoint']
            html_header_name = 'Llama2-70B'
        elif 'falcon-7b' in llm_model_id:
            sagemaker_endpoint_name=env_params['falcon_7b_sagemaker_endpoint']
            html_header_name = 'Falcon-7B'
        elif 'falcon-40b' in llm_model_id:
            sagemaker_endpoint_name=env_params['falcon_40b_sagemaker_endpoint']
            html_header_name = 'Falcon-40B'
        elif 'falcon-180b' in llm_model_id:
            sagemaker_endpoint_name=env_params['falcon_180b_sagemaker_endpoint']
            html_header_name = 'Falcon-180B'


        

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
                "throttling_rate_limit": 100,
                "description": env_name + " stage deployment",
            },
            description=api_description,
        )
        rag_llm_api = rag_llm_root_api.root.add_resource("rag")

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
                    role_name= env_params['lambda_role_name'],
                    assumed_by= _iam.ServicePrincipal('lambda.amazonaws.com'),
                    managed_policies= [
                        _iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
                    ]
                )

        
        lambda_function = _lambda.DockerImageFunction(
            self,
            f"llm_rag_{env_name}",
            memory_size=1024,
            timeout=_cdk.Duration.minutes(10),
            role=custom_lambda_role,
            function_name=env_params['lambda_function_name'],
            code=_lambda.DockerImageCode.from_ecr(
                repository=_ecr.Repository.from_repository_name(
                    self,
                    f"lambda_rag_{env_name}",
                    env_params["ecr_repository_name"],
                ),
                tag_or_digest=str(current_timestamp)
            ),
            environment={ 'INDEX_NAME': env_params['index_name'],
                          'OPENSEARCH_ENDPOINT': collection_endpoint,
                          'MODEL_PATH': env_params['model_path'],
                          'REGION': region,
                          'MAX_TOKENS': "2000",
                          'TEMPERATURE': "0.9",
                          'TOP_P': "0.6",
                          'SAGEMAKER_ENDPOINT': sagemaker_endpoint_name,
                          'LLM_MODEL_ID': llm_model_id
                        }
        )


        html_generation_function = _cdk.aws_lambda.Function(self, f'llm_html_function_{env_name}',
                                            function_name=f'llm-html-generator-{env_name}',
                                            runtime=_cdk.aws_lambda.Runtime.PYTHON_3_9,
                                            memory_size=128,
                                            handler='llm_html_generator.handler',
                                            timeout=_cdk.Duration.minutes(1),
                                            code=_cdk.aws_lambda.Code.from_asset(os.path.join(os.getcwd(), 'artifacts/html_lambda/')),
                                            environment={ 'ENVIRONMENT': env_name, 'LLM_MODEL_NAME': html_header_name})        
    
        oss_policy = _iam.PolicyStatement(
            actions=[
                "aoss:*",
                "sagemaker:*",
                "iam:ListUsers",
                "iam:ListRoles",
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
        query_api.add_method(
            "GET",
            lambda_integration,
            operation_name="Query LLM with enhanced Prompt",
            method_responses=method_responses,
        )
        index_docs_api = rag_llm_api.add_resource("index-documents")
        index_docs_api.add_method(
            "POST",
            lambda_integration,
            operation_name="index document",
            method_responses=method_responses,
        )
        index_sample_data_api = rag_llm_api.add_resource("index-sample-data")
        index_sample_data_api.add_method(
            "POST",
            lambda_integration,
            operation_name="index sample document",
            method_responses=method_responses,
        )

        index_docs_api.add_method(
            "DELETE",
            lambda_integration,
            operation_name="delete document index",
            method_responses=method_responses,
        )
        self.add_cors_options(index_docs_api)
        self.add_cors_options(query_api)
        self.add_cors_options(index_sample_data_api)

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
        )
