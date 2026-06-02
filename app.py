#!/usr/bin/env python3
import os
import aws_cdk as cdk
from aws_cdk import Tags
from infrastructure.opensearch_nextgen_stack import OpensearchNextgenStack
from infrastructure.knowledge_base_stack import KnowledgeBaseStack
from infrastructure.agentcore_stack import AgentCoreStack
from infrastructure.cognito_stack import CognitoStack
from infrastructure.cloudfront_hosting_stack import CloudFrontHostingStack

app = cdk.App()

account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
region = os.getenv("CDK_DEFAULT_REGION")
env = cdk.Environment(account=account_id, region=region)
env_name = app.node.try_get_context("environment_name")

# Stack 1: AOSS Collection + Index Creator Lambda
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

# Stack 4: Cognito Auth
cognito_stack = CognitoStack(
    app, f"SRD-Auth-{env_name}",
    data_bucket_name=kb_stack.data_bucket_name,
    knowledge_base_id=kb_stack.knowledge_base_id,
    data_source_id=kb_stack.data_source_id,
    env=env,
)
cognito_stack.add_dependency(kb_stack)
Tags.of(cognito_stack).add("project", "serverless-rag-demo-v2")

# Stack 5: CloudFront Hosting (depends on Cognito for runtime-config)
cf_stack = CloudFrontHostingStack(
    app, f"SRD-CloudFront-{env_name}",
    cognito_user_pool_id=cognito_stack.user_pool_id,
    cognito_client_id=cognito_stack.client_id,
    cognito_identity_pool_id=cognito_stack.identity_pool_id,
    env=env,
)
cf_stack.add_dependency(cognito_stack)
cf_stack.add_dependency(agentcore_stack)
Tags.of(cf_stack).add("project", "serverless-rag-demo-v2")

# Stack 6 (optional): Hive Multi-Agent Platform
hive_enabled = app.node.try_get_context("hive_enabled") == "true"
if hive_enabled:
    from infrastructure.hive_stack import HiveStack
    hive_stack = HiveStack(
        app, f"SRD-Hive-{env_name}",
        cognito_identity_pool_id=cognito_stack.identity_pool_id,
        env=env,
    )
    hive_stack.add_dependency(cognito_stack)
    Tags.of(hive_stack).add("project", "serverless-rag-demo-v2")

app.synth()
