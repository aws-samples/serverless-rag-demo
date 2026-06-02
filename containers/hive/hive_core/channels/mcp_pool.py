import logging
from dataclasses import dataclass
from typing import Any
from hive_core.config import ChannelConfig

logger = logging.getLogger(__name__)


@dataclass
class MCPConnection:
    channel_id: str
    tools: list[dict]
    client: Any


class MCPPool:
    """Manages MCP client connections for data channels."""

    def __init__(self):
        self.connections: dict[str, MCPConnection] = {}
        self._agent_mapping: dict[str, list[str]] = {}

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
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            url = config.config["url"]
            headers = {}
            if "api_key" in config.config:
                headers["Authorization"] = f"Bearer {config.config['api_key']}"

            async with sse_client(url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    tools = [{"name": t.name, "description": t.description} for t in tools_result.tools]
                    return MCPConnection(channel_id=config.id, tools=tools, client=session)
        except Exception as e:
            logger.error(f"MCP SSE connect failed {config.id}: {e}")
            raise

    async def _connect_stdio(self, config: ChannelConfig) -> MCPConnection:
        try:
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client, StdioServerParameters

            params = StdioServerParameters(
                command=config.config["command"],
                args=config.config.get("args", []),
                env=config.config.get("env", {}),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    tools = [{"name": t.name, "description": t.description} for t in tools_result.tools]
                    return MCPConnection(channel_id=config.id, tools=tools, client=session)
        except Exception as e:
            logger.error(f"MCP stdio connect failed {config.id}: {e}")
            raise

    def disconnect(self, channel_id: str):
        if channel_id in self.connections:
            del self.connections[channel_id]
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

    def disconnect_all(self):
        for cid in list(self.connections.keys()):
            self.disconnect(cid)
