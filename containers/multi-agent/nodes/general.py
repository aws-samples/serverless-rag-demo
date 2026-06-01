from strands import Agent
from strands.models import BedrockModel
import os

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")
REGION = os.getenv("REGION", "us-east-1")

GENERAL_PROMPT = """You are a helpful, friendly assistant. Answer questions clearly and concisely.
If you don't know something, say so honestly."""


def chat(query: str) -> str:
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    agent = Agent(system_prompt=GENERAL_PROMPT, model=model)
    return str(agent(query))
