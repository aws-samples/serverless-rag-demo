from aws_cdk import Stack, Tags
from constructs import Construct
from infrastructure.opensearch_nextgen_stack import OpensearchNextgenStack
from infrastructure.knowledge_base_stack import KnowledgeBaseStack
from infrastructure.agentcore_stack import AgentCoreStack
from infrastructure.cloudfront_hosting_stack import CloudFrontHostingStack
import os


class LlmsWithServerlessRagStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        env_name = self.node.try_get_context("environment_name")
        env_params = self.node.try_get_context(env_name)
        region = os.getenv("CDK_DEFAULT_REGION", "us-east-1")
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT", "123456789012")

        # 1. OpenSearch Serverless NextGen
        oss_stack = OpensearchNextgenStack(self, f"AOSS-{env_name}")

        # 2. Bedrock Knowledge Base (depends on AOSS)
        kb_stack = KnowledgeBaseStack(
            self, f"KB-{env_name}",
            collection_arn=oss_stack.collection_arn,
            collection_endpoint=oss_stack.collection_endpoint,
        )
        kb_stack.node.add_dependency(oss_stack)

        # 3. AgentCore Runtimes (depends on KB)
        agentcore_stack = AgentCoreStack(
            self, f"AgentCore-{env_name}",
            knowledge_base_id=kb_stack.knowledge_base_id,
            data_bucket_name=kb_stack.data_bucket_name,
            collection_endpoint=oss_stack.collection_endpoint,
        )
        agentcore_stack.node.add_dependency(kb_stack)

        # 4. CloudFront Hosting
        # Note: In full implementation, Cognito + API GW would be separate stacks
        # providing user_pool_id, client_id, rest_url, wss_url.
        # For now, create CloudFront with placeholder values that get overridden
        # by runtime-config.json at deploy time.
        cf_stack = CloudFrontHostingStack(
            self, f"CloudFront-{env_name}",
            cognito_user_pool_id="PLACEHOLDER",
            cognito_client_id="PLACEHOLDER",
            rest_endpoint_url=f"https://placeholder.execute-api.{region}.amazonaws.com/{env_name}/rag/",
            websocket_url=f"wss://placeholder.execute-api.{region}.amazonaws.com/{env_name}",
        )
        cf_stack.node.add_dependency(agentcore_stack)
