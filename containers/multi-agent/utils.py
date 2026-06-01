import boto3
import os
import uuid
import logging

logger = logging.getLogger(__name__)

S3_BUCKET = os.getenv("S3_BUCKET_NAME", "")
REGION = os.getenv("REGION", "us-east-1")

s3_client = boto3.client("s3", region_name=REGION)


def upload_to_s3(content: bytes, key: str, content_type: str = "text/html") -> str:
    s3_client.put_object(Bucket=S3_BUCKET, Key=key, Body=content, ContentType=content_type)
    return key


def generate_presigned_url(key: str, expiry: int = 3600) -> str:
    return s3_client.generate_presigned_url(
        "get_object", Params={"Bucket": S3_BUCKET, "Key": key}, ExpiresIn=expiry)


def upload_and_get_url(content: bytes, prefix: str, extension: str, content_type: str) -> str:
    key = f"{prefix}/{uuid.uuid4()}.{extension}"
    upload_to_s3(content, key, content_type)
    return generate_presigned_url(key)
