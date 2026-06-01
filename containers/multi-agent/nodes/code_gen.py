from strands import Agent
from strands.models import BedrockModel
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import upload_and_get_url

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")
REGION = os.getenv("REGION", "us-east-1")

CODE_GEN_PROMPT = """You are a code generator. Generate clean, working code based on user requests.
When generating HTML, include inline CSS and make it visually appealing.
Return ONLY the code, no explanations."""


def generate_code(query: str) -> str:
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    agent = Agent(system_prompt=CODE_GEN_PROMPT, model=model)
    code = str(agent(query))
    url = upload_and_get_url(code.encode("utf-8"), "generated-code", "html", "text/html")
    return f"Code generated and uploaded. <location>{url}</location>"
