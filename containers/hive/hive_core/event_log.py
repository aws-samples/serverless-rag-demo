import json
import logging
import time
from datetime import datetime, timezone
import boto3

logger = logging.getLogger(__name__)


class EventLog:
    """Append-only event log for agent activity. Powers the UI graph."""

    def __init__(self, bucket: str, user_id: str):
        self.bucket = bucket
        self.user_id = user_id
        self.buffer: list[dict] = []
        self.s3 = boto3.client("s3")

    def append(self, agent: str, event: str, data: dict):
        entry = {
            "timestamp": time.time(),
            "agent": agent,
            "event": event,
            "data": data,
        }
        self.buffer.append(entry)

    def get_recent(self, n: int = 50) -> list[dict]:
        return self.buffer[-n:]

    def flush(self):
        """Write buffered events to S3 as JSONL."""
        if not self.buffer:
            return

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"users/{self.user_id}/event-log/{today}.jsonl"
        body = "\n".join(json.dumps(e) for e in self.buffer)

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/x-ndjson",
        )
        logger.info(f"Flushed {len(self.buffer)} events to {key}")
        self.buffer.clear()
