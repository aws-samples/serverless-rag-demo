import boto3
import os
import logging

logger = logging.getLogger(__name__)

REGION = os.getenv("REGION", "us-east-1")
KB_ID = os.getenv("KNOWLEDGE_BASE_ID", "")

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)


def retrieve(query: str, user_email: str = None, search_scope: str = "all") -> str:
    retrieval_config = {
        "vectorSearchConfiguration": {
            "numberOfResults": 5,
            "overrideSearchType": "HYBRID",
        }
    }
    if search_scope == "my_docs" and user_email:
        retrieval_config["vectorSearchConfiguration"]["filter"] = {
            "equals": {"key": "user_email", "value": user_email}
        }

    response = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration=retrieval_config,
    )
    results = response.get("retrievalResults", [])
    if not results:
        return "No relevant documents found."

    context_parts = []
    for i, result in enumerate(results, 1):
        text = result.get("content", {}).get("text", "")
        score = result.get("score", 0)
        context_parts.append(f"[Source {i} (score: {score:.2f})]\n{text}")
    return "\n\n".join(context_parts)
