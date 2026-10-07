import json

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


def _kb_template(stack, construct_id):
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    return Template.from_stack(KnowledgeBaseStack(stack, construct_id,
        collection_arn="arn:aws:aoss:us-east-1:123456789012:collection/abc123",
        collection_endpoint="https://abc123.us-east-1.aoss.amazonaws.com"))


def _buckets(template):
    return [
        r["Properties"] for r in template.to_json()["Resources"].values()
        if r["Type"] == "AWS::S3::Bucket"
    ]


def _data_bucket(template):
    for bucket in _buckets(template):
        if "BucketName" in bucket:
            return bucket
    raise AssertionError("no named data bucket in the template")


def test_the_data_bucket_is_versioned_and_logged(app, stack):
    """Documents and their ownership sidecars must be recoverable and auditable.

    S3 server access logging is the only record of who read or wrote another
    user's document, which is exactly what this app needs to reconstruct.
    """
    bucket = _data_bucket(_kb_template(stack, "TestKBAudit"))
    assert bucket["VersioningConfiguration"] == {"Status": "Enabled"}
    assert bucket["LoggingConfiguration"]["LogFilePrefix"] == "data-bucket/"
    assert "DestinationBucketName" in bucket["LoggingConfiguration"]


def test_the_browser_may_only_put_cross_origin(app, stack):
    """Reads, deletes and listing go through the API with the ID token.

    A permissive CORS rule is what made the bucket reachable from the page in the
    first place, so it is narrowed to the one operation the upload flow needs.
    """
    rules = _data_bucket(_kb_template(stack, "TestKBCors"))[
        "CorsConfiguration"]["CorsRules"]
    assert len(rules) == 1
    assert sorted(rules[0]["AllowedMethods"]) == ["HEAD", "PUT"]


def test_the_ingestion_role_can_only_read_documents(app, stack):
    """The data source only ingests documents/, so that is all it may read.

    Evaluation output, feedback and generated artefacts share this bucket and are
    none of the ingestion role's business.
    """
    template = _kb_template(stack, "TestKBRole")
    statements = [
        s
        for r in template.to_json()["Resources"].values()
        if r["Type"] == "AWS::IAM::Role"
        for p in r["Properties"].get("Policies", [])
        for s in p["PolicyDocument"]["Statement"]
    ]
    s3_statements = [
        s for s in statements
        if any(a.startswith("s3:") for a in (
            s["Action"] if isinstance(s["Action"], list) else [s["Action"]]))
    ]

    get_object = [s for s in s3_statements if s["Action"] == "s3:GetObject"]
    assert len(get_object) == 1
    # The bucket ARN is a token, so assert on the suffix joined onto it.
    assert get_object[0]["Resource"]["Fn::Join"][1][-1] == "/documents/*"

    list_bucket = [s for s in s3_statements if s["Action"] == "s3:ListBucket"]
    assert len(list_bucket) == 1
    assert list_bucket[0]["Condition"] == \
        {"StringLike": {"s3:prefix": ["documents/*"]}}
