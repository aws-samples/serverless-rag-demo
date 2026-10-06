"""Regression tests for per-user isolation of documents, evaluations and feedback.

These pin both halves of the fix: the browser-held Cognito role must not be able
to reach any of that data, and the API handler must derive identity from the
verified JWT claim rather than from anything the caller supplies.
"""

import importlib
import json
import os
import sys

import pytest
from aws_cdk.assertions import Template

from infrastructure.app_api_stack import AppApiStack
from infrastructure.cognito_stack import CognitoStack

LAMBDA_SRC = os.path.join("infrastructure", "lambdas", "api")


def _app_api_template(stack):
    return Template.from_stack(AppApiStack(
        stack, "TestAppApi",
        user_pool_id="us-east-1_abc123",
        user_pool_client_id="client-456",
        data_bucket_name="srd-data-bucket",
        knowledge_base_id="KB123456",
        data_source_id="DS123456",
        eval_role_arn="arn:aws:iam::123456789012:role/srd-eval-service-role-test",
    ))


def _roles(template):
    return [
        r["Properties"] for r in template.to_json()["Resources"].values()
        if r["Type"] == "AWS::IAM::Role"
    ]


def _authenticated_role(template):
    """The role the Identity Pool hands to browsers."""
    for role in _roles(template):
        principals = [
            s.get("Principal", {})
            for s in role["AssumeRolePolicyDocument"]["Statement"]
        ]
        if any(p.get("Federated") == "cognito-identity.amazonaws.com" for p in principals):
            return role
    raise AssertionError("no Cognito-federated role in the template")


def _statements(role):
    return [
        statement
        for policy in role.get("Policies", [])
        for statement in policy["PolicyDocument"]["Statement"]
    ]


# --- the browser-held role ----------------------------------------------------

def test_authenticated_role_grants_nothing_but_agentcore(app, stack):
    """The browser role is the whole attack surface, so enumerate it exactly."""
    template = Template.from_stack(CognitoStack(
        stack, "TestAuth",
        data_bucket_name="srd-data-bucket",
        knowledge_base_id="KB123456",
    ))
    role = _authenticated_role(template)

    assert [p["PolicyName"] for p in role["Policies"]] == ["AgentCoreInvoke"]
    actions = sorted(
        action
        for statement in _statements(role)
        for action in statement["Action"]
    )
    assert actions == [
        "bedrock-agentcore:InvokeAgentRuntime",
        "bedrock-agentcore:InvokeAgentRuntimeWithWebSocketStream",
    ]
    assert role.get("ManagedPolicyArns", []) == []


@pytest.mark.parametrize("grant", [
    # The reported vulnerability: cross-user document read, write and delete.
    "documents/",
    "StartIngestionJob",
    # Same class of problem — CreateEvaluationJob cannot be scoped to a resource,
    # so on a browser role it covered every job in the account.
    "CreateEvaluationJob",
    "ListEvaluationJobs",
    "iam:PassRole",
    # Feedback was a read-modify-write of one shared file per day.
    "feedback/",
])
def test_authenticated_role_is_free_of_per_user_grants(app, stack, grant):
    template = Template.from_stack(CognitoStack(
        stack, "TestAuth",
        data_bucket_name="srd-data-bucket",
        knowledge_base_id="KB123456",
    ))
    assert grant not in json.dumps(_authenticated_role(template))


# --- the API surface ----------------------------------------------------------

def test_every_route_requires_a_verified_jwt(app, stack):
    template = _app_api_template(stack)
    routes = [
        r["Properties"] for r in template.to_json()["Resources"].values()
        if r["Type"] == "AWS::ApiGatewayV2::Route"
    ]
    assert len(routes) == 11
    for route in routes:
        assert route["AuthorizationType"] == "JWT", route["RouteKey"]
        assert "AuthorizerId" in route, route["RouteKey"]


def test_authorizer_is_bound_to_the_user_pool(app, stack):
    _app_api_template(stack).has_resource_properties(
        "AWS::ApiGatewayV2::Authorizer",
        {
            "AuthorizerType": "JWT",
            "IdentitySource": ["$request.header.Authorization"],
        },
    )


def test_handler_role_scopes_what_iam_can_scope(app, stack):
    """Only the two actions with no resource-level support may use "*"."""
    role = _roles(_app_api_template(stack))[0]
    wildcarded = sorted(
        action
        for statement in _statements(role)
        if statement["Resource"] == "*"
        for action in statement["Action"]
    )
    assert wildcarded == [
        "bedrock:CreateEvaluationJob",
        "bedrock:ListEvaluationJobs",
    ]


def test_handler_role_can_only_pass_the_eval_role_to_bedrock(app, stack):
    role = _roles(_app_api_template(stack))[0]
    pass_role = [s for s in _statements(role) if s.get("Sid") == "PassEvalRole"]
    assert len(pass_role) == 1
    assert pass_role[0]["Resource"] == \
        "arn:aws:iam::123456789012:role/srd-eval-service-role-test"
    assert pass_role[0]["Condition"] == \
        {"StringEquals": {"iam:PassedToService": "bedrock.amazonaws.com"}}


# --- handler authorisation logic ---------------------------------------------

@pytest.fixture(scope="module")
def api():
    """Import the Lambda package with the env vars it reads at module scope."""
    os.environ.setdefault("REGION", "us-east-1")
    os.environ.setdefault("DATA_BUCKET_NAME", "srd-data-bucket")
    os.environ.setdefault("KNOWLEDGE_BASE_ID", "KB123456")
    os.environ.setdefault("DATA_SOURCE_ID", "DS123456")
    os.environ.setdefault("EVAL_ROLE_ARN", "arn:aws:iam::123456789012:role/eval")
    os.environ.setdefault("EVALUATOR_MODEL_ARN", "arn:aws:bedrock:us-east-1::foundation-model/x")
    os.environ.setdefault("GENERATOR_MODEL_ARN", "global.anthropic.claude-sonnet-4-6")
    sys.path.insert(0, LAMBDA_SRC)
    try:
        return {
            name: importlib.import_module(name)
            for name in ("common", "documents", "evaluations", "feedback", "index")
        }
    finally:
        sys.path.pop(0)


@pytest.fixture(scope="module")
def common(api):
    return api["common"]


def _event(email, verified=True):
    return {"requestContext": {"authorizer": {"jwt": {"claims": {
        "email": email, "email_verified": verified,
    }}}}}


def test_caller_email_comes_from_the_verified_claim(common):
    assert common.caller_email(_event("alice@example.com")) == "alice@example.com"


@pytest.mark.parametrize("event", [
    {},
    {"requestContext": {"authorizer": {"jwt": {"claims": {}}}}},
    _event("alice@example.com", verified=False),
])
def test_caller_email_rejects_missing_or_unverified_claims(common, event):
    with pytest.raises(common.Forbidden):
        common.caller_email(event)


def test_every_route_is_reachable_and_unknown_routes_are_not(api):
    """A route added to the stack but not the router would 404 in production."""
    assert set(api["index"].ROUTES) == {
        "GET /documents",
        "POST /documents/upload-url",
        "POST /documents/download-url",
        "DELETE /documents",
        "POST /documents/sync",
        "GET /documents/ingestion-status",
        "POST /evaluations",
        "GET /evaluations",
        "GET /evaluations/status",
        "GET /evaluations/results",
        "POST /feedback",
    }


# --- documents ----------------------------------------------------------------

def test_assert_owned_rejects_another_users_key(api, common):
    with pytest.raises(common.Forbidden):
        api["documents"].assert_owned(
            "alice@example.com", "documents/bob@example.com/secret.txt")


def test_assert_owned_accepts_own_key(api):
    key = "documents/alice@example.com/notes.txt"
    assert api["documents"].assert_owned("alice@example.com", key) == key


@pytest.mark.parametrize("file_name", [
    "../bob@example.com/secret.txt",
    "../../etc/passwd",
    "a/b.txt",
    "",
    "notes.metadata.json",
])
def test_own_key_rejects_traversal_and_metadata_overwrites(api, common, file_name):
    with pytest.raises(common.BadRequest):
        api["documents"].own_key("alice@example.com", file_name)


def test_own_key_builds_a_prefixed_key(api):
    assert api["documents"].own_key("alice@example.com", "notes.txt") == \
        "documents/alice@example.com/notes.txt"


# --- evaluations --------------------------------------------------------------

def test_job_names_and_prefixes_differ_per_user(api):
    evaluations = api["evaluations"]
    alice = evaluations._job_name_prefix("alice@example.com")
    bob = evaluations._job_name_prefix("bob@example.com")
    assert alice != bob
    # The tag stands in for the address rather than embedding it.
    assert "alice@example.com" not in alice
    assert evaluations._job_prefix("alice@example.com", "a" * 16).startswith(
        "evaluations/")
    assert evaluations._job_prefix("alice@example.com", "a" * 16) != \
        evaluations._job_prefix("bob@example.com", "a" * 16)


def test_evaluation_status_refuses_another_users_job(api, common, monkeypatch):
    evaluations = api["evaluations"]
    other = f"{evaluations._job_name_prefix('bob@example.com')}{'b' * 16}"

    class FakeBedrock:
        def get_evaluation_job(self, jobIdentifier):
            return {"jobName": other, "status": "Completed"}

    monkeypatch.setattr(evaluations, "bedrock", FakeBedrock())
    event = {"queryStringParameters": {
        "jobArn": "arn:aws:bedrock:us-east-1:123456789012:evaluation-job/abc123def456",
    }}
    with pytest.raises(common.Forbidden):
        evaluations.evaluation_status(event, "alice@example.com")


@pytest.mark.parametrize("job_arn", [
    None,
    "not-an-arn",
    # A caller-supplied identifier must not be able to reach another service.
    "arn:aws:iam::123456789012:role/admin",
    "arn:aws:bedrock:us-east-1:123456789012:evaluation-job/../../other",
])
def test_evaluation_status_rejects_malformed_identifiers(api, common, job_arn):
    event = {"queryStringParameters": {"jobArn": job_arn}}
    with pytest.raises(common.BadRequest):
        api["evaluations"].evaluation_status(event, "alice@example.com")


@pytest.mark.parametrize("job_id", [None, "", "../../bob", "zzz", "a" * 15])
def test_result_job_ids_must_be_opaque_tokens(api, common, job_id):
    """The job id lands in an S3 key, so it is validated before use."""
    with pytest.raises(common.BadRequest):
        api["evaluations"]._own_token(job_id)


@pytest.mark.parametrize("metrics", [
    None, [], "Builtin.Correctness", ["Builtin.Nonexistent"],
])
def test_metrics_are_restricted_to_the_allowlist(api, common, metrics):
    with pytest.raises(common.BadRequest):
        api["evaluations"]._metrics({"metrics": metrics})


# --- feedback -----------------------------------------------------------------

def test_feedback_is_stamped_with_the_verified_email(api, monkeypatch):
    feedback = api["feedback"]
    written = {}

    def fake_put_object(**kwargs):
        written.update(kwargs)
        return {}

    monkeypatch.setattr(feedback.s3, "put_object", fake_put_object)
    feedback.submit_feedback(
        {"body": json.dumps({
            "rating": "up",
            "question": "q",
            "answer": "a",
            # A caller claiming to be someone else must not be believed.
            "userEmail": "bob@example.com",
            "timestamp": "1999-01-01T00:00:00Z",
        })},
        "alice@example.com",
    )

    entry = json.loads(written["Body"])
    assert entry["userEmail"] == "alice@example.com"
    assert entry["timestamp"] != "1999-01-01T00:00:00Z"
    # One object per submission, so there is no shared file to read or clobber.
    assert written["Key"].startswith("feedback/")
    assert written["Key"].endswith(".json")


@pytest.mark.parametrize("rating", [None, "", "UP", "maybe", 1])
def test_feedback_rejects_an_unknown_rating(api, common, rating):
    with pytest.raises(common.BadRequest):
        api["feedback"].submit_feedback(
            {"body": json.dumps({"rating": rating})}, "alice@example.com")
