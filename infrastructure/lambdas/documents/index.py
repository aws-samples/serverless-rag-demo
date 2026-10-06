"""Document management API handler.

All S3 and Knowledge Base access for user documents happens here rather than in
the browser. The caller's identity comes from the Cognito JWT claim that API
Gateway has already verified, never from the request body, so a caller cannot
act on another user's documents by naming them.

Key convention: documents/{userEmail}/{fileName}
"""

import json
import logging
import os
import posixpath
import re

import boto3
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ["REGION"]
DATA_BUCKET = os.environ["DATA_BUCKET_NAME"]
KB_ID = os.environ["KNOWLEDGE_BASE_ID"]
DATA_SOURCE_ID = os.environ["DATA_SOURCE_ID"]

PRESIGN_EXPIRY_SECONDS = 300
DOCUMENT_PREFIX = "documents/"
METADATA_SUFFIX = ".metadata.json"

# SigV4 is required for presigned URLs that the browser PUTs to directly.
s3 = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))
bedrock_agent = boto3.client("bedrock-agent", region_name=REGION)

# Conservative allowlist: anything outside this is rejected rather than rewritten,
# so a caller never gets a silently different key than the one they asked for.
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ ()-]{0,254}$")


class BadRequest(Exception):
    """Caller error -> 400."""


class Forbidden(Exception):
    """Caller is authenticated but not entitled to this object -> 403."""


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _caller_email(event: dict) -> str:
    """Return the email from the JWT claims API Gateway already verified.

    The authorizer rejects unsigned, expired and wrong-audience tokens before we
    are invoked, so a claim present here is trustworthy. Absence means the route
    was misconfigured without an authorizer.
    """
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    email = claims.get("email")
    if not email:
        raise Forbidden("No verified email claim on the request")
    if not claims.get("email_verified") in (True, "true", "True"):
        raise Forbidden("Email claim is not verified")
    return email


def _user_prefix(email: str) -> str:
    return f"{DOCUMENT_PREFIX}{email}/"


def _own_key(email: str, file_name: str) -> str:
    """Build the caller's own key for file_name, rejecting traversal attempts.

    The Lambda role can reach all of documents/*, so this check is what keeps a
    crafted fileName such as "../victim@example.com/secret.txt" from escaping
    the caller's own prefix.
    """
    if not file_name or not SAFE_FILENAME.match(file_name):
        raise BadRequest(
            "fileName must be 1-255 characters of letters, digits, spaces, "
            "dot, underscore, hyphen or parentheses"
        )
    if file_name.endswith(METADATA_SUFFIX):
        raise BadRequest("fileName may not end with " + METADATA_SUFFIX)

    key = _user_prefix(email) + file_name
    # Belt and braces: normalising must not move the key out of the prefix.
    if posixpath.normpath(key) != key or not key.startswith(_user_prefix(email)):
        raise BadRequest("Invalid fileName")
    return key


def _assert_owned(email: str, key: str) -> str:
    """Authorise an operation on an existing key the caller supplied."""
    if not key:
        raise BadRequest("key is required")
    if posixpath.normpath(key) != key:
        raise BadRequest("Invalid key")
    if not key.startswith(_user_prefix(email)):
        raise Forbidden("You can only access your own documents")
    return key


def _body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise BadRequest("Body must be valid JSON")
    if not isinstance(parsed, dict):
        raise BadRequest("Body must be a JSON object")
    return parsed


def list_documents(event: dict, email: str) -> dict:
    """List documents. Defaults to the caller's own; `scope=all` lists every owner.

    `scope=all` is retained because the UI offers a shared-corpus view, but it
    only ever exposes file names and owners, never content: fetching a document
    still requires ownership.
    """
    params = event.get("queryStringParameters") or {}
    scope = params.get("scope", "mine")
    if scope not in ("mine", "all"):
        raise BadRequest("scope must be 'mine' or 'all'")

    prefix = DOCUMENT_PREFIX if scope == "all" else _user_prefix(email)

    documents = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=DATA_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(METADATA_SUFFIX) or key.endswith("/"):
                continue

            relative = key[len(DOCUMENT_PREFIX):]
            owner, _, file_name = relative.partition("/")
            if not file_name:
                continue

            documents.append({
                "key": key,
                "fileName": file_name,
                "userEmail": owner,
                "size": obj.get("Size", 0),
                "lastModified": obj.get("LastModified"),
                "isOwner": owner == email,
            })

    return _response(200, {"documents": documents})


def create_upload_url(event: dict, email: str) -> dict:
    """Presign a PUT for the caller's own prefix and write the KB metadata sidecar.

    The sidecar carries the user_email the Knowledge Base filters on. Writing it
    here from the verified claim is what stops a caller from tagging an upload
    with somebody else's identity.
    """
    body = _body(event)
    file_name = body.get("fileName")
    content_type = body.get("contentType") or "application/octet-stream"
    if not isinstance(content_type, str) or len(content_type) > 255:
        raise BadRequest("contentType must be a string of at most 255 characters")

    key = _own_key(email, file_name)

    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": DATA_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=PRESIGN_EXPIRY_SECONDS,
    )

    s3.put_object(
        Bucket=DATA_BUCKET,
        Key=key + METADATA_SUFFIX,
        Body=json.dumps({"metadataAttributes": {"user_email": email}}),
        ContentType="application/json",
    )

    return _response(200, {"url": url, "key": key})


def create_download_url(event: dict, email: str) -> dict:
    key = _assert_owned(email, _body(event).get("key"))
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": DATA_BUCKET, "Key": key},
        ExpiresIn=PRESIGN_EXPIRY_SECONDS,
    )
    return _response(200, {"url": url})


def delete_document(event: dict, email: str) -> dict:
    key = _assert_owned(email, _body(event).get("key"))
    s3.delete_objects(
        Bucket=DATA_BUCKET,
        Delete={
            "Objects": [{"Key": key}, {"Key": key + METADATA_SUFFIX}],
            "Quiet": True,
        },
    )
    return _response(200, {"deleted": key})


def sync_knowledge_base(_event: dict, _email: str) -> dict:
    job = bedrock_agent.start_ingestion_job(
        knowledgeBaseId=KB_ID, dataSourceId=DATA_SOURCE_ID
    )
    return _response(202, {"ingestionJobId": job["ingestionJob"]["ingestionJobId"]})


def ingestion_status(_event: dict, _email: str) -> dict:
    jobs = bedrock_agent.list_ingestion_jobs(
        knowledgeBaseId=KB_ID,
        dataSourceId=DATA_SOURCE_ID,
        maxResults=1,
        sortBy=[{"attribute": "STARTED_AT", "order": "DESCENDING"}],
    )
    summaries = jobs.get("ingestionJobSummaries", [])
    if not summaries:
        return _response(200, {"status": None})

    job = summaries[0]
    stats = job.get("statistics", {})
    return _response(200, {
        "status": job.get("status", "Unknown"),
        "startedAt": job.get("startedAt"),
        "updatedAt": job.get("updatedAt"),
        "documentsScanned": stats.get("numberOfDocumentsScanned"),
        "documentsIndexed": stats.get("numberOfNewDocumentsIndexed"),
        "documentsFailed": stats.get("numberOfDocumentsFailed"),
    })


ROUTES = {
    "GET /documents": list_documents,
    "POST /documents/upload-url": create_upload_url,
    "POST /documents/download-url": create_download_url,
    "DELETE /documents": delete_document,
    "POST /documents/sync": sync_knowledge_base,
    "GET /documents/ingestion-status": ingestion_status,
}


def handler(event, _context):
    route = event.get("routeKey")
    try:
        email = _caller_email(event)
        handle = ROUTES.get(route)
        if handle is None:
            return _response(404, {"message": "Not found"})
        return handle(event, email)
    except BadRequest as exc:
        return _response(400, {"message": str(exc)})
    except Forbidden as exc:
        logger.warning("Denied %s: %s", route, exc)
        return _response(403, {"message": str(exc)})
    except Exception:
        # Detail stays in CloudWatch; the caller gets nothing it could probe with.
        logger.exception("Unhandled error on %s", route)
        return _response(500, {"message": "Internal server error"})
