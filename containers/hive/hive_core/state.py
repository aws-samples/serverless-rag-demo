import json
import logging
import boto3
from botocore.exceptions import ClientError
from hive_core.guardrails import DEFAULT_GUARDRAILS

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "agents": [],
    "channels": [],
}


class StateManager:
    """Manages per-user durable state in S3."""

    def __init__(self, bucket: str, user_id: str, kms_key_id: str):
        self.bucket = bucket
        self.user_id = user_id
        self.kms_key_id = kms_key_id
        self.prefix = f"users/{user_id}"
        self.s3 = boto3.client("s3")

    def _get_json(self, key: str, default=None):
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            return json.loads(resp["Body"].read())
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return default if default is not None else {}
            raise

    def _put_json(self, key: str, data: dict, encrypt: bool = False):
        kwargs = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": json.dumps(data),
            "ContentType": "application/json",
        }
        if encrypt:
            kwargs["ServerSideEncryption"] = "aws:kms"
            kwargs["SSEKMSKeyId"] = self.kms_key_id
        self.s3.put_object(**kwargs)

    def load_config(self) -> dict:
        return self._get_json(f"{self.prefix}/config.json", DEFAULT_CONFIG.copy())

    def save_config(self, config: dict):
        self._put_json(f"{self.prefix}/config.json", config)

    def load_secrets(self) -> dict:
        return self._get_json(f"{self.prefix}/secrets.enc", {})

    def save_secrets(self, secrets: dict):
        self._put_json(f"{self.prefix}/secrets.enc", secrets, encrypt=True)

    def save_script(self, name: str, content: str):
        self.s3.put_object(
            Bucket=self.bucket,
            Key=f"{self.prefix}/scripts/{name}",
            Body=content,
        )

    def load_script(self, name: str) -> str:
        resp = self.s3.get_object(
            Bucket=self.bucket, Key=f"{self.prefix}/scripts/{name}"
        )
        return resp["Body"].read().decode()

    def save_cron_jobs(self, jobs: list[dict]):
        self._put_json(f"{self.prefix}/cron/jobs.json", {"jobs": jobs})

    def load_cron_jobs(self) -> list[dict]:
        data = self._get_json(f"{self.prefix}/cron/jobs.json", {"jobs": []})
        return data.get("jobs", [])

    def load_persona(self) -> dict:
        return self._get_json(f"{self.prefix}/persona.json", {
            "persona": "",
            "channel_overrides": {},
            "contact_overrides": {},
        })

    def save_persona(self, persona: dict):
        self._put_json(f"{self.prefix}/persona.json", persona)

    def load_guardrails(self) -> dict:
        data = self._get_json(f"{self.prefix}/guardrails.json", DEFAULT_GUARDRAILS.copy())
        # Normalize "stranger" → "unknown" (UI may use either name)
        policies = data.get("policies", {})
        if "stranger" in policies and "unknown" not in policies:
            policies["unknown"] = policies.pop("stranger")
        return data

    def save_guardrails(self, guardrails: dict):
        self._put_json(f"{self.prefix}/guardrails.json", guardrails)

    def wipe(self):
        """Delete all state for this user."""
        resp = self.s3.list_objects_v2(
            Bucket=self.bucket, Prefix=f"{self.prefix}/"
        )
        if "Contents" not in resp:
            return
        objects = [{"Key": obj["Key"]} for obj in resp["Contents"]]
        self.s3.delete_objects(
            Bucket=self.bucket, Delete={"Objects": objects}
        )
        logger.info(f"Wiped state for user {self.user_id}: {len(objects)} objects deleted")
