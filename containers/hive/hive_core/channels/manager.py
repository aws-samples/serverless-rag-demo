import logging
from typing import Any, Optional
from hive_core.bus import MessageBus
from hive_core.config import ChannelConfig
from hive_core.channels.mcp_pool import MCPPool
from hive_core.channels.slack import SlackChannel
from hive_core.channels.whatsapp import WhatsAppChannel

logger = logging.getLogger(__name__)


class ChannelManager:
    """Orchestrates all communication and data channels."""

    def __init__(self, bus: MessageBus, bucket: str = "", user_id: str = ""):
        self.bus = bus
        self.bucket = bucket
        self.user_id = user_id
        self.mcp_pool = MCPPool()
        self.communication_channels: dict[str, Any] = {}
        self._channel_configs: list[ChannelConfig] = []

    async def register_channel(self, config: ChannelConfig) -> dict:
        """Register a channel. Returns init result (e.g., QR code for WhatsApp)."""
        self._channel_configs.append(config)
        result = {"status": "registered"}

        if config.type == "data" and config.provider == "mcp":
            await self.mcp_pool.connect(config)
        elif config.type == "communication":
            if config.provider == "slack":
                self.communication_channels[config.id] = SlackChannel(config)
            elif config.provider == "whatsapp-baileys":
                channel = WhatsAppChannel(config, bucket=self.bucket, user_id=self.user_id)
                self.communication_channels[config.id] = channel
                result = await channel.initialize()

        logger.info(f"Channel registered: {config.id} ({config.provider})")
        return result

    async def unregister_channel(self, channel_id: str):
        if channel_id in self.communication_channels:
            channel = self.communication_channels[channel_id]
            if isinstance(channel, WhatsAppChannel):
                await channel.shutdown(clear_auth=True)
            del self.communication_channels[channel_id]
        elif channel_id in self.mcp_pool.connections:
            self.mcp_pool.disconnect(channel_id)
        self._channel_configs = [c for c in self._channel_configs if c.id != channel_id]

    async def send(self, channel_id: str, to: str, text: str, **kwargs):
        channel = self.communication_channels.get(channel_id)
        if channel:
            await channel.send(to, text, **kwargs)

    def get_whatsapp_channel(self, channel_id: str) -> Optional[WhatsAppChannel]:
        ch = self.communication_channels.get(channel_id)
        return ch if isinstance(ch, WhatsAppChannel) else None

    def list_channels(self) -> list[dict]:
        return [{"id": c.id, "type": c.type, "provider": c.provider, "agents": c.agents} for c in self._channel_configs]

    def get_mcp_tools_for_agent(self, agent_id: str) -> list[dict]:
        return self.mcp_pool.get_tools_for_agent(agent_id)

    async def shutdown(self):
        for ch_id, ch in list(self.communication_channels.items()):
            if isinstance(ch, WhatsAppChannel):
                await ch.shutdown()
        self.mcp_pool.disconnect_all()
        self.communication_channels.clear()
