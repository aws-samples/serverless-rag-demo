import logging
from typing import Any
from hive_core.bus import MessageBus
from hive_core.config import ChannelConfig
from hive_core.channels.mcp_pool import MCPPool
from hive_core.channels.slack import SlackChannel
from hive_core.channels.whatsapp import WhatsAppChannel

logger = logging.getLogger(__name__)


class ChannelManager:
    """Orchestrates all communication and data channels."""

    def __init__(self, bus: MessageBus):
        self.bus = bus
        self.mcp_pool = MCPPool()
        self.communication_channels: dict[str, Any] = {}
        self._channel_configs: list[ChannelConfig] = []

    async def register_channel(self, config: ChannelConfig):
        self._channel_configs.append(config)
        if config.type == "data" and config.provider == "mcp":
            await self.mcp_pool.connect(config)
        elif config.type == "communication":
            if config.provider == "slack":
                self.communication_channels[config.id] = SlackChannel(config)
            elif config.provider == "whatsapp-baileys":
                self.communication_channels[config.id] = WhatsAppChannel(config)
        logger.info(f"Channel registered: {config.id} ({config.provider})")

    async def unregister_channel(self, channel_id: str):
        if channel_id in self.communication_channels:
            del self.communication_channels[channel_id]
        elif channel_id in self.mcp_pool.connections:
            self.mcp_pool.disconnect(channel_id)
        self._channel_configs = [c for c in self._channel_configs if c.id != channel_id]

    async def send(self, channel_id: str, text: str, **kwargs):
        channel = self.communication_channels.get(channel_id)
        if channel:
            await channel.send(text, **kwargs)

    def list_channels(self) -> list[dict]:
        return [{"id": c.id, "type": c.type, "provider": c.provider, "agents": c.agents} for c in self._channel_configs]

    def get_mcp_tools_for_agent(self, agent_id: str) -> list[dict]:
        return self.mcp_pool.get_tools_for_agent(agent_id)

    async def shutdown(self):
        self.mcp_pool.disconnect_all()
        self.communication_channels.clear()
