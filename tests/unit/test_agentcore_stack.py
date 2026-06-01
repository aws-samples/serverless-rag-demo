import aws_cdk as cdk
from aws_cdk.assertions import Template
from infrastructure.agentcore_stack import AgentCoreStack
import os


def test_creates_iam_roles(app, stack):
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    nested = AgentCoreStack(stack, "TestAC",
        knowledge_base_id="kb-123",
        data_bucket_name="srd-store-test-123-us-east-1",
        collection_endpoint="https://abc.aoss.amazonaws.com")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::IAM::Role", 2)


def test_multi_agent_role_has_bedrock_permissions(app, stack):
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    nested = AgentCoreStack(stack, "TestAC2",
        knowledge_base_id="kb-123",
        data_bucket_name="srd-store-test-123-us-east-1",
        collection_endpoint="https://abc.aoss.amazonaws.com")
    template = Template.from_stack(nested)
    template.has_resource_properties("AWS::IAM::Role", {
        "Policies": [{
            "PolicyName": "MultiAgentPolicy",
        }]
    })
