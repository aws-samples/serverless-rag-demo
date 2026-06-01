#!/usr/bin/env python3
import os
import aws_cdk as cdk
from aws_cdk import Tags
from infrastructure.opensearch_nextgen_stack import OpensearchNextgenStack
from infrastructure.knowledge_base_stack import KnowledgeBaseStack
from infrastructure.agentcore_stack import AgentCoreStack
from infrastructure.cloudfront_hosting_stack import CloudFrontHostingStack

app = cdk.App()

account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
region = os.getenv("CDK_DEFAULT_REGION")
env = cdk.Environment(account=account_id, region=region)
env_name = app.node.try_get_context("environment_name")

# Stack 1: AOSS Collection + Index (deployed independently, survives downstream failures)
kb_role_arn = f"arn:aws:iam::{account_id}:role/srd-kb-role-{env_name}"
oss_stack = OpensearchNextgenStack(
    app, f"SRD-AOSS-{env_name}",
    kb_role_arn=kb_role_arn,
    env=env,
)
Tags.of(oss_stack).add("project", "serverless-rag-demo-v2")

# Stack 2: Bedrock Knowledge Base
kb_stack = KnowledgeBaseStack(
    app, f"SRD-KB-{env_name}",
    collection_arn=oss_stack.collection_arn,
    collection_endpoint=oss_stack.collection_endpoint,
    env=env,
)
kb_stack.add_dependency(oss_stack)
Tags.of(kb_stack).add("project", "serverless-rag-demo-v2")

# Stack 3: AgentCore Runtimes
agentcore_stack = AgentCoreStack(
    app, f"SRD-AgentCore-{env_name}",
    knowledge_base_id=kb_stack.knowledge_base_id,
    data_bucket_name=kb_stack.data_bucket_name,
    collection_endpoint=oss_stack.collection_endpoint,
    env=env,
)
agentcore_stack.add_dependency(kb_stack)
Tags.of(agentcore_stack).add("project", "serverless-rag-demo-v2")

# Stack 4: CloudFront Hosting
cf_stack = CloudFrontHostingStack(
    app, f"SRD-CloudFront-{env_name}",
    cognito_user_pool_id="PLACEHOLDER",
    cognito_client_id="PLACEHOLDER",
    rest_endpoint_url=f"https://placeholder.execute-api.{region}.amazonaws.com/{env_name}/rag/",
    websocket_url=f"wss://placeholder.execute-api.{region}.amazonaws.com/{env_name}",
    env=env,
)
cf_stack.add_dependency(agentcore_stack)
Tags.of(cf_stack).add("project", "serverless-rag-demo-v2")

app.synth()
