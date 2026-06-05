"""Hive self-awareness and self-management tools.

These tools let agents introspect the hive (list agents, channels) and
perform privileged operations (add channels, run code, spawn dynamic agents).
Privileged tools are gated by guardrails — only the owner tier can use them.
"""

import asyncio
import logging
import os
import subprocess
import tempfile
from strands import tool
from hive_core.guardrails import check_guardrails
from hive_core.config import DEFAULT_MODEL

logger = logging.getLogger(__name__)

# Global references set by app.py
_registry = None
_channel_manager = None
_config = None
_state = None
_event_loop = None


def set_hive_ops_refs(registry, channel_manager, config, state):
    """Wire up references from the session."""
    global _registry, _channel_manager, _config, _state, _event_loop
    _registry = registry
    _channel_manager = channel_manager
    _config = config
    _state = state
    try:
        _event_loop = asyncio.get_running_loop()
    except RuntimeError:
        _event_loop = None


def _run_async(coro):
    """Run async coroutine from sync Strands tool context."""
    global _event_loop
    if _event_loop and _event_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, _event_loop)
        return future.result(timeout=15)
    else:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Introspection tools (safe for all tiers)
# ---------------------------------------------------------------------------


@tool
def list_hive_agents() -> dict:
    """List all agents currently registered in the hive.

    Returns:
        dict with agents list, each having: id, name, status, model, message_count
    """
    if not _registry:
        return {"success": False, "error": "Registry not available"}

    agents = []
    for agent_id, agent in _registry.agents.items():
        agents.append({
            "id": agent.agent_id,
            "name": agent.name,
            "status": agent.status,
            "model": agent.model_id,
            "message_count": agent.message_count,
            "tools_count": len(agent.tools),
        })
    return {"success": True, "agents": agents}


@tool
def list_hive_channels() -> dict:
    """List all channels configured in the hive (WhatsApp, Slack, MCP, etc).

    Returns:
        dict with channels list, each having: id, provider, type, status
    """
    if not _channel_manager:
        return {"success": True, "channels": [], "note": "No channels configured yet. Use the Channels tab in the UI or ask me to add one."}

    channels = []
    for ch_id, ch in _channel_manager.communication_channels.items():
        channels.append({
            "id": ch_id,
            "provider": getattr(ch, "provider", "unknown"),
            "type": "communication",
            "connected": getattr(ch, "connected", False),
        })
    for ch_id, ch in _channel_manager.data_channels.items():
        channels.append({
            "id": ch_id,
            "provider": getattr(ch, "provider", "unknown"),
            "type": "data",
            "connected": getattr(ch, "connected", False),
        })
    return {"success": True, "channels": channels}


@tool
def get_hive_status() -> dict:
    """Get overall hive status — agents, channels, config summary.

    Returns:
        dict with agent_count, channel_count, model, and system info
    """
    agent_count = len(_registry.agents) if _registry else 0
    channel_count = 0
    if _channel_manager:
        channel_count = len(_channel_manager.communication_channels) + len(_channel_manager.data_channels)

    return {
        "success": True,
        "agent_count": agent_count,
        "channel_count": channel_count,
        "default_model": DEFAULT_MODEL,
        "region": os.getenv("REGION", "us-east-1"),
    }


# ---------------------------------------------------------------------------
# Management tools (owner-only, guardrailed)
# ---------------------------------------------------------------------------


@tool
def add_mcp_channel(channel_id: str, server_url: str, description: str = "") -> dict:
    """Add an MCP server as a data channel to the hive. OWNER ONLY.

    Args:
        channel_id: Unique ID for this channel (e.g. "my-mcp-server")
        server_url: The MCP server URL (e.g. "wss://example.com/mcp" or "stdio://command")
        description: Optional human-readable description

    Returns:
        dict with success status
    """
    blocked = check_guardrails("add_mcp_channel", channel_id=channel_id)
    if blocked:
        return {"success": False, "error": blocked}

    if not _channel_manager or not _config:
        return {"success": False, "error": "Session not fully initialized"}

    from hive_core.config import ChannelConfig
    channel_cfg = ChannelConfig(
        id=channel_id,
        provider="mcp",
        type="data",
        config={"url": server_url, "description": description},
        permissions=[],
        agents=["pa-agent"],
    )

    try:
        result = _run_async(_channel_manager.register_channel(channel_cfg))
        _config.channels.append(channel_cfg)
        _state.save_config(_config.to_dict())
        return {"success": True, "channel_id": channel_id, "message": f"MCP channel '{channel_id}' added and connected."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def remove_channel(channel_id: str) -> dict:
    """Remove a channel from the hive. OWNER ONLY.

    Args:
        channel_id: The channel ID to remove

    Returns:
        dict with success status
    """
    blocked = check_guardrails("remove_channel", channel_id=channel_id)
    if blocked:
        return {"success": False, "error": blocked}

    if not _channel_manager or not _config:
        return {"success": False, "error": "Session not fully initialized"}

    try:
        _run_async(_channel_manager.unregister_channel(channel_id))
        _config.channels = [c for c in _config.channels if c.id != channel_id]
        _state.save_config(_config.to_dict())
        return {"success": True, "message": f"Channel '{channel_id}' removed."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def run_code(code: str, language: str = "python") -> dict:
    """Execute a code snippet in a sandboxed subprocess. OWNER ONLY.

    Use this for quick computations, data transformations, API calls,
    or any task that benefits from code execution. The code runs in an
    isolated subprocess with a 30-second timeout.

    Args:
        code: The code to execute
        language: Programming language (currently only "python" supported)

    Returns:
        dict with stdout, stderr, return_code, and success status
    """
    blocked = check_guardrails("run_code")
    if blocked:
        return {"success": False, "error": blocked}

    if language != "python":
        return {"success": False, "error": f"Language '{language}' not supported. Use 'python'."}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        script_path = f.name

    try:
        result = subprocess.run(
            ["python3", script_path],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:2000],
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Code execution timed out (30s limit)"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        os.unlink(script_path)


@tool
def spawn_dynamic_agent(task: str, context: str = "") -> dict:
    """Spawn a temporary single-use agent to handle a specific task. OWNER ONLY.

    This creates a lightweight agent that runs a single query and returns the result.
    Useful for delegating subtasks, research, or specialized processing.

    Args:
        task: The task/prompt for the dynamic agent
        context: Optional additional context to provide

    Returns:
        dict with the agent's response
    """
    blocked = check_guardrails("spawn_dynamic_agent")
    if blocked:
        return {"success": False, "error": blocked}

    try:
        from strands import Agent as StrandsAgent
        from strands.models import BedrockModel

        region = os.getenv("REGION", "us-east-1")
        model = BedrockModel(
            model_id=DEFAULT_MODEL,
            region_name=region,
        )

        prompt = "You are a temporary task agent. Complete the given task concisely and return the result."
        if context:
            prompt += f"\n\nContext: {context}"

        agent = StrandsAgent(system_prompt=prompt, model=model, tools=[])
        result = agent(task)
        return {"success": True, "result": str(result)}
    except Exception as e:
        logger.error(f"Dynamic agent failed: {e}")
        return {"success": False, "error": str(e)}
