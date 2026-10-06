import json
import logging
import os
from bedrock_agentcore import BedrockAgentCoreApp
from auth import AuthError, verified_email
from query import rag_query_stream

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()


@app.websocket
async def websocket_handler(websocket, context):
    """RAG Query WebSocket handler with streaming responses."""
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()
            query = data.get("query", "")
            model_id = data.get("model_id")
            search_scope = data.get("search_scope", "my_docs")
            search_type = data.get("search_type", "HYBRID")
            chat_history = data.get("chat_history", [])

            if not query:
                await websocket.send_json({"type": "error", "message": "No query provided"})
                continue

            # The caller's identity comes from a verified ID token, never from a
            # user_email field in the message: the WebSocket is signed with the
            # shared authenticated role, so the transport cannot tell us who this
            # is. Any user_email in `data` is ignored.
            try:
                user_email = verified_email(data.get("id_token", ""))
            except AuthError as e:
                logger.warning(f"Rejected query: {e}")
                await websocket.send_json({"type": "error", "message": "Authentication required"})
                continue

            # Stream response tokens back
            await websocket.send_json({"type": "start", "query": query})

            try:
                async for chunk in rag_query_stream(
                    query=query,
                    model_id=model_id,
                    user_email=user_email,
                    search_scope=search_scope,
                    search_type=search_type,
                    chat_history=chat_history,
                ):
                    await websocket.send_json(chunk)

                await websocket.send_json({"type": "end"})
            except Exception as e:
                logger.error(f"RAG query error: {e}")
                await websocket.send_json({"type": "error", "message": str(e)})

    except Exception as e:
        if "disconnect" not in str(e).lower():
            logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()


if __name__ == "__main__":
    app.run(log_level="info")
