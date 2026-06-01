#!/usr/bin/env python3
import os
import aws_cdk as cdk
from aws_cdk import Tags
from llms_with_serverless_rag.llms_with_serverless_rag_stack import LlmsWithServerlessRagStack

app = cdk.App()

account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
region = os.getenv("CDK_DEFAULT_REGION")
env = cdk.Environment(account=account_id, region=region)
env_name = app.node.try_get_context("environment_name")

stack = LlmsWithServerlessRagStack(app, f"ServerlessRagV2-{env_name}", env=env)
Tags.of(stack).add("project", "serverless-rag-demo-v2")

app.synth()
