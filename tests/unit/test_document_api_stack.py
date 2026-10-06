"""Regression tests for per-user document isolation.

These pin the two halves of the fix: the browser-held role must not be able to
reach documents/* at all, and the API handler must derive identity from the
verified JWT claim rather than anything the caller supplies.
"""

import importlib
import json
import os
import sys

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from infrastructure.cognito_stack import CognitoStack
from infrastructure.document_api_stack import DocumentApiStack


def _document_api_template(stack):
    return Template.from_stack(DocumentApiStack(
        stack, "TestDocApi",
        user_pool_id="us-east-1_abc123",
        user_pool_client_id="client-456",
        data_bucket_name="srd-data-bucket",
        knowledge_base_id="KB123456",
        data_source_id="DS123456",
    ))


def test_authenticated_role_cannot_reach_user_documents(app, stack):
    """The reported vulnerability: a browser-held role with documents/* access."""
    template = Template.from_stack(CognitoStack(
        stack, "TestAuth",
        data_bucket_name="srd-data-bucket",
        knowledge_base_id="KB123456",
    ))
    rendered = json.dumps(template.to_json())
    assert "documents/" not in rendered
    # Knowledge Base ingestion was reachable from the browser via the same role.
    assert "StartIngestionJob" not in rendered


def test_every_document_route_requires_a_verified_jwt(app, stack):
    template = _document_api_template(stack)
    routes = [
        r["Properties"] for r in template.to_json()["Resources"].values()
        if r["Type"] == "AWS::ApiGatewayV2::Route"
    ]
    assert len(routes) == 6
    for route in routes:
        assert route["AuthorizationType"] == "JWT", route["RouteKey"]
        assert "AuthorizerId" in route, route["RouteKey"]


def test_authorizer_is_bound_to_the_user_pool(app, stack):
    _document_api_template(stack).has_resource_properties(
        "AWS::ApiGatewayV2::Authorizer",
        {
            "AuthorizerType": "JWT",
            "IdentitySource": ["$request.header.Authorization"],
        },
    )


# --- handler authorisation logic ---------------------------------------------

@pytest.fixture(scope="module")
def documents():
    """Import the Lambda handler with the env vars it reads at module scope."""
    os.environ.setdefault("REGION", "us-east-1")
    os.environ.setdefault("DATA_BUCKET_NAME", "srd-data-bucket")
    os.environ.setdefault("KNOWLEDGE_BASE_ID", "KB123456")
    os.environ.setdefault("DATA_SOURCE_ID", "DS123456")
    sys.path.insert(0, os.path.join("infrastructure", "lambdas", "documents"))
    try:
        return importlib.import_module("index")
    finally:
        sys.path.pop(0)


def _event(email, verified=True):
    return {"requestContext": {"authorizer": {"jwt": {"claims": {
        "email": email, "email_verified": verified,
    }}}}}


def test_caller_email_comes_from_the_verified_claim(documents):
    assert documents._caller_email(_event("alice@example.com")) == "alice@example.com"


@pytest.mark.parametrize("event", [
    {},
    {"requestContext": {"authorizer": {"jwt": {"claims": {}}}}},
    _event("alice@example.com", verified=False),
])
def test_caller_email_rejects_missing_or_unverified_claims(documents, event):
    with pytest.raises(documents.Forbidden):
        documents._caller_email(event)


def test_assert_owned_rejects_another_users_key(documents):
    with pytest.raises(documents.Forbidden):
        documents._assert_owned(
            "alice@example.com", "documents/bob@example.com/secret.txt")


def test_assert_owned_accepts_own_key(documents):
    key = "documents/alice@example.com/notes.txt"
    assert documents._assert_owned("alice@example.com", key) == key


@pytest.mark.parametrize("file_name", [
    "../bob@example.com/secret.txt",
    "../../etc/passwd",
    "a/b.txt",
    "",
    "notes.metadata.json",
])
def test_own_key_rejects_traversal_and_metadata_overwrites(documents, file_name):
    with pytest.raises(documents.BadRequest):
        documents._own_key("alice@example.com", file_name)


def test_own_key_builds_a_prefixed_key(documents):
    assert documents._own_key("alice@example.com", "notes.txt") == \
        "documents/alice@example.com/notes.txt"
