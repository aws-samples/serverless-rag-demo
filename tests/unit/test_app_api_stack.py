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


def test_the_shared_corpus_group_exists_and_starts_empty(app, stack):
    """Cross-user listing is opt-in, so no one is in the group on a fresh deploy."""
    from infrastructure.cognito_stack import SHARED_CORPUS_GROUP

    template = Template.from_stack(CognitoStack(
        stack, "TestAuth",
        data_bucket_name="srd-data-bucket",
        knowledge_base_id="KB123456",
    ))
    groups = [
        r["Properties"] for r in template.to_json()["Resources"].values()
        if r["Type"] == "AWS::Cognito::UserPoolGroup"
    ]
    assert [g["GroupName"] for g in groups] == [SHARED_CORPUS_GROUP]
    # Membership is granted deliberately; nothing here puts a user in it.
    assert "AWS::Cognito::UserPoolUserToGroupAttachment" not in \
        json.dumps(template.to_json())


def test_the_group_name_is_the_same_everywhere(app, stack, common):
    """Three copies of the name decide the same thing and must not drift."""
    from infrastructure.cognito_stack import SHARED_CORPUS_GROUP

    assert common.SHARED_CORPUS_GROUP == SHARED_CORPUS_GROUP
    _app_api_template(stack).has_resource_properties("AWS::Lambda::Function", {
        "Environment": {"Variables": {"SHARED_CORPUS_GROUP": SHARED_CORPUS_GROUP}},
    })

    with open(os.path.join("containers", "rag-query", "auth.py")) as f:
        assert f'"{SHARED_CORPUS_GROUP}"' in f.read()
    with open(os.path.join(
            "artifacts", "chat-ui", "src", "common", "groups.ts")) as f:
        assert f'"{SHARED_CORPUS_GROUP}"' in f.read()


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


def _event(email, verified=True, groups=None):
    claims = {"email": email, "email_verified": verified}
    if groups is not None:
        claims["cognito:groups"] = groups
    return {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}}


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


@pytest.mark.parametrize("groups, expected", [
    (["corpus-readers"], True),
    (["other", "corpus-readers"], True),
    # API Gateway flattens the array to a bracketed string in payload 1.0.
    ("[corpus-readers]", True),
    ("[other corpus-readers]", True),
    ("other,corpus-readers", True),
    (["corpus-reader"], False),
    ([], False),
    ("", False),
    ("[]", False),
    (None, False),
])
def test_shared_corpus_membership_is_read_from_the_claim(common, groups, expected):
    event = _event("alice@example.com", groups=groups)
    assert common.may_read_shared_corpus(event) is expected


def test_group_membership_cannot_be_asserted_by_the_caller(common):
    """The group must come from the claim, not from anything in the request."""
    event = _event("alice@example.com")
    event["queryStringParameters"] = {"cognito:groups": "corpus-readers"}
    event["body"] = json.dumps({"cognito:groups": ["corpus-readers"]})
    event["headers"] = {"cognito:groups": "corpus-readers"}
    assert common.may_read_shared_corpus(event) is False


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


@pytest.mark.parametrize("groups", [None, [], ["other"], "[other]"])
def test_listing_all_owners_requires_the_group(api, common, groups):
    with pytest.raises(common.Forbidden):
        api["documents"].list_documents(
            {**_event("alice@example.com", groups=groups),
             "queryStringParameters": {"scope": "all"}},
            "alice@example.com",
        )


def _listing(api, monkeypatch, event):
    """Run list_documents against a stubbed bucket and return the keys listed."""
    seen = {}

    class FakePaginator:
        def paginate(self, **kwargs):
            seen.update(kwargs)
            return [{"Contents": [
                {"Key": "documents/alice@example.com/mine.txt", "Size": 1},
                {"Key": "documents/bob@example.com/theirs.txt", "Size": 2},
            ]}]

    monkeypatch.setattr(api["documents"].s3, "get_paginator",
                        lambda _name: FakePaginator())
    result = api["documents"].list_documents(event, "alice@example.com")
    return seen, json.loads(result["body"])["documents"]


def test_listing_defaults_to_the_callers_own_prefix(api, monkeypatch):
    seen, documents = _listing(api, monkeypatch, _event("alice@example.com"))
    assert seen["Prefix"] == "documents/alice@example.com/"
    assert all(d["isOwner"] for d in documents if d["userEmail"] == "alice@example.com")


def test_a_group_member_may_list_every_owner(api, monkeypatch):
    event = {**_event("alice@example.com", groups=["corpus-readers"]),
             "queryStringParameters": {"scope": "all"}}
    seen, documents = _listing(api, monkeypatch, event)
    assert seen["Prefix"] == "documents/"
    # Names and owners only — content still needs assert_owned.
    assert {d["userEmail"] for d in documents} == \
        {"alice@example.com", "bob@example.com"}
    assert [d["isOwner"] for d in documents] == [True, False]


@pytest.mark.parametrize("scope", ["everything", "ALL", "mine ", 1])
def test_listing_rejects_an_unknown_scope(api, common, scope):
    with pytest.raises(common.BadRequest):
        api["documents"].list_documents(
            {**_event("alice@example.com"),
             "queryStringParameters": {"scope": scope}},
            "alice@example.com",
        )


@pytest.mark.parametrize("content_length", [
    None, "1024", 0, -1, True, 1.5,
    # A presigned PUT is otherwise unbounded.
    50 * 1024 * 1024 + 1,
])
def test_upload_size_must_be_a_sane_integer(api, common, content_length):
    with pytest.raises(common.BadRequest):
        api["documents"]._content_length({"contentLength": content_length})


def test_upload_url_signs_the_declared_length(api, monkeypatch):
    documents = api["documents"]
    signed = {}

    def fake_presign(operation, Params, ExpiresIn):
        signed.update(Params)
        return "https://example.invalid/put"

    monkeypatch.setattr(documents.s3, "generate_presigned_url", fake_presign)
    monkeypatch.setattr(documents.s3, "put_object", lambda **kwargs: {})

    documents.create_upload_url(
        {**_event("alice@example.com"), "body": json.dumps({
            "fileName": "notes.txt",
            "contentType": "text/plain",
            "contentLength": 1024,
        })},
        "alice@example.com",
    )
    # Signed, so the URL cannot be replayed with a body of a different size.
    assert signed["ContentLength"] == 1024
    assert signed["Key"] == "documents/alice@example.com/notes.txt"


def test_upload_url_stamps_the_sidecar_with_the_verified_email(api, monkeypatch):
    documents = api["documents"]
    written = {}

    monkeypatch.setattr(documents.s3, "generate_presigned_url",
                        lambda *a, **k: "https://example.invalid/put")
    monkeypatch.setattr(documents.s3, "put_object",
                        lambda **kwargs: written.update(kwargs) or {})

    documents.create_upload_url(
        {**_event("alice@example.com"), "body": json.dumps({
            "fileName": "notes.txt",
            "contentLength": 1024,
            # A caller tagging their upload as someone else must not be believed:
            # this attribute is what the Knowledge Base filters retrieval on.
            "userEmail": "bob@example.com",
        })},
        "alice@example.com",
    )
    sidecar = json.loads(written["Body"])
    assert sidecar["metadataAttributes"]["user_email"] == "alice@example.com"
    assert written["Key"] == "documents/alice@example.com/notes.txt.metadata.json"


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
