import aws_cdk as cdk
from aws_cdk.assertions import Template
from infrastructure.opensearch_nextgen_stack import OpensearchNextgenStack
import os


def test_creates_collection(app, stack):
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    nested = OpensearchNextgenStack(stack, "TestAOSS2")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::OpenSearchServerless::Collection", 1)


def test_creates_security_policies(app, stack):
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    nested = OpensearchNextgenStack(stack, "TestAOSS3")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::OpenSearchServerless::SecurityPolicy", 2)


def test_creates_access_policy(app, stack):
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    nested = OpensearchNextgenStack(stack, "TestAOSS4")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::OpenSearchServerless::AccessPolicy", 1)


def test_collection_is_vectorsearch_type(app, stack):
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    nested = OpensearchNextgenStack(stack, "TestAOSS5")
    template = Template.from_stack(nested)
    template.has_resource_properties("AWS::OpenSearchServerless::Collection", {
        "Type": "VECTORSEARCH",
        "Name": "srd-vectors-test",
    })


def test_exposes_collection_endpoint(app, stack):
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    nested = OpensearchNextgenStack(stack, "TestAOSS6")
    assert nested.collection_endpoint is not None
    assert nested.collection_name == "srd-vectors-test"
