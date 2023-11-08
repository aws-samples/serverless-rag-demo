from aws_cdk import Stack, Tags, Environment, aws_codebuild as _codebuild, aws_ecr as _ecr
from constructs import Construct
from infrastructure.opensearch_vectordb_stack import OpensearchVectorDbStack
from infrastructure.ecr_stack import Ecr_stack
from infrastructure.api_gw_stack import ApiGw_Stack
from infrastructure.bedrock_layer_stack import BedrockLayerStack
import os


class LlmsWithServerlessRagStack(Stack):
    def tag_my_stack(self, stack):
        tags = Tags.of(stack)
        tags.add("project", "llms-with-serverless-rag")

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        env_name = self.node.try_get_context("environment_name")
        llm_model_id = self.node.try_get_context("llm_model_id")
        # Opensearch Serverless config
        oss_stack = OpensearchVectorDbStack(self, f"vector_db_{env_name}")
        stack_deployed = None
        if llm_model_id == 'Amazon Bedrock':
            bedrock_stack = BedrockLayerStack(self, f'bedrock_rag_container_{env_name}')
            stack_deployed = bedrock_stack
        else:
            ecr_stack = Ecr_stack(self, f'lambda_rag_container_{env_name}')
            stack_deployed = ecr_stack
        # Lambda / Api Gateway text/html
        #api_gw_stack = ApiGw_Stack(self, f'api_gw_lambda_{env_name}')
        # Sagemaker

        self.tag_my_stack(oss_stack)
        self.tag_my_stack(stack_deployed)
        
        stack_deployed.add_dependency(oss_stack)