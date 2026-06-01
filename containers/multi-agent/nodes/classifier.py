from strands import Agent
from strands.models import BedrockModel
import os
import logging

logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")
REGION = os.getenv("REGION", "us-east-1")

CLASSIFIER_PROMPT = """You are an intent classifier. Given a user query, classify it into exactly ONE category:
- RETRIEVAL: Questions answerable from uploaded documents/knowledge base
- WEB_SEARCH: Questions requiring current web information
- CODE_GEN: Requests to generate code (HTML, Python, etc.)
- PPT_GEN: Requests to create presentations/slides
- WEATHER: Questions about weather
- GENERAL: Casual conversation, greetings, or topics not matching above

Respond with ONLY the category name, nothing else."""


def classify_intent(query: str) -> str:
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    agent = Agent(system_prompt=CLASSIFIER_PROMPT, model=model)
    response = agent(query)
    intent = str(response).strip().upper()
    valid_intents = {"RETRIEVAL", "WEB_SEARCH", "CODE_GEN", "PPT_GEN", "WEATHER", "GENERAL"}
    if intent not in valid_intents:
        logger.warning(f"Unknown intent '{intent}', defaulting to GENERAL")
        return "GENERAL"
    return intent
