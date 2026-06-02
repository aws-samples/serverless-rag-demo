# WhatsApp Baileys Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up end-to-end WhatsApp messaging via Baileys sidecar inside the Hive container, with QR pairing, incoming message routing, configurable modes, and S3-persisted auth state.

**Architecture:** Node.js Express sidecar (port 3001) manages Baileys WhatsApp connection. Python app communicates with sidecar via localhost HTTP. Auth state persisted to S3 for reconnection without QR. Incoming messages routed through HiveRouter based on per-channel/per-contact mode config.

**Tech Stack:** `@whiskeysockets/baileys`, `express`, `qrcode` (Node.js sidecar); `aiohttp` (Python HTTP client); existing Hive bus/router/WebSocket infrastructure.

---

## File Structure

```
containers/hive/
  sidecar/
    package.json          # Node.js deps (baileys, express, qrcode)
    index.js              # Express server + Baileys lifecycle
  hive_core/
    channels/
      whatsapp.py         # Rewrite: process mgmt, auth persistence, incoming handling
      manager.py          # Modify: call initialize(), relay results
    wa_handler.py         # New: incoming message handler + mode logic
  app.py                  # Modify: internal route, wa_approve handler, WebSocket types
  requirements.txt        # Modify: add aiohttp
  Dockerfile              # Modify: npm install sidecar deps
artifacts/chat-ui/
  src/components/hive/
    wa-qr-modal.tsx       # New: QR code display modal
    hive-layout.tsx       # Modify: handle wa_* messages, show QR modal
    channel-config.tsx    # Modify: add incoming_mode + prefix fields
    types.ts              # Modify: new WA message types
```

---

### Task 1: Baileys Sidecar — package.json and Express Server

**Files:**
- Create: `containers/hive/sidecar/package.json`
- Create: `containers/hive/sidecar/index.js`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "hive-wa-sidecar",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "start": "node index.js"
  },
  "dependencies": {
    "@whiskeysockets/baileys": "^6.7.16",
    "express": "^4.21.0",
    "qrcode": "^1.5.4",
    "pino": "^9.6.0"
  }
}
```

- [ ] **Step 2: Create index.js with Express server and Baileys lifecycle**

```javascript
const express = require("express");
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require("@whiskeysockets/baileys");
const QRCode = require("qrcode");
const pino = require("pino");
const path = require("path");

const app = express();
app.use(express.json());

const PORT = 3001;
const PYTHON_APP_URL = "http://localhost:8080";
const logger = pino({ level: "info" });

let sock = null;
let currentQR = null;
let connected = false;
let phoneNumber = "";
let authStatePath = "/tmp/wa-auth";

async function startConnection() {
    const { state, saveCreds } = await useMultiFileAuthState(authStatePath);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
        version,
        auth: state,
        logger: pino({ level: "silent" }),
        printQRInTerminal: false,
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            currentQR = await QRCode.toDataURL(qr);
            logger.info("QR code generated");
            // Notify Python app
            fetch(`${PYTHON_APP_URL}/internal/wa-event`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ event: "qr", qr: currentQR }),
            }).catch(() => {});
        }

        if (connection === "close") {
            connected = false;
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            logger.info({ statusCode, shouldReconnect }, "Connection closed");
            if (shouldReconnect) {
                setTimeout(startConnection, 3000);
            }
            fetch(`${PYTHON_APP_URL}/internal/wa-event`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ event: "disconnected", logged_out: !shouldReconnect }),
            }).catch(() => {});
        }

        if (connection === "open") {
            connected = true;
            currentQR = null;
            phoneNumber = sock.user?.id?.split(":")[0] || "";
            logger.info({ phoneNumber }, "Connected to WhatsApp");
            fetch(`${PYTHON_APP_URL}/internal/wa-event`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ event: "connected", phone: phoneNumber }),
            }).catch(() => {});
        }
    });

    sock.ev.on("messages.upsert", async ({ messages }) => {
        for (const msg of messages) {
            if (msg.key.fromMe || !msg.message) continue;
            const text = msg.message.conversation
                || msg.message.extendedTextMessage?.text
                || "";
            if (!text) continue;

            const from = msg.key.remoteJid;
            const fromName = msg.pushName || "";
            const isGroup = from.endsWith("@g.us");

            fetch(`${PYTHON_APP_URL}/internal/wa-message`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    from,
                    from_name: fromName,
                    message: text,
                    timestamp: Math.floor(Date.now() / 1000),
                    is_group: isGroup,
                    group_id: isGroup ? from : null,
                }),
            }).catch((err) => logger.error({ err }, "Failed to forward message"));
        }
    });
}

// REST API
app.post("/init", async (req, res) => {
    if (req.body.authStatePath) {
        authStatePath = req.body.authStatePath;
    }
    try {
        await startConnection();
        // Give Baileys a moment to check if auth state works
        await new Promise((resolve) => setTimeout(resolve, 2000));
        if (connected) {
            res.json({ status: "connected", phone: phoneNumber });
        } else if (currentQR) {
            res.json({ status: "qr_needed", qr: currentQR });
        } else {
            res.json({ status: "connecting" });
        }
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.post("/send", async (req, res) => {
    const { to, message } = req.body;
    if (!sock || !connected) {
        return res.status(503).json({ success: false, error: "Not connected" });
    }
    try {
        await sock.sendMessage(to, { text: message });
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

app.get("/status", (req, res) => {
    res.json({ connected, phone: phoneNumber });
});

app.get("/qr", (req, res) => {
    res.json({ qr: currentQR });
});

app.post("/shutdown", async (req, res) => {
    if (sock) {
        sock.end();
        sock = null;
    }
    connected = false;
    res.json({ success: true });
});

app.listen(PORT, "127.0.0.1", () => {
    logger.info({ port: PORT }, "WhatsApp sidecar ready");
});
```

- [ ] **Step 3: Verify sidecar can be installed**

Run: `cd containers/hive/sidecar && npm install`
Expected: `node_modules/` created without errors.

- [ ] **Step 4: Commit**

```bash
git add containers/hive/sidecar/
git commit -m "feat(hive): add Baileys WhatsApp sidecar"
```

---

### Task 2: Update Dockerfile to Install Sidecar Dependencies

**Files:**
- Modify: `containers/hive/Dockerfile`

- [ ] **Step 1: Update Dockerfile**

Replace the current Dockerfile with:

```dockerfile
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Install Node.js for channel bridge sidecar
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install sidecar Node.js dependencies
COPY sidecar/package.json sidecar/package-lock.json* sidecar/
RUN cd sidecar && npm install --production

COPY . .

EXPOSE 8080

CMD ["python", "app.py"]
```

- [ ] **Step 2: Add aiohttp to requirements.txt**

Append to `containers/hive/requirements.txt`:
```
aiohttp>=3.11.0
```

- [ ] **Step 3: Verify Docker build succeeds**

Run: `docker build --platform linux/arm64 -t hive-dev containers/hive/`
Expected: Build completes successfully.

- [ ] **Step 4: Commit**

```bash
git add containers/hive/Dockerfile containers/hive/requirements.txt
git commit -m "feat(hive): install sidecar deps and aiohttp in container"
```

---

### Task 3: Rewrite WhatsApp Channel Class

**Files:**
- Modify: `containers/hive/hive_core/channels/whatsapp.py`

- [ ] **Step 1: Rewrite whatsapp.py with process management and auth persistence**

```python
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
        """Send a message via WhatsApp."""
        message = f"{self.reply_prefix}{text}" if self.reply_prefix else text
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{SIDECAR_URL}/send",
                json={"to": to, "message": message},
            ) as resp:
                if resp.status != 200:
                    logger.error(f"WhatsApp send failed: {await resp.text()}")

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
```

- [ ] **Step 2: Commit**

```bash
git add containers/hive/hive_core/channels/whatsapp.py
git commit -m "feat(hive): rewrite WhatsApp channel with sidecar management and S3 auth"
```

---

### Task 4: Incoming Message Handler

**Files:**
- Create: `containers/hive/hive_core/wa_handler.py`

- [ ] **Step 1: Create wa_handler.py**

```python
import asyncio
import logging
from typing import Any, Callable, Awaitable

from hive_core.channels.whatsapp import WhatsAppChannel

logger = logging.getLogger(__name__)


class WhatsAppIncomingHandler:
    """Handles incoming WhatsApp messages based on channel mode config."""

    def __init__(
        self,
        channel: WhatsAppChannel,
        route_fn: Callable[[str, str], Awaitable[str]],
        get_response_fn: Callable[[], Awaitable[dict | None]],
        ws_notify_fn: Callable[[dict], Awaitable[None]],
    ):
        self.channel = channel
        self._route = route_fn
        self._get_response = get_response_fn
        self._ws_notify = ws_notify_fn
        self._pending_approvals: dict[str, dict] = {}

    async def handle_message(self, payload: dict):
        """Process an incoming WhatsApp message based on mode."""
        sender = payload["from"]
        message = payload["message"]
        from_name = payload.get("from_name", "")
        mode = self.channel.get_mode_for_sender(sender)

        logger.info(f"WA incoming from {from_name} ({sender}), mode={mode}")

        if mode in ("redirect-to-agent", "silent", "notify"):
            # Route through Hive
            target = await self._route("wa-user", message)
            response = await self._get_response()
            result_text = ""
            if response:
                result_text = response.get("result", str(response))

            # Send reply via WhatsApp
            if result_text:
                await self.channel.send(sender, result_text)

            # Notify UI if mode requires it
            if mode == "notify":
                await self._ws_notify({
                    "type": "wa_incoming",
                    "channel_id": self.channel.channel_id,
                    "from": sender,
                    "from_name": from_name,
                    "message": message,
                    "mode": mode,
                    "response": result_text,
                })

        elif mode == "ask":
            # Route to get proposed response, but don't send yet
            target = await self._route("wa-user", message)
            response = await self._get_response()
            result_text = ""
            if response:
                result_text = response.get("result", str(response))

            # Store pending approval
            approval_id = f"{sender}:{payload.get('timestamp', '')}"
            self._pending_approvals[approval_id] = {
                "sender": sender,
                "response": result_text,
            }

            # Push to UI for approval
            await self._ws_notify({
                "type": "wa_incoming",
                "channel_id": self.channel.channel_id,
                "from": sender,
                "from_name": from_name,
                "message": message,
                "mode": "ask",
                "proposed_response": result_text,
                "approval_id": approval_id,
            })

    async def handle_approval(self, approval_id: str, action: str, edited_response: str = ""):
        """Handle user approval/rejection of a proposed response."""
        pending = self._pending_approvals.pop(approval_id, None)
        if not pending:
            logger.warning(f"No pending approval: {approval_id}")
            return

        if action == "send":
            await self.channel.send(pending["sender"], pending["response"])
        elif action == "edit":
            await self.channel.send(pending["sender"], edited_response)
        # "reject" = do nothing
```

- [ ] **Step 2: Commit**

```bash
git add containers/hive/hive_core/wa_handler.py
git commit -m "feat(hive): add WhatsApp incoming message handler with mode logic"
```

---

### Task 5: Update ChannelManager to Initialize WhatsApp

**Files:**
- Modify: `containers/hive/hive_core/channels/manager.py`

- [ ] **Step 1: Update manager.py**

Replace the entire file:

```python
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
                await channel.shutdown()
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
```

- [ ] **Step 2: Commit**

```bash
git add containers/hive/hive_core/channels/manager.py
git commit -m "feat(hive): update ChannelManager for WhatsApp initialization"
```

---

### Task 6: Update app.py — Internal Routes and WebSocket Handlers

**Files:**
- Modify: `containers/hive/app.py`

- [ ] **Step 1: Update app.py with internal WA endpoints and WA WebSocket messages**

Replace the entire `app.py`:

```python
# containers/hive/app.py
import asyncio
import json
import logging
import os
from bedrock_agentcore import BedrockAgentCoreApp
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from hive_core.state import StateManager
from hive_core.bus import MessageBus, Message
from hive_core.event_log import EventLog
from hive_core.config import HiveConfig, ChannelConfig, default_config
from hive_core.registry import AgentRegistry
from hive_core.router import HiveRouter
from hive_core.executor import CodeExecutor
from hive_core.scheduler import HiveScheduler
from hive_core.agents.pa import PersonalAssistantAgent
from hive_core.agents.reminder import ReminderAgent
from hive_core.agents.market import MarketAgent
from hive_core.channels.manager import ChannelManager
from hive_core.wa_handler import WhatsAppIncomingHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BUCKET = os.getenv("HIVE_STATE_BUCKET", "hive-state-test")
KMS_KEY_ID = os.getenv("HIVE_KMS_KEY_ID", "")
REGION = os.getenv("REGION", "us-east-1")

app = BedrockAgentCoreApp()

# Global reference to active session (single-user per container)
_active_session = None
_active_websocket = None


class HiveSession:
    """Per-user Hive session with full agent orchestration."""

    def __init__(self, user_id: str, workspace_dir: str = "/tmp/hive"):
        self.user_id = user_id
        self.state = StateManager(bucket=BUCKET, user_id=user_id, kms_key_id=KMS_KEY_ID)
        self.bus = MessageBus()
        self.event_log = EventLog(bucket=BUCKET, user_id=user_id)
        self.executor = CodeExecutor(workspace_dir=workspace_dir)
        self.scheduler = HiveScheduler(state=self.state, bus=self.bus)
        self.registry = AgentRegistry(bus=self.bus, event_log=self.event_log)
        self.router = HiveRouter(bus=self.bus, registry=self.registry, event_log=self.event_log)
        self.channel_manager = ChannelManager(bus=self.bus, bucket=BUCKET, user_id=user_id)
        self.config: HiveConfig = default_config()
        self._response_queue: asyncio.Queue = asyncio.Queue()
        self.wa_handler: WhatsAppIncomingHandler | None = None

    async def initialize(self):
        """Load state and initialize agents."""
        stored = self.state.load_config()
        if stored.get("agents"):
            self.config = HiveConfig.from_dict(stored)
        else:
            self.config = default_config()
            self.state.save_config(self.config.to_dict())

        self._register_default_agents()
        self.scheduler.load()
        self.scheduler.start()
        self.bus.subscribe("__user__", self._collect_response)
        logger.info(f"Session initialized for {self.user_id}")

    def _register_default_agents(self):
        PersonalAssistantAgent(bus=self.bus, event_log=self.event_log, executor=self.executor)
        ReminderAgent(bus=self.bus, event_log=self.event_log, scheduler=self.scheduler)
        MarketAgent(bus=self.bus, event_log=self.event_log)

    async def _collect_response(self, message: Message):
        await self._response_queue.put(message)

    async def handle_query(self, query: str):
        target = await self.router.route(self.user_id, query)
        return target

    async def get_response(self, timeout: float = 60.0) -> dict | None:
        try:
            msg = await asyncio.wait_for(self._response_queue.get(), timeout=timeout)
            return msg.payload
        except asyncio.TimeoutError:
            logger.error("Agent response timeout after 60s")
            return None

    def setup_wa_handler(self, channel):
        """Wire up WhatsApp incoming handler for a channel."""
        async def ws_notify(data):
            global _active_websocket
            if _active_websocket:
                try:
                    await _active_websocket.send_json(data)
                except Exception:
                    pass

        self.wa_handler = WhatsAppIncomingHandler(
            channel=channel,
            route_fn=self.handle_query,
            get_response_fn=self.get_response,
            ws_notify_fn=ws_notify,
        )

    def shutdown(self):
        self.scheduler.stop()
        self.event_log.flush()


@app.websocket
async def websocket_handler(websocket, context):
    """Hive WebSocket handler with full agent orchestration."""
    global _active_session, _active_websocket
    await websocket.accept()
    _active_websocket = websocket
    session = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "init":
                user_id = data.get("user_id", "anonymous")
                session = HiveSession(user_id)
                await session.initialize()
                _active_session = session
                await websocket.send_json({
                    "type": "init_complete",
                    "config": session.config.to_dict(),
                })

            elif msg_type == "chat" and session:
                query = data.get("query", "")
                session.event_log.append("user", "message", {"query": query})
                target = await session.handle_query(query)
                await websocket.send_json({"type": "routed", "target": target})
                response = await session.get_response()
                if response:
                    await websocket.send_json({"type": "response", "data": response})
                else:
                    await websocket.send_json({"type": "error", "message": "Agent timeout"})

            elif msg_type == "add_channel" and session:
                channel_data = data.get("channel", {})
                channel_cfg = ChannelConfig.from_dict(channel_data)
                result = await session.channel_manager.register_channel(channel_cfg)
                session.config.channels.append(channel_cfg)
                session.state.save_config(session.config.to_dict())
                session.event_log.append("system", "channel_added", {"id": channel_cfg.id})

                # If WhatsApp, set up handler and relay QR/status
                if channel_cfg.provider == "whatsapp-baileys":
                    wa_channel = session.channel_manager.get_whatsapp_channel(channel_cfg.id)
                    if wa_channel:
                        session.setup_wa_handler(wa_channel)
                    if result.get("status") == "qr_needed":
                        await websocket.send_json({
                            "type": "wa_qr",
                            "channel_id": channel_cfg.id,
                            "qr": result.get("qr", ""),
                        })
                    elif result.get("status") == "connected":
                        await websocket.send_json({
                            "type": "wa_connected",
                            "channel_id": channel_cfg.id,
                            "phone": result.get("phone", ""),
                        })

                await websocket.send_json({
                    "type": "channel_added",
                    "channel": channel_data,
                    "config": session.config.to_dict(),
                })

            elif msg_type == "wa_approve" and session and session.wa_handler:
                approval_id = data.get("approval_id", "")
                action = data.get("action", "reject")
                edited = data.get("response", "")
                await session.wa_handler.handle_approval(approval_id, action, edited)

            elif msg_type == "get_events" and session:
                events = session.event_log.get_recent(data.get("count", 50))
                await websocket.send_json({"type": "events", "events": events})

            elif msg_type == "get_config" and session:
                await websocket.send_json({
                    "type": "config",
                    "config": session.config.to_dict(),
                })

            elif msg_type == "wipe" and session:
                session.shutdown()
                session.state.wipe()
                session = None
                _active_session = None
                await websocket.send_json({"type": "wiped"})

    except Exception as e:
        if "disconnect" not in str(e).lower():
            logger.error(f"WebSocket error: {e}")
    finally:
        if session:
            session.shutdown()
        _active_session = None
        _active_websocket = None


# Internal HTTP routes for sidecar communication
async def handle_wa_message(request: Request):
    """Receive incoming WhatsApp message from sidecar."""
    global _active_session
    if not _active_session or not _active_session.wa_handler:
        return JSONResponse({"error": "No active session"}, status_code=503)
    payload = await request.json()
    asyncio.create_task(_active_session.wa_handler.handle_message(payload))
    return JSONResponse({"ok": True})


async def handle_wa_event(request: Request):
    """Receive WhatsApp connection events from sidecar (qr, connected, disconnected)."""
    global _active_session, _active_websocket
    payload = await request.json()
    event = payload.get("event")

    if _active_websocket:
        if event == "qr":
            await _active_websocket.send_json({
                "type": "wa_qr",
                "channel_id": "whatsapp",
                "qr": payload.get("qr", ""),
            })
        elif event == "connected":
            await _active_websocket.send_json({
                "type": "wa_connected",
                "channel_id": "whatsapp",
                "phone": payload.get("phone", ""),
            })
            # Persist auth state on successful connection
            if _active_session:
                for ch in _active_session.channel_manager.communication_channels.values():
                    if hasattr(ch, "persist_auth_to_s3"):
                        ch.persist_auth_to_s3()
        elif event == "disconnected":
            await _active_websocket.send_json({
                "type": "wa_status",
                "channel_id": "whatsapp",
                "connected": False,
            })

    return JSONResponse({"ok": True})


# Register internal routes with the app's underlying ASGI app
app.routes.extend([
    Route("/internal/wa-message", handle_wa_message, methods=["POST"]),
    Route("/internal/wa-event", handle_wa_event, methods=["POST"]),
])


if __name__ == "__main__":
    app.run(host="0.0.0.0", log_level="info")
```

- [ ] **Step 2: Verify app imports succeed**

Run: `cd containers/hive && python -c "import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add containers/hive/app.py
git commit -m "feat(hive): wire WhatsApp sidecar into app with internal HTTP routes"
```

---

### Task 7: Update UI Types

**Files:**
- Modify: `artifacts/chat-ui/src/components/hive/types.ts`

- [ ] **Step 1: Add WhatsApp message types to types.ts**

Add to the `HiveMessage` union type:

```typescript
    | { type: "wa_approve"; channel_id: string; approval_id: string; action: "send" | "edit" | "reject"; response?: string };
```

Add to the `HiveResponse` union type:

```typescript
    | { type: "wa_qr"; channel_id: string; qr: string }
    | { type: "wa_connected"; channel_id: string; phone: string }
    | { type: "wa_incoming"; channel_id: string; from: string; from_name: string; message: string; mode: string; proposed_response?: string; response?: string; approval_id?: string }
    | { type: "wa_status"; channel_id: string; connected: boolean };
```

The full updated `types.ts`:

```typescript
export interface AgentConfig {
    id: string;
    name: string;
    type: "default" | "custom";
    system_prompt: string;
    model: string;
    tools: string[];
    channels: string[];
    mcp_channels: string[];
    autonomy: "ask" | "notify" | "silent";
}

export interface ChannelConfig {
    id: string;
    type: "communication" | "data";
    provider: string;
    config: Record<string, any>;
    permissions: string[];
    agents: string[];
}

export interface HiveConfig {
    agents: AgentConfig[];
    channels: ChannelConfig[];
}

export interface HiveEvent {
    timestamp: number;
    agent: string;
    event: string;
    data: Record<string, any>;
}

export interface CronJob {
    id: string;
    name: string;
    schedule: string;
    action: string;
    payload: Record<string, any>;
    agent_id: string;
    notify_channel: string;
}

export type AgentStatus = "idle" | "thinking" | "acting" | "error";

export type HiveMessage =
    | { type: "init"; user_id: string }
    | { type: "chat"; query: string }
    | { type: "get_events"; count?: number }
    | { type: "get_config" }
    | { type: "add_channel"; channel: ChannelConfig }
    | { type: "remove_channel"; channel_id: string }
    | { type: "list_channels" }
    | { type: "wa_approve"; channel_id: string; approval_id: string; action: "send" | "edit" | "reject"; response?: string }
    | { type: "wipe" };

export type HiveResponse =
    | { type: "init_complete"; config: HiveConfig }
    | { type: "routed"; target: string }
    | { type: "response"; data: Record<string, any> }
    | { type: "events"; events: HiveEvent[] }
    | { type: "config"; config: HiveConfig }
    | { type: "channel_added"; channel_id: string; channel?: any; config?: HiveConfig }
    | { type: "channels"; channels: any[] }
    | { type: "wa_qr"; channel_id: string; qr: string }
    | { type: "wa_connected"; channel_id: string; phone: string }
    | { type: "wa_incoming"; channel_id: string; from: string; from_name: string; message: string; mode: string; proposed_response?: string; response?: string; approval_id?: string }
    | { type: "wa_status"; channel_id: string; connected: boolean }
    | { type: "wiped" }
    | { type: "error"; message: string };
```

- [ ] **Step 2: Commit**

```bash
git add artifacts/chat-ui/src/components/hive/types.ts
git commit -m "feat(hive-ui): add WhatsApp WebSocket message types"
```

---

### Task 8: QR Code Modal Component

**Files:**
- Create: `artifacts/chat-ui/src/components/hive/wa-qr-modal.tsx`

- [ ] **Step 1: Create wa-qr-modal.tsx**

```tsx
import { Modal, Box, SpaceBetween, StatusIndicator, Spinner } from "@cloudscape-design/components";

interface WaQrModalProps {
    visible: boolean;
    qrDataUrl: string | null;
    connected: boolean;
    phone: string;
    onDismiss: () => void;
}

export function WaQrModal({ visible, qrDataUrl, connected, phone, onDismiss }: WaQrModalProps) {
    return (
        <Modal
            visible={visible}
            onDismiss={onDismiss}
            header="Link WhatsApp"
            closeAriaLabel="Close"
        >
            <SpaceBetween size="m" alignItems="center">
                {connected ? (
                    <>
                        <StatusIndicator type="success">
                            Connected to WhatsApp ({phone})
                        </StatusIndicator>
                        <p>Your WhatsApp is linked. You can close this dialog.</p>
                    </>
                ) : qrDataUrl ? (
                    <>
                        <p>Scan this QR code with your WhatsApp app:</p>
                        <p style={{ fontSize: "12px", color: "#888" }}>
                            WhatsApp → Settings → Linked Devices → Link a Device
                        </p>
                        <img
                            src={qrDataUrl}
                            alt="WhatsApp QR Code"
                            style={{ width: 280, height: 280, imageRendering: "pixelated" }}
                        />
                    </>
                ) : (
                    <>
                        <Spinner size="large" />
                        <p>Connecting to WhatsApp...</p>
                    </>
                )}
            </SpaceBetween>
        </Modal>
    );
}
```

- [ ] **Step 2: Commit**

```bash
git add artifacts/chat-ui/src/components/hive/wa-qr-modal.tsx
git commit -m "feat(hive-ui): add WhatsApp QR code modal component"
```

---

### Task 9: Update hive-layout.tsx to Handle WhatsApp Events

**Files:**
- Modify: `artifacts/chat-ui/src/components/hive/hive-layout.tsx`

- [ ] **Step 1: Add WA state and QR modal integration**

Add imports at the top:

```tsx
import { WaQrModal } from "./wa-qr-modal";
```

Add state variables after existing state declarations:

```tsx
    const [waQrVisible, setWaQrVisible] = useState(false);
    const [waQrData, setWaQrData] = useState<string | null>(null);
    const [waConnected, setWaConnected] = useState(false);
    const [waPhone, setWaPhone] = useState("");
```

Add WhatsApp cases to the `handleMessage` switch:

```tsx
            case "wa_qr":
                setWaQrData(msg.qr);
                setWaQrVisible(true);
                break;
            case "wa_connected":
                setWaConnected(true);
                setWaPhone(msg.phone);
                // Auto-dismiss after 2s
                setTimeout(() => setWaQrVisible(false), 2000);
                break;
            case "wa_incoming":
                setMessages((prev) => [
                    ...prev,
                    {
                        id: crypto.randomUUID(),
                        role: "system" as const,
                        content: `📱 WhatsApp from ${msg.from_name || msg.from}: ${msg.message}${msg.response ? `\n\n🤖 Reply: ${msg.response}` : ""}${msg.proposed_response ? `\n\n🤖 Proposed: ${msg.proposed_response}` : ""}`,
                        timestamp: Date.now(),
                    },
                ]);
                break;
            case "wa_status":
                setWaConnected(msg.connected);
                break;
```

Add the QR modal component before the closing `</SpaceBetween>`:

```tsx
            <WaQrModal
                visible={waQrVisible}
                qrDataUrl={waQrData}
                connected={waConnected}
                phone={waPhone}
                onDismiss={() => setWaQrVisible(false)}
            />
```

- [ ] **Step 2: Verify build succeeds**

Run: `cd artifacts/chat-ui && npm run build`
Expected: Build completes without errors.

- [ ] **Step 3: Commit**

```bash
git add artifacts/chat-ui/src/components/hive/hive-layout.tsx
git commit -m "feat(hive-ui): handle WhatsApp QR and incoming messages in layout"
```

---

### Task 10: Update Channel Config Wizard with Mode and Prefix Fields

**Files:**
- Modify: `artifacts/chat-ui/src/components/hive/channel-config.tsx`

- [ ] **Step 1: Add incoming_mode and reply_prefix fields to WhatsApp config step**

In the `renderProviderFields()` function, update the `whatsapp-baileys` case:

```tsx
            case "whatsapp-baileys":
                return (
                    <SpaceBetween size="m">
                        <FormField label="Phone Number">
                            <Input
                                value={config.phone_number || ""}
                                onChange={({ detail }) => setConfig({ ...config, phone_number: detail.value })}
                                placeholder="+61..."
                            />
                        </FormField>
                        <FormField label="Incoming Message Mode" description="How to handle messages received on WhatsApp">
                            <Select
                                selectedOption={
                                    [
                                        { label: "Ask (show in UI, wait for approval)", value: "ask" },
                                        { label: "Notify (auto-reply, show in UI)", value: "notify" },
                                        { label: "Silent (auto-reply, no UI notification)", value: "silent" },
                                        { label: "Redirect to Agent (Hive takes over)", value: "redirect-to-agent" },
                                    ].find((o) => o.value === (config.incoming_mode || "notify")) || null
                                }
                                onChange={({ detail }) => setConfig({ ...config, incoming_mode: detail.selectedOption?.value || "notify" })}
                                options={[
                                    { label: "Ask (show in UI, wait for approval)", value: "ask" },
                                    { label: "Notify (auto-reply, show in UI)", value: "notify" },
                                    { label: "Silent (auto-reply, no UI notification)", value: "silent" },
                                    { label: "Redirect to Agent (Hive takes over)", value: "redirect-to-agent" },
                                ]}
                            />
                        </FormField>
                        <FormField label="Reply Prefix (optional)" description="Text prepended to all agent replies, e.g. '[AI] '">
                            <Input
                                value={config.reply_prefix || ""}
                                onChange={({ detail }) => setConfig({ ...config, reply_prefix: detail.value })}
                                placeholder="[AI] "
                            />
                        </FormField>
                        <Alert type="info">
                            After saving, you'll need to scan a QR code with your WhatsApp to link the device.
                            Note: Baileys is unofficial — WhatsApp may break compatibility.
                        </Alert>
                    </SpaceBetween>
                );
```

- [ ] **Step 2: Verify build succeeds**

Run: `cd artifacts/chat-ui && npm run build`
Expected: Build completes without errors.

- [ ] **Step 3: Commit**

```bash
git add artifacts/chat-ui/src/components/hive/channel-config.tsx
git commit -m "feat(hive-ui): add incoming mode and reply prefix to WhatsApp config wizard"
```

---

### Task 11: Integration Test — Docker Build and Local E2E

**Files:**
- No new files

- [ ] **Step 1: Build the full container**

Run: `docker build --platform linux/arm64 -t hive-dev containers/hive/`
Expected: Build succeeds, sidecar `node_modules/` installed.

- [ ] **Step 2: Run container and verify sidecar starts**

Run:
```bash
docker run --rm -d -p 8080:8080 \
  -e REGION=us-east-1 \
  -e HIVE_STATE_BUCKET=srd-hive-state-dev-444206144756 \
  -e HIVE_KMS_KEY_ID=ee6c2653-3cd8-4ade-a298-56a479a1a28b \
  -e AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id) \
  -e AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key) \
  --name hive-wa-test hive-dev:latest
```

Then test WebSocket init and add_channel:
```python
import asyncio, websockets, json

async def test():
    async with websockets.connect('ws://localhost:8080/ws') as ws:
        await ws.send(json.dumps({'type': 'init', 'user_id': 'test-wa'}))
        resp = await asyncio.wait_for(ws.recv(), timeout=10)
        print(f'Init: {json.loads(resp)["type"]}')

        await ws.send(json.dumps({
            'type': 'add_channel',
            'channel': {
                'id': 'whazbot',
                'type': 'communication',
                'provider': 'whatsapp-baileys',
                'config': {'phone_number': '+1234', 'incoming_mode': 'notify', 'reply_prefix': ''},
                'permissions': ['read', 'send'],
                'agents': ['pa-agent']
            }
        }))
        # Should get wa_qr or channel_added
        for _ in range(3):
            resp = await asyncio.wait_for(ws.recv(), timeout=20)
            data = json.loads(resp)
            print(f'Got: {data["type"]}')
            if data['type'] == 'wa_qr':
                print('QR code received!')
                break

asyncio.run(test())
```

Expected: `wa_qr` message with QR data URI.

- [ ] **Step 3: Build UI and verify**

Run: `cd artifacts/chat-ui && npm run build`
Expected: Build succeeds.

- [ ] **Step 4: Clean up test container**

Run: `docker stop hive-wa-test && docker rm hive-wa-test`

- [ ] **Step 5: Commit any fixes if needed, then final commit**

```bash
git add -A
git commit -m "feat(hive): WhatsApp Baileys channel integration complete"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Baileys sidecar (Task 1)
- ✅ Auth state persistence to S3 (Task 3)
- ✅ QR code relay to UI (Tasks 6, 8, 9)
- ✅ Incoming message modes (ask/notify/silent/redirect-to-agent) (Task 4)
- ✅ Contact overrides (Task 3 — `get_mode_for_sender`)
- ✅ Configurable reply prefix (Tasks 3, 10)
- ✅ WebSocket protocol extensions (Tasks 6, 7)
- ✅ UI QR modal (Task 8)
- ✅ UI incoming message display (Task 9)
- ✅ Channel config wizard fields (Task 10)
- ✅ Dockerfile update (Task 2)
- ✅ Internal HTTP endpoint (Task 6)

**Placeholder scan:** None found.

**Type consistency:** `WhatsAppChannel` constructor takes `(config, bucket, user_id)` in Task 3, and `ChannelManager` passes those in Task 5. `wa_handler.handle_message` signature matches what `handle_wa_message` passes in Task 6. WebSocket message types in Task 7 match what's sent in Tasks 6/9.
