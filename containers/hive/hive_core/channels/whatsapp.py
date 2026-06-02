import logging
from typing import Optional
from hive_core.config import ChannelConfig

logger = logging.getLogger(__name__)
SIDECAR_URL = "http://localhost:3001"


class WhatsAppChannel:
    """WhatsApp via Baileys Node.js sidecar."""

    def __init__(self, config: ChannelConfig):
        self.channel_id = config.id
        self.phone_number = config.config.get("phone_number", "")
        self.auth_state_path = config.config.get("auth_state_path", "/tmp/wa-auth")
        self.agents = config.agents

    async def initialize(self) -> Optional[str]:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{SIDECAR_URL}/whatsapp/init", json={"authStatePath": self.auth_state_path}) as resp:
                data = await resp.json()
                return data.get("qr_code")

    async def send(self, to: str, text: str):
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{SIDECAR_URL}/whatsapp/send", json={"to": to, "message": text}) as resp:
                if resp.status != 200:
                    logger.error(f"WhatsApp send failed: {await resp.text()}")

    async def get_status(self) -> dict:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{SIDECAR_URL}/whatsapp/status") as resp:
                return await resp.json()
