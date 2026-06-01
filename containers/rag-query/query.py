import boto3
import os
import logging

logger = logging.getLogger(__name__)

REGION = os.getenv("REGION", "us-east-1")
KB_ID = os.getenv("KNOWLEDGE_BASE_ID", "")
MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)
bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)


def _retrieve_context(query: str, user_email: str = None, search_scope: str = "all") -> tuple[str, list]:
    """Retrieve relevant documents from Knowledge Base."""
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
    sources = []

    if not results:
        return "No relevant documents found in the knowledge base.", sources

    context_parts = []
    for i, result in enumerate(results, 1):
        text = result.get("content", {}).get("text", "")
        score = result.get("score", 0)
        uri = result.get("location", {}).get("s3Location", {}).get("uri", "unknown")
        context_parts.append(f"[Source {i} | score: {score:.2f} | {uri}]\n{text}")
        sources.append({"index": i, "uri": uri, "score": score})

    return "\n\n".join(context_parts), sources


async def rag_query_stream(query: str, user_email: str = None, search_scope: str = "all", chat_history: list = None):
    """Stream RAG query response token by token."""
    context, sources = _retrieve_context(query, user_email, search_scope)

    # Send sources metadata
    yield {"type": "sources", "sources": sources}

    history_text = ""
    if chat_history:
        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history[-5:]])
        history_text = f"\nRecent conversation:\n{history_text}\n"

    system_prompt = f"""You are a helpful document assistant. Answer questions using the retrieved context below.
If the context doesn't contain enough information, say so clearly.
Cite sources by their number when referencing specific information.
{history_text}
Retrieved Context:
{context}"""

    # Stream response from Bedrock
    response = bedrock_runtime.converse_stream(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": query}]}],
        system=[{"text": system_prompt}],
        inferenceConfig={"maxTokens": 4096},
    )

    for event in response["stream"]:
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                yield {"type": "token", "text": delta["text"]}
        elif "metadata" in event:
            usage = event["metadata"].get("usage", {})
            yield {"type": "metadata", "usage": usage}
