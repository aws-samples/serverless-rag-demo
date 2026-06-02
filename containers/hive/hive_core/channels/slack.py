import logging
from typing import Optional
from hive_core.config import ChannelConfig

logger = logging.getLogger(__name__)


class SlackChannel:
    """Slack communication channel using webhooks."""

    def __init__(self, config: ChannelConfig):
        self.channel_id = config.id
        self.webhook_url = config.config.get("webhook_url", "")
        self.default_channel = config.config.get("default_channel", "#general")
        self.agents = config.agents

    def _format_payload(self, text: str, channel: Optional[str] = None) -> dict:
        return {"text": text, "channel": channel or self.default_channel}

    async def send(self, text: str, channel: Optional[str] = None):
        import aiohttp
        payload = self._format_payload(text, channel)
        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"Slack send failed ({resp.status})")
