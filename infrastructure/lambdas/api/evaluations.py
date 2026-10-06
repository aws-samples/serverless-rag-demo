"""RAG evaluation jobs, scoped to the calling user.

bedrock:CreateEvaluationJob and bedrock:ListEvaluationJobs have no resource-level
support in IAM — they can only be granted on "*". That is survivable on this
Lambda role, which no user controls, but it is not something to hand to a browser:
with it, any signed-in user could read every evaluation job in the account and
start unbounded paid jobs. So the grant lives here, and this module decides what
each caller may see:

  * job names are server-generated and carry an opaque per-user tag, so listing
    filters to the caller and a fetch by ARN is refused unless the tag matches
  * dataset and output locations are derived from the verified email, so a caller
    cannot read from or write to another user's prefix
"""

import json
import os
import re
import uuid

import boto3

from common import (
    BadRequest,
    DATA_BUCKET,
    Forbidden,
    REGION,
    body,
    logger,
    response,
    s3,
    user_tag,
)

KB_ID = os.environ["KNOWLEDGE_BASE_ID"]
EVAL_ROLE_ARN = os.environ["EVAL_ROLE_ARN"]
EVALUATOR_MODEL_ARN = os.environ["EVALUATOR_MODEL_ARN"]
GENERATOR_MODEL_ARN = os.environ["GENERATOR_MODEL_ARN"]

EVALUATION_PREFIX = "evaluations/"
MAX_QUESTIONS = 100
MAX_RESULT_OBJECTS = 20
MAX_RESULT_BYTES = 5 * 1024 * 1024

# Mirrors ALL_METRICS in the UI. An allowlist rather than passthrough so a caller
# cannot probe the Bedrock API with arbitrary metric names.
ALLOWED_METRICS = frozenset([
    "Builtin.Correctness",
    "Builtin.Completeness",
    "Builtin.Helpfulness",
    "Builtin.LogicalCoherence",
    "Builtin.Faithfulness",
    "Builtin.ContextRelevance",
    "Builtin.ContextCoverage",
])

JOB_TOKEN = re.compile(r"^[a-f0-9]{16}$")
JOB_ARN = re.compile(
    r"^arn:aws(-[^:]+)?:bedrock:[a-z0-9-]{1,20}:[0-9]{12}:evaluation-job/[a-z0-9]{12}$"
)

bedrock = boto3.client("bedrock", region_name=REGION)


def _job_name_prefix(email: str) -> str:
    return f"srd-{user_tag(email)}-"


def _job_prefix(email: str, token: str) -> str:
    return f"{EVALUATION_PREFIX}{user_tag(email)}/{token}/"


def _own_token(token) -> str:
    """Validate a caller-supplied job token before it reaches an S3 key."""
    if not token or not isinstance(token, str) or not JOB_TOKEN.match(token):
        raise BadRequest("jobId must be 16 hexadecimal characters")
    return token


def _questions(data: dict) -> list:
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise BadRequest("questions must be a non-empty list")
    if len(questions) > MAX_QUESTIONS:
        raise BadRequest(f"questions must contain at most {MAX_QUESTIONS} entries")

    cleaned = []
    for entry in questions:
        if not isinstance(entry, dict):
            raise BadRequest("each question must be an object")
        question = entry.get("question")
        if not isinstance(question, str) or not question.strip():
            raise BadRequest("each question must have non-empty text")
        if len(question) > 2000:
            raise BadRequest("a question must be at most 2000 characters")
        expected = entry.get("expected_answer")
        if expected is not None:
            if not isinstance(expected, str):
                raise BadRequest("expected_answer must be a string")
            if len(expected) > 4000:
                raise BadRequest("expected_answer must be at most 4000 characters")
        cleaned.append((question, expected or None))
    return cleaned


def _metrics(data: dict) -> list:
    metrics = data.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise BadRequest("metrics must be a non-empty list")
    unknown = [m for m in metrics if m not in ALLOWED_METRICS]
    if unknown:
        raise BadRequest(f"Unsupported metrics: {', '.join(map(str, unknown))}")
    return list(dict.fromkeys(metrics))


def create_evaluation(event: dict, email: str) -> dict:
    data = body(event)
    questions = _questions(data)
    metrics = _metrics(data)

    token = uuid.uuid4().hex[:16]
    prefix = _job_prefix(email, token)
    dataset_key = f"{prefix}input.jsonl"
    job_name = f"{_job_name_prefix(email)}{token}"

    lines = []
    for question, expected in questions:
        turn = {"prompt": {"content": [{"text": question}]}}
        if expected:
            turn["referenceResponses"] = [{"content": [{"text": expected}]}]
        lines.append(json.dumps({"conversationTurns": [turn]}))

    s3.put_object(
        Bucket=DATA_BUCKET,
        Key=dataset_key,
        Body="\n".join(lines),
        ContentType="application/jsonl",
    )

    job = bedrock.create_evaluation_job(
        jobName=job_name,
        roleArn=EVAL_ROLE_ARN,
        applicationType="RagEvaluation",
        evaluationConfig={
            "automated": {
                "datasetMetricConfigs": [
                    {
                        # Not "General" — EvaluationTaskType only accepts
                        # Summarization, Classification, QuestionAndAnswer,
                        # Generation or Custom, so the old value was rejected
                        # before the job could start.
                        "taskType": "QuestionAndAnswer",
                        "dataset": {
                            "name": job_name,
                            "datasetLocation": {
                                "s3Uri": f"s3://{DATA_BUCKET}/{dataset_key}"
                            },
                        },
                        "metricNames": metrics,
                    },
                ],
                "evaluatorModelConfig": {
                    "bedrockEvaluatorModels": [
                        {"modelIdentifier": EVALUATOR_MODEL_ARN},
                    ],
                },
            },
        },
        inferenceConfig={
            "ragConfigs": [
                {
                    "knowledgeBaseConfig": {
                        "retrieveAndGenerateConfig": {
                            "type": "KNOWLEDGE_BASE",
                            "knowledgeBaseConfiguration": {
                                "knowledgeBaseId": KB_ID,
                                "modelArn": GENERATOR_MODEL_ARN,
                            },
                        },
                    },
                },
            ],
        },
        outputDataConfig={"s3Uri": f"s3://{DATA_BUCKET}/{prefix}output/"},
    )

    return response(202, {
        "jobId": token,
        "jobArn": job["jobArn"],
        "jobName": job_name,
    })


def list_evaluations(_event: dict, email: str) -> dict:
    prefix = _job_name_prefix(email)
    jobs = bedrock.list_evaluation_jobs(
        nameContains=prefix,
        maxResults=20,
        sortBy="CreationTime",
        sortOrder="Descending",
    )

    summaries = []
    for job in jobs.get("jobSummaries", []):
        name = job.get("jobName", "")
        # nameContains is a substring match, so re-check it is really a prefix.
        if not name.startswith(prefix):
            continue
        summaries.append({
            "jobId": name[len(prefix):],
            "jobArn": job.get("jobArn", ""),
            "jobName": name,
            "status": job.get("status", "Unknown"),
            "createdAt": job.get("creationTime"),
        })

    return response(200, {"jobs": summaries})


def evaluation_status(event: dict, email: str) -> dict:
    params = event.get("queryStringParameters") or {}
    job_arn = params.get("jobArn")
    if not job_arn or not JOB_ARN.match(job_arn):
        raise BadRequest("jobArn must be a Bedrock evaluation job ARN")

    job = bedrock.get_evaluation_job(jobIdentifier=job_arn)
    name = job.get("jobName", "")
    if not name.startswith(_job_name_prefix(email)):
        raise Forbidden("You can only view your own evaluation jobs")

    return response(200, {
        "jobId": name[len(_job_name_prefix(email)):],
        "jobArn": job_arn,
        "jobName": name,
        "status": job.get("status", "Unknown"),
        "createdAt": job.get("creationTime"),
    })


def evaluation_results(event: dict, email: str) -> dict:
    """Read and aggregate a finished job's output from the caller's own prefix.

    Bedrock nests its output under the prefix it was given rather than writing a
    fixed file name, so find the JSONL rather than guessing at a path.
    """
    params = event.get("queryStringParameters") or {}
    token = _own_token(params.get("jobId"))
    prefix = f"{_job_prefix(email, token)}output/"

    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=DATA_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".jsonl") and obj.get("Size", 0) <= MAX_RESULT_BYTES:
                keys.append(obj["Key"])
        if len(keys) >= MAX_RESULT_OBJECTS:
            break

    if not keys:
        return response(200, {"results": None})

    aggregate: dict = {}
    per_question = []
    for key in keys[:MAX_RESULT_OBJECTS]:
        payload = s3.get_object(Bucket=DATA_BUCKET, Key=key)["Body"].read()
        for line in payload.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed result line in %s", key)
                continue

            question = (
                record.get("conversationTurnContent", {})
                .get("prompt", {})
                .get("content", [{}])[0]
                .get("text", "")
            )
            answer = record.get("output", {}).get("text", "")

            metrics = []
            for name, value in (record.get("scores") or {}).items():
                try:
                    score = float(value)
                except (TypeError, ValueError):
                    continue
                metrics.append({"metricName": name, "score": score})
                aggregate.setdefault(name, []).append(score)

            per_question.append({
                "question": question,
                "generatedAnswer": answer,
                "metrics": metrics,
            })

    return response(200, {"results": {
        "aggregateScores": [
            {"metricName": name, "score": sum(scores) / len(scores)}
            for name, scores in aggregate.items()
        ],
        "perQuestion": per_question,
    }})
