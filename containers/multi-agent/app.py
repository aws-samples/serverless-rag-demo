import logging
import os
from bedrock_agentcore import BedrockAgentCoreApp
from auth import AuthError, verified_caller
from graph import run_graph_stream

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

MAX_QUERY_CHARS = 4000


@app.websocket
async def websocket_handler(websocket, context):
    """Multi-Agent WebSocket handler with streaming responses."""
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()
            query = data.get("query", "")

            if not query or not isinstance(query, str):
                await websocket.send_json({"type": "error", "message": "No query provided"})
                continue
            if len(query) > MAX_QUERY_CHARS:
                await websocket.send_json(
                    {"type": "error", "message": f"Query must be {MAX_QUERY_CHARS} characters or fewer"})
                continue

            # The caller's identity comes from a verified ID token, never from a
            # user_email field in the message: the WebSocket is signed with the
            # shared authenticated role, so the transport cannot tell us who this
            # is. Any user_email in `data` is ignored.
            try:
                caller = verified_caller(data.get("id_token", ""))
            except AuthError as e:
                logger.warning(f"Rejected query: {e}")
                await websocket.send_json({"type": "error", "message": "Authentication required"})
                continue

            user_context = {
                "user_email": caller.email,
                # Retrieval narrows to the caller unless they ask for the shared
                # corpus *and* their token says they may read it.
                "search_scope": data.get("search_scope", "my_docs"),
                "may_read_shared_corpus": caller.may_read_shared_corpus,
            }

            await websocket.send_json({"type": "start", "query": query})

            try:
                async for chunk in run_graph_stream(query, user_context):
                    await websocket.send_json(chunk)

                await websocket.send_json({"type": "end"})
            except PermissionError as e:
                logger.warning(f"Refused query from {caller.email}: {e}")
                await websocket.send_json({"type": "error", "message": str(e)})
            except Exception as e:
                # The detail goes to CloudWatch; the caller gets nothing that
                # describes our internals.
                logger.exception("Multi-agent error")
                await websocket.send_json(
                    {"type": "error", "message": "The agent could not complete this request"})

    except Exception as e:
        if "disconnect" not in str(e).lower():
            logger.error(f"WebSocket error: {e}")
    finally:
        await websocket.close()


if __name__ == "__main__":
    app.run(log_level="info")
