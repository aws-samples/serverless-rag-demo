import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from hive_core.config import ChannelConfig

logger = logging.getLogger(__name__)


@dataclass
class MCPConnection:
    channel_id: str
    tools: list[dict]
    client: Any  # Active ClientSession
    _cleanup: Any = None  # Callable to shut down the connection


class MCPPool:
    """Manages MCP client connections for data channels.

    Keeps connections alive so tools remain callable after connect().
    """

    def __init__(self):
        self.connections: dict[str, MCPConnection] = {}
        self._agent_mapping: dict[str, list[str]] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def connect(self, config: ChannelConfig) -> MCPConnection:
        transport = config.config.get("transport", "sse")
        if transport == "sse":
            conn = await self._connect_sse(config)
        elif transport == "stdio":
            conn = await self._connect_stdio(config)
        else:
            raise ValueError(f"Unknown MCP transport: {transport}")

        self.connections[config.id] = conn
        for agent_id in config.agents:
            if agent_id not in self._agent_mapping:
                self._agent_mapping[agent_id] = []
            self._agent_mapping[agent_id].append(config.id)

        logger.info(f"MCP connected: {config.id} ({len(conn.tools)} tools)")
        return conn

    async def _connect_sse(self, config: ChannelConfig) -> MCPConnection:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        url = config.config["url"]
        headers = {}
        if "api_key" in config.config:
            headers["Authorization"] = f"Bearer {config.config['api_key']}"

        # Create an event that signals when session is ready
        ready = asyncio.Event()
        conn_holder: dict[str, Any] = {}

        async def _run():
            try:
                async with sse_client(url, headers=headers) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        conn_holder["session"] = session
                        conn_holder["tools"] = [
                            {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
                            for t in tools_result.tools
                        ]
                        ready.set()
                        # Keep alive until cancelled
                        await asyncio.Event().wait()
            except asyncio.CancelledError:
                logger.info(f"MCP SSE connection closed: {config.id}")
            except Exception as e:
                logger.error(f"MCP SSE connection error {config.id}: {e}")
                conn_holder["error"] = e
                ready.set()

        task = asyncio.create_task(_run())
        self._tasks[config.id] = task

        await asyncio.wait_for(ready.wait(), timeout=15)

        if "error" in conn_holder:
            raise conn_holder["error"]

        session = conn_holder["session"]
        tools = conn_holder["tools"]

        def cleanup():
            task.cancel()

        return MCPConnection(channel_id=config.id, tools=tools, client=session, _cleanup=cleanup)

    async def _connect_stdio(self, config: ChannelConfig) -> MCPConnection:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client, StdioServerParameters

        params = StdioServerParameters(
            command=config.config["command"],
            args=config.config.get("args", []),
            env=config.config.get("env", {}),
        )

        ready = asyncio.Event()
        conn_holder: dict[str, Any] = {}

        async def _run():
            try:
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        conn_holder["session"] = session
                        conn_holder["tools"] = [
                            {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
                            for t in tools_result.tools
                        ]
                        ready.set()
                        await asyncio.Event().wait()
            except asyncio.CancelledError:
                logger.info(f"MCP stdio connection closed: {config.id}")
            except Exception as e:
                logger.error(f"MCP stdio connection error {config.id}: {e}")
                conn_holder["error"] = e
                ready.set()

        task = asyncio.create_task(_run())
        self._tasks[config.id] = task

        await asyncio.wait_for(ready.wait(), timeout=30)

        if "error" in conn_holder:
            raise conn_holder["error"]

        session = conn_holder["session"]
        tools = conn_holder["tools"]

        def cleanup():
            task.cancel()

        return MCPConnection(channel_id=config.id, tools=tools, client=session, _cleanup=cleanup)

    async def call_tool(self, channel_id: str, tool_name: str, arguments: dict) -> Any:
        """Call a tool on a connected MCP server."""
        conn = self.connections.get(channel_id)
        if not conn:
            raise RuntimeError(f"MCP channel '{channel_id}' not connected")
        result = await conn.client.call_tool(tool_name, arguments)
        return result

    def disconnect(self, channel_id: str):
        conn = self.connections.get(channel_id)
        if conn and conn._cleanup:
            conn._cleanup()
        if channel_id in self.connections:
            del self.connections[channel_id]
        if channel_id in self._tasks:
            del self._tasks[channel_id]
        for agent_id in list(self._agent_mapping.keys()):
            self._agent_mapping[agent_id] = [
                cid for cid in self._agent_mapping[agent_id] if cid != channel_id
            ]

    def get_tools_for_agent(self, agent_id: str) -> list[dict]:
        channel_ids = self._agent_mapping.get(agent_id, [])
        tools = []
        for cid in channel_ids:
            conn = self.connections.get(cid)
            if conn:
                tools.extend(conn.tools)
        return tools

    def get_channel_for_tool(self, tool_name: str) -> str | None:
        """Find which channel owns a given tool name."""
        for cid, conn in self.connections.items():
            if any(t["name"] == tool_name for t in conn.tools):
                return cid
        return None

    def disconnect_all(self):
        for cid in list(self.connections.keys()):
            self.disconnect(cid)
