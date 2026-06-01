import logging
from nodes.classifier import classify_intent
from nodes.retriever import retrieve
from nodes.web_search import search_web
from nodes.code_gen import generate_code
from nodes.ppt_gen import generate_ppt
from nodes.weather import get_weather
from nodes.general import chat

logger = logging.getLogger(__name__)


def _handle_retrieval(query: str, context: dict) -> str:
    from strands import Agent
    from strands.models import BedrockModel
    import os

    user_email = context.get("user_email")
    search_scope = context.get("search_scope", "all")
    kb_context = retrieve(query, user_email=user_email, search_scope=search_scope)

    if kb_context == "No relevant documents found.":
        return kb_context

    model = BedrockModel(
        model_id=os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0"),
        region_name=os.getenv("REGION", "us-east-1"),
    )
    agent = Agent(
        system_prompt=f"""Answer the user's question using ONLY the following context.
If the context doesn't contain the answer, say so.
Cite sources by number.

Context:
{kb_context}""",
        model=model,
    )
    return str(agent(query))


ROUTE_MAP = {
    "RETRIEVAL": lambda q, ctx: _handle_retrieval(q, ctx),
    "WEB_SEARCH": lambda q, ctx: search_web(q),
    "CODE_GEN": lambda q, ctx: generate_code(q),
    "PPT_GEN": lambda q, ctx: generate_ppt(q),
    "WEATHER": lambda q, ctx: get_weather(q),
    "GENERAL": lambda q, ctx: chat(q),
}


def run_graph(query: str, context: dict) -> str:
    intent = classify_intent(query)
    logger.info(f"Classified intent: {intent}")
    handler = ROUTE_MAP.get(intent, ROUTE_MAP["GENERAL"])
    return handler(query, context)
