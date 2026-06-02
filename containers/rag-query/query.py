import boto3
import os
import logging

logger = logging.getLogger(__name__)

REGION = os.getenv("REGION", "us-east-1")
KB_ID = os.getenv("KNOWLEDGE_BASE_ID", "")
MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6")

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)


async def rag_query_stream(query: str, model_id: str = None, user_email: str = None, search_scope: str = "all", search_type: str = "HYBRID", chat_history: list = None):
    """Stream RAG query response with native citations via retrieve_and_generate_stream."""
    model_id = model_id or MODEL_ID

    # Build retrieval filter for per-user search
    filter_config = None
    if search_scope == "my_docs" and user_email:
        filter_config = {
            "equals": {"key": "user_email", "value": user_email}
        }

    retrieval_config = {
        "knowledgeBaseConfiguration": {
            "knowledgeBaseId": KB_ID,
            "modelArn": f"arn:aws:bedrock:{REGION}::foundation-model/{model_id}" if not model_id.startswith("arn:") else model_id,
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {
                    "numberOfResults": 5,
                    "overrideSearchType": search_type,
                }
            },
            "generationConfiguration": {
                "inferenceConfig": {
                    "textInferenceConfig": {
                        "maxTokens": 4096,
                    }
                },
            },
        }
    }

    if filter_config:
        retrieval_config["knowledgeBaseConfiguration"]["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"] = filter_config

    # Add chat history as session context
    session_config = {}
    if chat_history and len(chat_history) > 0:
        # Format recent history for context
        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history[-5:]])
        query = f"Context from recent conversation:\n{history_text}\n\nCurrent question: {query}"

    # Use model ARN for retrieve_and_generate_stream
    model_arn = model_id
    if not model_arn.startswith("arn:"):
        # For global inference profiles
        if model_arn.startswith("global."):
            model_arn = f"arn:aws:bedrock::{REGION}:inference-profile/{model_arn}"
        else:
            model_arn = f"arn:aws:bedrock:{REGION}::foundation-model/{model_arn}"

    kwargs = {
        "input": {"text": query},
        "retrieveAndGenerateConfiguration": {
            "type": "KNOWLEDGE_BASE",
            **retrieval_config,
        },
    }

    try:
        response = bedrock_agent_runtime.retrieve_and_generate_stream(**kwargs)
    except Exception as e:
        logger.error(f"retrieve_and_generate_stream failed: {e}")
        # Fallback to separate retrieve + converse if streaming RAG not available
        async for chunk in _fallback_rag_stream(query, model_id, user_email, search_scope, search_type, chat_history):
            yield chunk
        return

    # Process the stream
    citations_sent = False
    for event in response.get("stream", []):
        if "output" in event:
            text = event["output"].get("text", "")
            if text:
                yield {"type": "token", "text": text}

        if "citation" in event and not citations_sent:
            citation = event["citation"]
            references = citation.get("retrievedReferences", [])
            if references:
                sources = []
                for i, ref in enumerate(references, 1):
                    uri = ref.get("location", {}).get("s3Location", {}).get("uri", "")
                    content_text = ref.get("content", {}).get("text", "")[:200]
                    # Skip empty/placeholder sources
                    if not uri or not content_text.strip():
                        continue
                    sources.append({
                        "index": i,
                        "uri": uri,
                        "excerpt": content_text,
                    })
                if sources:
                    yield {"type": "sources", "sources": sources}
                    citations_sent = True


async def _fallback_rag_stream(query: str, model_id: str = None, user_email: str = None, search_scope: str = "all", search_type: str = "HYBRID", chat_history: list = None):
    """Fallback: separate Retrieve + ConverseStream if retrieve_and_generate_stream unavailable."""
    model_id = model_id or MODEL_ID
    bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)

    retrieval_config = {
        "vectorSearchConfiguration": {
            "numberOfResults": 5,
            "overrideSearchType": search_type,
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
    context_parts = []

    for i, result in enumerate(results, 1):
        text = result.get("content", {}).get("text", "")
        score = result.get("score", 0)
        uri = result.get("location", {}).get("s3Location", {}).get("uri", "")
        # Skip results with no content, no URI, or very low relevance
        if not text.strip() or not uri or score < 0.1:
            continue
        context_parts.append(f"[Source {i} | score: {score:.2f} | {uri}]\n{text}")
        sources.append({"index": i, "uri": uri, "score": score})

    if sources:
        yield {"type": "sources", "sources": sources}

    context = "\n\n".join(context_parts) if context_parts else "No relevant documents found."

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

    response = bedrock_runtime.converse_stream(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": query}]}],
        system=[{"text": system_prompt}],
        inferenceConfig={"maxTokens": 4096},
    )

    for event in response["stream"]:
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                yield {"type": "token", "text": delta["text"]}
