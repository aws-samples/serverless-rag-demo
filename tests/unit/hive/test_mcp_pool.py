import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from hive_core.channels.mcp_pool import MCPPool, MCPConnection
from hive_core.config import ChannelConfig


@pytest.fixture
def pool():
    return MCPPool()


def test_pool_starts_empty(pool):
    assert len(pool.connections) == 0


@pytest.mark.asyncio
async def test_connect_sse_channel(pool):
    config = ChannelConfig(
        id="test-mcp", type="data", provider="mcp",
        config={"transport": "sse", "url": "http://localhost:8080/mcp"},
        permissions=["read"], agents=["pa-agent"]
    )
    with patch.object(pool, "_connect_sse", new_callable=AsyncMock) as mock:
        mock.return_value = MCPConnection(channel_id="test-mcp", tools=[{"name": "get_data"}], client=MagicMock())
        conn = await pool.connect(config)
        assert conn.channel_id == "test-mcp"
        assert len(conn.tools) == 1


def test_disconnect(pool):
    pool.connections["test-mcp"] = MCPConnection(channel_id="test-mcp", tools=[], client=MagicMock())
    pool.disconnect("test-mcp")
    assert "test-mcp" not in pool.connections


def test_get_tools_for_agent(pool):
    pool.connections["mcp-1"] = MCPConnection(channel_id="mcp-1", tools=[{"name": "a"}, {"name": "b"}], client=MagicMock())
    pool._agent_mapping = {"pa-agent": ["mcp-1"]}
    tools = pool.get_tools_for_agent("pa-agent")
    assert len(tools) == 2


def test_get_tools_for_unregistered_agent(pool):
    assert pool.get_tools_for_agent("unknown") == []
