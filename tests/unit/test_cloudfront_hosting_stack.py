import aws_cdk as cdk
from aws_cdk.assertions import Template
from infrastructure.cloudfront_hosting_stack import CloudFrontHostingStack
import os

# Prevent CDK from trying to run Docker during unit tests
os.environ["CDK_BUNDLING_STUBS"] = "true"


def test_creates_s3_bucket(app, stack):
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    nested = CloudFrontHostingStack(stack, "TestCF",
        cognito_user_pool_id="pool-123",
        cognito_client_id="client-456",
        rest_endpoint_url="https://api.example.com/test/rag/",
        websocket_url="wss://ws.example.com/test")
    template = Template.from_stack(nested)
    template.has_resource_properties("AWS::S3::Bucket", {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "BlockPublicPolicy": True,
            "IgnorePublicAcls": True,
            "RestrictPublicBuckets": True,
        }
    })


def test_creates_cloudfront_distribution(app, stack):
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    nested = CloudFrontHostingStack(stack, "TestCF2",
        cognito_user_pool_id="pool-123",
        cognito_client_id="client-456",
        rest_endpoint_url="https://api.example.com/test/rag/",
        websocket_url="wss://ws.example.com/test")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::CloudFront::Distribution", 1)
