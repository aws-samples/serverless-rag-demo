import json
import os

import pytest
from aws_cdk.assertions import Template

from infrastructure.agentcore_stack import AgentCoreStack

DATA_BUCKET = "srd-store-test-123-us-east-1"


@pytest.fixture
def template(app, stack):
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    return Template.from_stack(AgentCoreStack(
        stack, "TestAC",
        knowledge_base_id="kb-123",
        data_bucket_name=DATA_BUCKET,
        collection_endpoint="https://abc.aoss.amazonaws.com",
    ))


def _as_list(value):
    """CDK collapses a single-element Action or Resource list into a string."""
    return value if isinstance(value, list) else [value]


def _role_statements(template, policy_name):
    for resource in template.to_json()["Resources"].values():
        if resource["Type"] != "AWS::IAM::Role":
            continue
        for policy in resource["Properties"].get("Policies", []):
            if policy["PolicyName"] == policy_name:
                return policy["PolicyDocument"]["Statement"]
    raise AssertionError(f"no role carries a {policy_name} policy")


def test_creates_iam_roles(template):
    # Multi-agent runtime, RAG query runtime, and the Web Search Gateway.
    template.resource_count_is("AWS::IAM::Role", 3)


def test_multi_agent_role_has_bedrock_permissions(template):
    actions = {
        action
        for statement in _role_statements(template, "MultiAgentPolicy")
        for action in _as_list(statement["Action"])
    }
    assert "bedrock:InvokeModel" in actions
    assert "bedrock:Retrieve" in actions


# --- the runtime's own S3 reach -----------------------------------------------

def test_multi_agent_role_cannot_touch_user_documents(template):
    """A prompt-injected document must not be able to reach the corpus.

    The sidecars under documents/ are what the Knowledge Base filters ownership
    on, so write access to them would undo per-user isolation regardless of what
    the API handler enforces.
    """
    artefacts = [
        s for s in _role_statements(template, "MultiAgentPolicy")
        if s.get("Sid") == "GeneratedArtefacts"
    ]
    assert len(artefacts) == 1
    assert sorted(_as_list(artefacts[0]["Resource"])) == [
        f"arn:aws:s3:::{DATA_BUCKET}/generated-code/*",
        f"arn:aws:s3:::{DATA_BUCKET}/generated-ppt/*",
    ]

    s3_resources = [
        resource
        for statement in _role_statements(template, "MultiAgentPolicy")
        for resource in _as_list(statement["Resource"])
        if isinstance(resource, str) and resource.startswith("arn:aws:s3:")
    ]
    assert f"arn:aws:s3:::{DATA_BUCKET}/*" not in s3_resources
    assert not any("documents/" in r for r in s3_resources)


# --- the Web Search Gateway ---------------------------------------------------

def test_the_only_outbound_reach_is_the_managed_web_search_tool(template):
    """Web research used to be an arbitrary-URL fetch; it is now one service ARN."""
    statements = _role_statements(template, "WebSearchGatewayPolicy")
    by_sid = {s["Sid"]: s for s in statements}
    assert set(by_sid) == {"InvokeGateway", "InvokeWebSearch"}
    assert _as_list(by_sid["InvokeWebSearch"]["Action"]) == \
        ["bedrock-agentcore:InvokeWebSearch"]
    assert _as_list(by_sid["InvokeWebSearch"]["Resource"]) == \
        ["arn:aws:bedrock-agentcore:us-east-1:aws:tool/web-search.v1"]


def test_the_gateway_role_can_only_be_assumed_by_our_own_gateways(template):
    for resource in template.to_json()["Resources"].values():
        if resource["Type"] != "AWS::IAM::Role":
            continue
        if not any(
            p["PolicyName"] == "WebSearchGatewayPolicy"
            for p in resource["Properties"].get("Policies", [])
        ):
            continue
        assume = resource["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
        assert assume["Principal"] == \
            {"Service": "bedrock-agentcore.amazonaws.com"}
        # Without these a confused-deputy call from another account's gateway
        # would be able to borrow the role.
        assert assume["Condition"]["StringEquals"]["aws:SourceAccount"] == \
            "123456789012"
        assert "gateway/*" in assume["Condition"]["ArnLike"]["aws:SourceArn"]
        return
    raise AssertionError("no gateway service role in the template")


def test_the_runtime_may_invoke_the_gateway(template):
    invoke = [
        s for s in _role_statements(template, "MultiAgentPolicy")
        if s.get("Sid") == "InvokeWebSearchGateway"
    ]
    assert len(invoke) == 1
    assert _as_list(invoke[0]["Action"]) == ["bedrock-agentcore:InvokeGateway"]


def test_the_rag_query_runtime_gets_no_s3_and_no_gateway(template):
    """It only retrieves and generates, so neither belongs on its role."""
    policy = json.dumps(_role_statements(template, "RAGQueryPolicy"))
    assert "s3:" not in policy
    assert "bedrock-agentcore:" not in policy
