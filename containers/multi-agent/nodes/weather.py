from strands import Agent
from strands.models import BedrockModel
from strands_tools import http_request
import os

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")
REGION = os.getenv("REGION", "us-east-1")

WEATHER_PROMPT = """You are a weather assistant. Use the http_request tool to find current weather information.
Report temperature, conditions, and forecast concisely."""


def get_weather(query: str) -> str:
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    agent = Agent(system_prompt=WEATHER_PROMPT, model=model, tools=[http_request])
    return str(agent(query))
