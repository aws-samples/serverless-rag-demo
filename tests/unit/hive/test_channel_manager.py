import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from hive_core.channels.manager import ChannelManager
from hive_core.channels.mcp_pool import MCPConnection
from hive_core.config import ChannelConfig
from hive_core.bus import MessageBus


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def manager(bus):
    return ChannelManager(bus=bus)


def test_manager_starts_empty(manager):
    assert len(manager.communication_channels) == 0


@pytest.mark.asyncio
async def test_register_slack_channel(manager):
    config = ChannelConfig(
        id="slack-1", type="communication", provider="slack",
        config={"webhook_url": "https://hooks.slack.com/x", "default_channel": "#test"},
        permissions=["send"], agents=["pa-agent"]
    )
    await manager.register_channel(config)
    assert "slack-1" in manager.communication_channels


@pytest.mark.asyncio
async def test_register_mcp_channel(manager):
    config = ChannelConfig(
        id="mcp-1", type="data", provider="mcp",
        config={"transport": "sse", "url": "http://localhost:9090/mcp"},
        permissions=["read"], agents=["market-agent"]
    )
    with patch.object(manager.mcp_pool, "connect", new_callable=AsyncMock) as mock:
        mock.return_value = MCPConnection(channel_id="mcp-1", tools=[], client=MagicMock())
        await manager.register_channel(config)
        mock.assert_called_once()


def test_list_channels_empty(manager):
    assert manager.list_channels() == []
