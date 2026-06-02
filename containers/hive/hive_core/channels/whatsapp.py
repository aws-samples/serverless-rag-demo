import asyncio
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
from typing import Optional

import aiohttp
import boto3
from botocore.exceptions import ClientError

from hive_core.config import ChannelConfig

logger = logging.getLogger(__name__)
SIDECAR_URL = "http://127.0.0.1:3001"
AUTH_STATE_PATH = "/tmp/wa-auth"


class WhatsAppChannel:
    """WhatsApp via Baileys Node.js sidecar with S3-persisted auth."""

    def __init__(self, config: ChannelConfig, bucket: str, user_id: str):
        self.channel_id = config.id
        self.phone_number = config.config.get("phone_number", "")
        self.incoming_mode = config.config.get("incoming_mode", "notify")
        self.reply_prefix = config.config.get("reply_prefix", "")
        self.contact_overrides = config.config.get("contact_overrides", {})
        self.agents = config.agents
        self.bucket = bucket
        self.user_id = user_id
        self._process: Optional[subprocess.Popen] = None
        self._s3 = boto3.client("s3")
        self._connected = False

    async def initialize(self) -> dict:
        """Start sidecar, restore auth, return init status (qr/connected)."""
        self._restore_auth_from_s3()
        self._start_sidecar()
        await asyncio.sleep(2)  # Let sidecar boot

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{SIDECAR_URL}/init",
                json={"authStatePath": AUTH_STATE_PATH},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if data.get("status") == "connected":
                    self._connected = True
                return data

    def _start_sidecar(self):
        """Start the Node.js sidecar process."""
        if self._process and self._process.poll() is None:
            return  # Already running
        sidecar_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "sidecar")
        sidecar_dir = os.path.abspath(sidecar_dir)
        self._process = subprocess.Popen(
            ["node", "index.js"],
            cwd=sidecar_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logger.info(f"Sidecar started (PID {self._process.pid})")

    def _restore_auth_from_s3(self):
        """Download auth state tarball from S3 and extract to /tmp/wa-auth."""
        s3_key = f"users/{self.user_id}/wa-auth/state.tar.gz"
        try:
            resp = self._s3.get_object(Bucket=self.bucket, Key=s3_key)
            os.makedirs(AUTH_STATE_PATH, exist_ok=True)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
            tmp.write(resp["Body"].read())
            tmp.close()
            with tarfile.open(tmp.name, "r:gz") as tar:
                tar.extractall(AUTH_STATE_PATH)
            os.unlink(tmp.name)
            logger.info("Restored WhatsApp auth state from S3")
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.info("No existing auth state in S3, will need QR scan")
            else:
                logger.error(f"Failed to restore auth state: {e}")

    def persist_auth_to_s3(self):
        """Upload auth state directory as tarball to S3."""
        if not os.path.isdir(AUTH_STATE_PATH):
            return
        s3_key = f"users/{self.user_id}/wa-auth/state.tar.gz"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
        with tarfile.open(tmp.name, "w:gz") as tar:
            for item in os.listdir(AUTH_STATE_PATH):
                tar.add(os.path.join(AUTH_STATE_PATH, item), arcname=item)
        tmp.close()
        self._s3.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=open(tmp.name, "rb").read(),
        )
        os.unlink(tmp.name)
        logger.info("Persisted WhatsApp auth state to S3")

    def get_mode_for_sender(self, sender_jid: str) -> str:
        """Return the mode for a given sender (contact override or channel default)."""
        override = self.contact_overrides.get(sender_jid)
        if override and isinstance(override, dict):
            return override.get("mode", self.incoming_mode)
        return self.incoming_mode

    async def send(self, to: str, text: str):
        """Send a message via WhatsApp. Raises on failure."""
        message = f"{self.reply_prefix}{text}" if self.reply_prefix else text
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{SIDECAR_URL}/send",
                json={"to": to, "message": message},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status != 200 or not data.get("success"):
                    error = data.get("error", f"HTTP {resp.status}")
                    raise RuntimeError(f"WhatsApp send failed: {error}")

    async def get_messages(self, jid: str, limit: int = 20) -> list:
        """Get recent messages for a contact from sidecar buffer."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{SIDECAR_URL}/messages",
                params={"jid": jid, "limit": str(limit)},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
                return data.get("messages", [])

    async def get_contacts(self) -> list:
        """Get list of contacts with recent message activity."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{SIDECAR_URL}/contacts",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
                return data.get("contacts", [])

    async def get_status(self) -> dict:
        """Get sidecar connection status."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{SIDECAR_URL}/status", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return await resp.json()
        except Exception:
            return {"connected": False, "phone": ""}

    async def shutdown(self):
        """Stop sidecar and persist auth state."""
        self.persist_auth_to_s3()
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._process.wait(timeout=5)
            logger.info("Sidecar stopped")
