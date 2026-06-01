import logging
import os
import boto3
from nodes.classifier import classify_intent
from nodes.retriever import retrieve
from nodes.web_search import search_web
from nodes.code_gen import generate_code
from nodes.ppt_gen import generate_ppt
from nodes.weather import get_weather
from nodes.general import chat

logger = logging.getLogger(__name__)

REGION = os.getenv("REGION", "us-east-1")
MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")

bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)


async def run_graph_stream(query: str, context: dict):
    """Run multi-agent graph and stream results."""
    # Step 1: Classify intent
    intent = classify_intent(query)
    logger.info(f"Classified intent: {intent}")
    yield {"type": "intent", "intent": intent}

    # Step 2: Execute the appropriate handler
    if intent == "RETRIEVAL":
        async for chunk in _stream_retrieval(query, context):
            yield chunk
    elif intent == "CODE_GEN":
        result = generate_code(query)
        yield {"type": "result", "content": result}
    elif intent == "PPT_GEN":
        result = generate_ppt(query)
        yield {"type": "result", "content": result}
    elif intent == "WEATHER":
        result = get_weather(query)
        yield {"type": "result", "content": result}
    elif intent == "WEB_SEARCH":
        result = search_web(query)
        yield {"type": "result", "content": result}
    else:
        # GENERAL — stream from Bedrock
        async for chunk in _stream_general(query):
            yield chunk


async def _stream_retrieval(query: str, context: dict):
    """Stream retrieval-augmented response."""
    user_email = context.get("user_email")
    search_scope = context.get("search_scope", "all")
    kb_context = retrieve(query, user_email=user_email, search_scope=search_scope)

    if kb_context == "No relevant documents found.":
        yield {"type": "token", "text": kb_context}
        return

    system_prompt = f"""Answer the user's question using ONLY the following context.
If the context doesn't contain the answer, say so.
Cite sources by number.

Context:
{kb_context}"""

    async for chunk in _stream_converse(query, system_prompt):
        yield chunk


async def _stream_general(query: str):
    """Stream general conversation response."""
    system_prompt = "You are a helpful assistant. Be concise and informative."
    async for chunk in _stream_converse(query, system_prompt):
        yield chunk


async def _stream_converse(query: str, system_prompt: str):
    """Stream response from Bedrock Converse API."""
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
