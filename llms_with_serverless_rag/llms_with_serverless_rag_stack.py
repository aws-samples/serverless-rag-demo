from aws_cdk import Stack, Tags, Environment, aws_codebuild as _codebuild, aws_ecr as _ecr
from constructs import Construct
from infrastructure.opensearch_vectordb_stack import OpensearchVectorDbStack
from infrastructure.api_gw_stack import ApiGw_Stack
from infrastructure.bedrock_layer_stack import BedrockLayerStack
from infrastructure.ecr_ui_stack import ECRUIStack
from infrastructure.apprunner_hosting_stack import AppRunnerHostingStack
import os


class LlmsWithServerlessRagStack(Stack):
    def tag_my_stack(self, stack):
        tags = Tags.of(stack)
        tags.add("project", "llms-with-serverless-rag")

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        env_name = self.node.try_get_context("environment_name")
        is_opensearch = self.node.try_get_context("is_aoss")
        bedrock_stack = BedrockLayerStack(self, f'bedrock_rag_container_{env_name}')
        stack_deployed = bedrock_stack
        self.tag_my_stack(stack_deployed)

        if is_opensearch == 'yes':
            # Opensearch Serverless config
            oss_stack = OpensearchVectorDbStack(self, f"vector_db_{env_name}")
            self.tag_my_stack(oss_stack)
            stack_deployed.add_dependency(oss_stack)

        ecr_ui_stack = ECRUIStack(self, f"ecr_ui_{env_name}")
        self.tag_my_stack(ecr_ui_stack)

        apprunner_stack = AppRunnerHostingStack(self, f"apprunner_hosting_{env_name}")
        self.tag_my_stack(apprunner_stack)
        apprunner_stack.add_dependency(ecr_ui_stack)

        
    

        
        

        