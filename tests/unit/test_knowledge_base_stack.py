import aws_cdk as cdk
from aws_cdk.assertions import Template
from infrastructure.knowledge_base_stack import KnowledgeBaseStack
import os


def test_creates_kb_role(app, stack):
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    nested = KnowledgeBaseStack(stack, "TestKB",
        collection_arn="arn:aws:aoss:us-east-1:123456789012:collection/abc123",
        collection_endpoint="https://abc123.us-east-1.aoss.amazonaws.com")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::IAM::Role", 1)


def test_creates_s3_bucket(app, stack):
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    nested = KnowledgeBaseStack(stack, "TestKB2",
        collection_arn="arn:aws:aoss:us-east-1:123456789012:collection/abc123",
        collection_endpoint="https://abc123.us-east-1.aoss.amazonaws.com")
    template = Template.from_stack(nested)
    template.has_resource_properties("AWS::S3::Bucket", {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "BlockPublicPolicy": True,
            "IgnorePublicAcls": True,
            "RestrictPublicBuckets": True,
        }
    })


def test_creates_knowledge_base(app, stack):
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    nested = KnowledgeBaseStack(stack, "TestKB3",
        collection_arn="arn:aws:aoss:us-east-1:123456789012:collection/abc123",
        collection_endpoint="https://abc123.us-east-1.aoss.amazonaws.com")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::Bedrock::KnowledgeBase", 1)
