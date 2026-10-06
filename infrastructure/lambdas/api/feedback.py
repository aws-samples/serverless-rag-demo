"""Thumbs-up/down feedback on chat answers.

Previously the browser read the whole day's feedback file, appended to it and put
it back. That gave every signed-in user a read of everyone else's feedback —
emails, questions and answers — and let any one of them replace the day's file
wholesale, besides losing entries whenever two people voted at once.

Each submission is now its own object, written here with the caller's verified
email, so there is nothing shared to read or clobber.
"""

import json
import uuid
from datetime import datetime, timezone

from common import (
    BadRequest,
    DATA_BUCKET,
    body,
    response,
    s3,
    text_field,
)

FEEDBACK_PREFIX = "feedback/"
MAX_SOURCES = 50
MAX_SOURCE_LENGTH = 2048


def _sources(data: dict) -> list:
    sources = data.get("sources") or []
    if not isinstance(sources, list):
        raise BadRequest("sources must be a list")
    if len(sources) > MAX_SOURCES:
        raise BadRequest(f"sources must contain at most {MAX_SOURCES} entries")
    for source in sources:
        if not isinstance(source, str) or len(source) > MAX_SOURCE_LENGTH:
            raise BadRequest(
                f"each source must be a string of at most {MAX_SOURCE_LENGTH} characters"
            )
    return sources


def submit_feedback(event: dict, email: str) -> dict:
    data = body(event)

    rating = data.get("rating")
    if rating not in ("up", "down"):
        raise BadRequest("rating must be 'up' or 'down'")

    now = datetime.now(timezone.utc)
    entry = {
        "timestamp": now.isoformat(),
        "userEmail": email,
        "question": text_field(data, "question", max_length=8000, required=False),
        "answer": text_field(data, "answer", max_length=20000, required=False),
        "sources": _sources(data),
        "rating": rating,
    }

    key = f"{FEEDBACK_PREFIX}{now.date().isoformat()}/{uuid.uuid4().hex}.json"
    s3.put_object(
        Bucket=DATA_BUCKET,
        Key=key,
        Body=json.dumps(entry),
        ContentType="application/json",
    )

    return response(201, {"recorded": True})
