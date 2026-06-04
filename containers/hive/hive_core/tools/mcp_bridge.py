"""Bridge MCP tools into Strands-compatible callable tools."""
import asyncio
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_mcp_pool = None
_event_loop = None
_ws_notify_fn = None


def set_mcp_pool(pool):
    global _mcp_pool, _event_loop
    _mcp_pool = pool
    try:
        _event_loop = asyncio.get_running_loop()
    except RuntimeError:
        _event_loop = None


def set_mcp_ws_notify(fn):
    """Set the WebSocket notify function for pushing MCP events to UI."""
    global _ws_notify_fn
    _ws_notify_fn = fn


def _run_async(coro):
    """Run async coroutine from sync Strands tool context."""
    global _event_loop
    if _event_loop and _event_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, _event_loop)
        return future.result(timeout=30)
    else:
        return asyncio.run(coro)


def _notify_channel_event(event_type: str, channel_id: str, tool_name: str, message: str, metadata: dict = None):
    """Push a channel event to the UI WebSocket."""
    global _ws_notify_fn, _event_loop
    if not _ws_notify_fn or not _event_loop:
        return
    try:
        asyncio.run_coroutine_threadsafe(
            _ws_notify_fn({
                "type": event_type,
                "channel_id": channel_id,
                "provider": "mcp",
                "contact": tool_name,
                "contact_name": tool_name,
                "message": message,
                "timestamp": int(time.time()),
                "metadata": metadata or {},
            }),
            _event_loop,
        )
    except Exception:
        pass


def create_mcp_tool(tool_name: str, tool_description: str, channel_id: str):
    """Create a Strands-compatible function that calls an MCP tool.

    Returns a function with proper docstring for Strands tool registration.
    """

    def mcp_tool_fn(**kwargs) -> dict:
        """Dynamically generated MCP tool wrapper."""
        global _mcp_pool
        if not _mcp_pool:
            return {"success": False, "error": "MCP pool not initialized"}

        # Emit outgoing event (request to MCP)
        request_summary = json.dumps(kwargs, default=str)[:200] if kwargs else "(no args)"
        _notify_channel_event(
            "channel_outgoing", channel_id, tool_name,
            request_summary, {"tool": tool_name, "args": kwargs},
        )

        try:
            result = _run_async(_mcp_pool.call_tool(channel_id, tool_name, kwargs))
            # MCP returns CallToolResult with content list
            if hasattr(result, "content"):
                texts = []
                for block in result.content:
                    if hasattr(block, "text"):
                        texts.append(block.text)
                    elif hasattr(block, "data"):
                        texts.append(str(block.data))
                result_text = "\n".join(texts)
            else:
                result_text = str(result)

            # Emit incoming event (response from MCP)
            _notify_channel_event(
                "channel_incoming", channel_id, tool_name,
                result_text[:300], {"tool": tool_name, "success": True},
            )

            return {"success": True, "result": result_text}
        except Exception as e:
            logger.error(f"MCP tool {tool_name} call failed: {e}")
            _notify_channel_event(
                "channel_incoming", channel_id, tool_name,
                f"ERROR: {e}", {"tool": tool_name, "success": False},
            )
            return {"success": False, "error": str(e)}

    # Set function metadata for Strands introspection
    mcp_tool_fn.__name__ = tool_name
    mcp_tool_fn.__qualname__ = tool_name
    mcp_tool_fn.__doc__ = f"{tool_description}\n\nArgs:\n    **kwargs: Tool-specific arguments passed to MCP server."

    return mcp_tool_fn


def create_mcp_tools_for_agent(agent_id: str) -> list:
    """Create Strands tool functions for all MCP tools mapped to an agent."""
    global _mcp_pool
    if not _mcp_pool:
        return []

    tools = []
    channel_ids = _mcp_pool._agent_mapping.get(agent_id, [])
    for cid in channel_ids:
        conn = _mcp_pool.connections.get(cid)
        if not conn:
            continue
        for tool_meta in conn.tools:
            fn = create_mcp_tool(tool_meta["name"], tool_meta.get("description", ""), cid)
            tools.append(fn)

    return tools
