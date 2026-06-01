import json
import logging
import os
from bedrock_agentcore import BedrockAgentCoreApp
from graph import run_graph_stream

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()


@app.websocket
async def websocket_handler(websocket, context):
    """Multi-Agent WebSocket handler with streaming responses."""
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()
            query = data.get("query", "")
            user_context = {
                "user_email": data.get("user_email"),
                "search_scope": data.get("search_scope", "all"),
            }

            if not query:
                await websocket.send_json({"type": "error", "message": "No query provided"})
                continue

            await websocket.send_json({"type": "start", "query": query})

            try:
                async for chunk in run_graph_stream(query, user_context):
                    await websocket.send_json(chunk)

                await websocket.send_json({"type": "end"})
            except Exception as e:
                logger.error(f"Multi-agent error: {e}")
                await websocket.send_json({"type": "error", "message": str(e)})

    except Exception as e:
        if "disconnect" not in str(e).lower():
            logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()


if __name__ == "__main__":
    app.run(log_level="info")
