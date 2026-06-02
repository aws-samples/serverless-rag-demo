"""Bridge MCP tools into Strands-compatible callable tools."""
import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_mcp_pool = None
_event_loop = None


def set_mcp_pool(pool):
    global _mcp_pool, _event_loop
    _mcp_pool = pool
    try:
        _event_loop = asyncio.get_running_loop()
    except RuntimeError:
        _event_loop = None


def _run_async(coro):
    """Run async coroutine from sync Strands tool context."""
    global _event_loop
    if _event_loop and _event_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, _event_loop)
        return future.result(timeout=30)
    else:
        return asyncio.run(coro)


def create_mcp_tool(tool_name: str, tool_description: str, channel_id: str):
    """Create a Strands-compatible function that calls an MCP tool.

    Returns a function with proper docstring for Strands tool registration.
    """

    def mcp_tool_fn(**kwargs) -> dict:
        """Dynamically generated MCP tool wrapper."""
        global _mcp_pool
        if not _mcp_pool:
            return {"success": False, "error": "MCP pool not initialized"}

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
                return {"success": True, "result": "\n".join(texts)}
            return {"success": True, "result": str(result)}
        except Exception as e:
            logger.error(f"MCP tool {tool_name} call failed: {e}")
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
