import boto3
import os
import logging
from strands import Agent
from strands.models import BedrockModel

logger = logging.getLogger(__name__)

REGION = os.getenv("REGION", "us-east-1")
KB_ID = os.getenv("KNOWLEDGE_BASE_ID", "")
MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-6-v1:0")

bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)


def rag_query(query: str, user_email: str = None, search_scope: str = "all", chat_history: list = None) -> str:
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

    if not results:
        context = "No relevant documents found in the knowledge base."
    else:
        context_parts = []
        for i, result in enumerate(results, 1):
            text = result.get("content", {}).get("text", "")
            score = result.get("score", 0)
            source = result.get("location", {}).get("s3Location", {}).get("uri", "unknown")
            context_parts.append(f"[Source {i} | score: {score:.2f} | {source}]\n{text}")
        context = "\n\n".join(context_parts)

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

    model = BedrockModel(model_id=MODEL_ID, region_name=REGION)
    agent = Agent(system_prompt=system_prompt, model=model)
    return str(agent(query))
