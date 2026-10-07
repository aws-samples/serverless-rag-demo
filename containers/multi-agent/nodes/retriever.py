import boto3
import os
import logging

logger = logging.getLogger(__name__)

REGION = os.getenv("REGION", "us-east-1")
KB_ID = os.getenv("KNOWLEDGE_BASE_ID", "")

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)

# Only this exact value opts into searching every user's documents.
SHARED_CORPUS_SCOPE = "all"


def retrieve(
    query: str,
    user_email: str = None,
    search_scope: str = "my_docs",
    may_read_shared_corpus: bool = False,
) -> str:
    """Retrieve context for one caller, failing closed.

    Anything other than an explicit "all" scopes retrieval to the caller's own
    documents, so an unrecognised scope narrows rather than widens. "all" is
    additionally gated on the caller's Cognito group: asking for the shared
    corpus is not the same as being allowed it.
    """
    retrieval_config = {
        "vectorSearchConfiguration": {
            "numberOfResults": 5,
            "overrideSearchType": "HYBRID",
        }
    }

    if search_scope == SHARED_CORPUS_SCOPE:
        if not may_read_shared_corpus:
            raise PermissionError(
                "You are not a member of the group that may search shared documents"
            )
    else:
        if not user_email:
            raise PermissionError("Cannot scope retrieval without a caller identity")
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
