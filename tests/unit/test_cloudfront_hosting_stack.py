import pytest

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
        cognito_identity_pool_id="us-east-1:00000000-0000-0000-0000-000000000000")
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
        cognito_identity_pool_id="us-east-1:00000000-0000-0000-0000-000000000000")
    template = Template.from_stack(nested)
    template.resource_count_is("AWS::CloudFront::Distribution", 1)


# Hashing the chat-ui asset directory is slow, so the hardening assertions share
# one synthesised template rather than building a stack each.
@pytest.fixture(scope="module")
def hardened():
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
    app = cdk.App(context={
        "environment_name": "test",
        "aws:cdk:bundling-stacks": [],
    })
    parent = cdk.Stack(app, "TestStack",
        env=cdk.Environment(account="123456789012", region="us-east-1"))
    template = Template.from_stack(CloudFrontHostingStack(parent, "TestCFHeaders",
        cognito_user_pool_id="pool-123",
        cognito_client_id="client-456",
        cognito_identity_pool_id="us-east-1:00000000-0000-0000-0000-000000000000"))
    policies = [
        r["Properties"]["ResponseHeadersPolicyConfig"]
        for r in template.to_json()["Resources"].values()
        if r["Type"] == "AWS::CloudFront::ResponseHeadersPolicy"
    ]
    assert len(policies) == 1
    return template, policies[0]["SecurityHeadersConfig"]


def test_every_response_carries_a_restrictive_csp(hardened):
    """The app holds Cognito tokens in the page, so the CSP is the XSS backstop.

    'self' for scripts means an injected inline script does not run even if one
    gets rendered, and frame-ancestors 'none' keeps the page out of someone
    else's frame.
    """
    _, headers = hardened
    csp = headers["ContentSecurityPolicy"]["ContentSecurityPolicy"]
    directives = dict(
        d.strip().split(" ", 1) for d in csp.split("; ") if " " in d.strip())
    assert directives["script-src"] == "'self'"
    assert directives["default-src"] == "'self'"
    assert directives["object-src"] == "'none'"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["base-uri"] == "'self'"
    assert headers["ContentSecurityPolicy"]["Override"] is True


def test_the_usual_hardening_headers_are_set(hardened):
    _, headers = hardened
    assert headers["ContentTypeOptions"]["Override"] is True
    assert headers["FrameOptions"]["FrameOption"] == "DENY"
    assert headers["ReferrerPolicy"]["ReferrerPolicy"] == \
        "strict-origin-when-cross-origin"
    assert headers["StrictTransportSecurity"]["AccessControlMaxAgeSec"] == 31536000
    assert headers["StrictTransportSecurity"]["IncludeSubdomains"] is True


def test_the_policy_is_actually_attached_to_the_distribution(hardened):
    """A policy nobody references would pass every assertion above and do nothing."""
    template, _ = hardened
    resources = template.to_json()["Resources"]
    policy_ids = [
        logical_id for logical_id, r in resources.items()
        if r["Type"] == "AWS::CloudFront::ResponseHeadersPolicy"
    ]
    distribution = next(
        r["Properties"]["DistributionConfig"] for r in resources.values()
        if r["Type"] == "AWS::CloudFront::Distribution"
    )
    assert distribution["DefaultCacheBehavior"]["ResponseHeadersPolicyId"] == \
        {"Ref": policy_ids[0]}
