import boto3
import os
import logging
import re

logger = logging.getLogger(__name__)

REGION = os.getenv("REGION", "us-east-1")
KB_ID = os.getenv("KNOWLEDGE_BASE_ID", "")
MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6")

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)

# Only this exact value opts into searching every user's documents.
SHARED_CORPUS_SCOPE = "all"

# The model id arrives from the browser and ends up inside an ARN we hand to
# Bedrock, so it is matched against a shape rather than trusted: a bare
# "provider.model" or an inference profile prefixed with a routing region. An
# id the caller has crafted to look like an ARN is rejected outright, which
# stops it naming a resource in someone else's account.
MODEL_ID_PATTERN = re.compile(
    r"^(?:global|us|eu|apac)?\.?"
    r"(?:anthropic|amazon|meta|mistral|cohere|ai21|deepseek|openai|qwen|writer|twelvelabs|stability)"
    r"\.[a-z0-9][a-z0-9.\-]{0,95}(?::[0-9]+)?$"
)

# Chat history is replayed into the prompt, so it is capped in both directions:
# how many turns we keep and how much of each turn.
MAX_HISTORY_TURNS = 5
MAX_HISTORY_CHARS = 2000
HISTORY_ROLES = ("user", "assistant")


def _model_id(model_id: str | None) -> str:
    """Return a model id safe to interpolate into a Bedrock ARN."""
    candidate = (model_id or MODEL_ID).strip()
    if not MODEL_ID_PATTERN.match(candidate):
        raise ValueError("Unsupported model")
    return candidate


def _model_arn(model_id: str) -> str:
    """Return the ARN for a validated model id.

    Bedrock resolves cross-region inference profiles given in this form, so the
    shape is the same for both; what changed is that a caller can no longer
    supply a whole ARN of their own.
    """
    return f"arn:aws:bedrock:{REGION}::foundation-model/{model_id}"


def _history_text(chat_history: list | None) -> str:
    """Render recent turns, dropping anything that is not a well-formed turn.

    The history comes from the browser, so a missing key must not raise and an
    unbounded transcript must not become an unbounded prompt.
    """
    if not isinstance(chat_history, list):
        return ""

    lines = []
    for msg in chat_history[-MAX_HISTORY_TURNS:]:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role not in HISTORY_ROLES or not isinstance(content, str):
            continue
        lines.append(f"{role}: {content[:MAX_HISTORY_CHARS]}")

    return "\n".join(lines)


def _retrieval_filter(
    user_email: str,
    search_scope: str,
    may_read_shared_corpus: bool = False,
) -> dict | None:
    """Return the Knowledge Base filter for this caller, failing closed.

    Anything other than an explicit "all" scopes retrieval to the caller's own
    documents. That matters because the UI has sent "user" where this module
    previously expected "my_docs", which silently disabled the filter and
    searched the whole corpus; an unrecognised scope must narrow, not widen.

    The shared corpus is additionally gated on the caller's Cognito group, so
    asking for it is not the same as being allowed it.
    """
    if search_scope == SHARED_CORPUS_SCOPE:
        if not may_read_shared_corpus:
            raise PermissionError(
                "You are not a member of the group that may search shared documents"
            )
        return None

    if not user_email:
        raise ValueError(
            f"user_email is required unless search_scope is '{SHARED_CORPUS_SCOPE}'"
        )

    return {"equals": {"key": "user_email", "value": user_email}}


async def rag_query_stream(query: str, model_id: str = None, user_email: str = None, search_scope: str = "my_docs", search_type: str = "HYBRID", chat_history: list = None, may_read_shared_corpus: bool = False):
    """Stream RAG query response with native citations via retrieve_and_generate_stream."""
    model_id = _model_id(model_id)

    filter_config = _retrieval_filter(user_email, search_scope, may_read_shared_corpus)

    retrieval_config = {
        "knowledgeBaseConfiguration": {
            "knowledgeBaseId": KB_ID,
            "modelArn": _model_arn(model_id),
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
    history_text = _history_text(chat_history)
    if history_text:
        query = f"Context from recent conversation:\n{history_text}\n\nCurrent question: {query}"

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
        async for chunk in _fallback_rag_stream(
            query, model_id, user_email, search_scope, search_type, chat_history,
            may_read_shared_corpus,
        ):
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


async def _fallback_rag_stream(query: str, model_id: str = None, user_email: str = None, search_scope: str = "my_docs", search_type: str = "HYBRID", chat_history: list = None, may_read_shared_corpus: bool = False):
    """Fallback: separate Retrieve + ConverseStream if retrieve_and_generate_stream unavailable."""
    model_id = _model_id(model_id)
    bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)

    retrieval_config = {
        "vectorSearchConfiguration": {
            "numberOfResults": 5,
            "overrideSearchType": search_type,
        }
    }

    filter_config = _retrieval_filter(user_email, search_scope, may_read_shared_corpus)
    if filter_config:
        retrieval_config["vectorSearchConfiguration"]["filter"] = filter_config

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

    history_text = _history_text(chat_history)
    if history_text:
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
