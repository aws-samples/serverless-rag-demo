"""Shared request plumbing for the app API.

The caller's identity always comes from the Cognito JWT claim that API Gateway
verified before this function was invoked — never from the request body or query
string. Everything a caller may touch is derived from that claim, so naming
somebody else's resource is not a thing the API can be asked to do.
"""

import hashlib
import json
import logging
import os

import boto3
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ["REGION"]
DATA_BUCKET = os.environ["DATA_BUCKET_NAME"]

# Membership of this Cognito group is what grants the shared-corpus view.
# Without it a caller only ever sees their own documents.
SHARED_CORPUS_GROUP = os.environ.get("SHARED_CORPUS_GROUP", "corpus-readers")

# SigV4 is required for presigned URLs the browser uses directly.
s3 = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))


class BadRequest(Exception):
    """Caller error -> 400."""


class Forbidden(Exception):
    """Caller is authenticated but not entitled to this resource -> 403."""


def response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _claims(event: dict) -> dict:
    return (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )


def caller_email(event: dict) -> str:
    """Return the email from the JWT claims API Gateway already verified.

    The authorizer rejects unsigned, expired and wrong-audience tokens before we
    are invoked, so a claim present here is trustworthy. Absence means the route
    was misconfigured without an authorizer.
    """
    claims = _claims(event)
    email = claims.get("email")
    if not email:
        raise Forbidden("No verified email claim on the request")
    if claims.get("email_verified") not in (True, "true", "True"):
        raise Forbidden("Email claim is not verified")
    return email


def caller_groups(event: dict) -> list:
    """Return the caller's Cognito groups from the verified claims.

    API Gateway flattens the claim, so `cognito:groups` arrives as a JSON array
    or as a bracketed, space-separated string depending on the payload version.
    Handle both rather than silently treating a string as a list of characters.
    """
    groups = _claims(event).get("cognito:groups") or []
    if isinstance(groups, str):
        groups = groups.strip().strip("[]").replace(",", " ").split()
    return [g for g in groups if isinstance(g, str) and g]


def may_read_shared_corpus(event: dict) -> bool:
    return SHARED_CORPUS_GROUP in caller_groups(event)


def user_tag(email: str) -> str:
    """A stable, opaque per-user token safe to use inside resource names.

    Bedrock job names and S3 URIs for evaluation jobs allow a narrower character
    set than an email address does, and sanitising an email into that set is not
    injective — two different users could collapse onto the same string and end
    up sharing a prefix. Hashing avoids that, and keeps addresses out of
    resource names that show up in logs and the console.
    """
    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:12]


def body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise BadRequest("Body must be valid JSON")
    if not isinstance(parsed, dict):
        raise BadRequest("Body must be a JSON object")
    return parsed


def text_field(data: dict, name: str, *, max_length: int, required: bool = True) -> str:
    value = data.get(name)
    if value is None or value == "":
        if required:
            raise BadRequest(f"{name} is required")
        return ""
    if not isinstance(value, str):
        raise BadRequest(f"{name} must be a string")
    if len(value) > max_length:
        raise BadRequest(f"{name} must be at most {max_length} characters")
    return value
