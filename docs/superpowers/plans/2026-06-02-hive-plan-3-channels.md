# Hive Plan 3: Channel System

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the unified channel system: MCP client pool for data channels, communication channel manager (Slack, WhatsApp via Baileys sidecar), and dynamic channel configuration.

**Architecture:** ChannelManager orchestrates all channels. MCP channels use the `mcp` Python SDK to connect via SSE or stdio, discover tools, and inject them into agents. Communication channels use a Node.js sidecar for WhatsApp (Baileys) and direct HTTP for Slack webhooks. IPC between Python and Node.js is local HTTP.

**Tech Stack:** mcp Python SDK, Node.js, Baileys, Slack SDK, FastAPI (IPC), asyncio

**Depends on:** Plan 1 (StateManager, Bus), Plan 2 (AgentRegistry, agents)

---

## File Structure

```
containers/hive/hive_core/channels/__init__.py       — Package init
containers/hive/hive_core/channels/manager.py        — ChannelManager (orchestrates all channels)
containers/hive/hive_core/channels/mcp_pool.py       — MCP connection pool (SSE + stdio)
containers/hive/hive_core/channels/slack.py          — Slack channel (webhook outbound, RTM inbound)
containers/hive/hive_core/channels/whatsapp.py       — WhatsApp channel (IPC to Node sidecar)
containers/hive/sidecar/package.json                 — Node.js sidecar dependencies
containers/hive/sidecar/index.js                     — Sidecar entrypoint (HTTP bridge)
containers/hive/sidecar/whatsapp.js                  — Baileys WhatsApp client
tests/unit/hive/test_mcp_pool.py                     — MCP pool tests
tests/unit/hive/test_channel_manager.py              — Channel manager tests
tests/unit/hive/test_slack_channel.py                — Slack channel tests
```

---

### Task 1: MCP Connection Pool

**Files:**
- Create: `containers/hive/hive_core/channels/__init__.py`
- Create: `containers/hive/hive_core/channels/mcp_pool.py`
- Create: `tests/unit/hive/test_mcp_pool.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/hive/test_mcp_pool.py
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
        config={"transport": "sse", "url": "http://localhost:8080/mcp", "api_key": "test-key"},
        permissions=["read"], agents=["pa-agent"]
    )
    with patch("hive_core.channels.mcp_pool.MCPPool._connect_sse") as mock_connect:
        mock_connect.return_value = MCPConnection(
            channel_id="test-mcp",
            tools=[{"name": "get_data", "description": "Gets data"}],
            client=MagicMock(),
        )
        conn = await pool.connect(config)
        assert conn.channel_id == "test-mcp"
        assert len(conn.tools) == 1


@pytest.mark.asyncio
async def test_connect_stdio_channel(pool):
    config = ChannelConfig(
        id="github-mcp", type="data", provider="mcp",
        config={"transport": "stdio", "command": "npx", "args": ["-y", "server-github"], "env": {}},
        permissions=["read", "write"], agents=["pa-agent"]
    )
    with patch("hive_core.channels.mcp_pool.MCPPool._connect_stdio") as mock_connect:
        mock_connect.return_value = MCPConnection(
            channel_id="github-mcp",
            tools=[{"name": "list_repos", "description": "List repos"}],
            client=MagicMock(),
        )
        conn = await pool.connect(config)
        assert conn.channel_id == "github-mcp"


def test_disconnect(pool):
    pool.connections["test-mcp"] = MCPConnection(
        channel_id="test-mcp", tools=[], client=MagicMock()
    )
    pool.disconnect("test-mcp")
    assert "test-mcp" not in pool.connections


def test_get_tools_for_agent(pool):
    pool.connections["mcp-1"] = MCPConnection(
        channel_id="mcp-1",
        tools=[{"name": "tool_a"}, {"name": "tool_b"}],
        client=MagicMock(),
    )
    pool.connections["mcp-2"] = MCPConnection(
        channel_id="mcp-2",
        tools=[{"name": "tool_c"}],
        client=MagicMock(),
    )
    pool._agent_mapping = {"pa-agent": ["mcp-1"], "market-agent": ["mcp-2"]}

    tools = pool.get_tools_for_agent("pa-agent")
    assert len(tools) == 2
    assert tools[0]["name"] == "tool_a"


def test_get_tools_for_unregistered_agent(pool):
    tools = pool.get_tools_for_agent("unknown-agent")
    assert tools == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_mcp_pool.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement MCPPool**

```python
# containers/hive/hive_core/channels/__init__.py
from .mcp_pool import MCPPool
from .manager import ChannelManager

__all__ = ["MCPPool", "ChannelManager"]

# containers/hive/hive_core/channels/mcp_pool.py
import logging
from dataclasses import dataclass, field
from typing import Any
from hive_core.config import ChannelConfig

logger = logging.getLogger(__name__)


@dataclass
class MCPConnection:
    channel_id: str
    tools: list[dict]
    client: Any  # MCP client instance


class MCPPool:
    """Manages MCP client connections for data channels."""

    def __init__(self):
        self.connections: dict[str, MCPConnection] = {}
        self._agent_mapping: dict[str, list[str]] = {}  # agent_id -> [channel_ids]

    async def connect(self, config: ChannelConfig) -> MCPConnection:
        """Establish MCP connection and discover tools."""
        transport = config.config.get("transport", "sse")

        if transport == "sse":
            conn = await self._connect_sse(config)
        elif transport == "stdio":
            conn = await self._connect_stdio(config)
        else:
            raise ValueError(f"Unknown MCP transport: {transport}")

        self.connections[config.id] = conn

        # Map agents to this channel
        for agent_id in config.agents:
            if agent_id not in self._agent_mapping:
                self._agent_mapping[agent_id] = []
            self._agent_mapping[agent_id].append(config.id)

        logger.info(f"MCP connected: {config.id} ({len(conn.tools)} tools discovered)")
        return conn

    async def _connect_sse(self, config: ChannelConfig) -> MCPConnection:
        """Connect to MCP server via SSE transport."""
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
                    tools = [
                        {"name": t.name, "description": t.description, "schema": t.inputSchema}
                        for t in tools_result.tools
                    ]
                    return MCPConnection(
                        channel_id=config.id,
                        tools=tools,
                        client=session,
                    )
        except Exception as e:
            logger.error(f"Failed to connect MCP SSE {config.id}: {e}")
            raise

    async def _connect_stdio(self, config: ChannelConfig) -> MCPConnection:
        """Connect to MCP server via stdio transport."""
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
                    tools = [
                        {"name": t.name, "description": t.description, "schema": t.inputSchema}
                        for t in tools_result.tools
                    ]
                    return MCPConnection(
                        channel_id=config.id,
                        tools=tools,
                        client=session,
                    )
        except Exception as e:
            logger.error(f"Failed to connect MCP stdio {config.id}: {e}")
            raise

    def disconnect(self, channel_id: str):
        """Disconnect an MCP channel."""
        if channel_id in self.connections:
            del self.connections[channel_id]
            # Clean up agent mapping
            for agent_id in list(self._agent_mapping.keys()):
                self._agent_mapping[agent_id] = [
                    cid for cid in self._agent_mapping[agent_id] if cid != channel_id
                ]
            logger.info(f"MCP disconnected: {channel_id}")

    def get_tools_for_agent(self, agent_id: str) -> list[dict]:
        """Get all MCP tools available to an agent."""
        channel_ids = self._agent_mapping.get(agent_id, [])
        tools = []
        for cid in channel_ids:
            conn = self.connections.get(cid)
            if conn:
                tools.extend(conn.tools)
        return tools

    async def call_tool(self, channel_id: str, tool_name: str, arguments: dict) -> Any:
        """Call an MCP tool on a specific channel."""
        conn = self.connections.get(channel_id)
        if not conn:
            raise ValueError(f"Channel {channel_id} not connected")

        result = await conn.client.call_tool(tool_name, arguments)
        return result

    def disconnect_all(self):
        """Disconnect all MCP channels."""
        for cid in list(self.connections.keys()):
            self.disconnect(cid)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_mcp_pool.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add containers/hive/hive_core/channels/__init__.py containers/hive/hive_core/channels/mcp_pool.py tests/unit/hive/test_mcp_pool.py
git commit -m "feat(hive): add MCP connection pool with SSE and stdio transports"
```

---

### Task 2: Slack Channel

**Files:**
- Create: `containers/hive/hive_core/channels/slack.py`
- Create: `tests/unit/hive/test_slack_channel.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/hive/test_slack_channel.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from hive_core.channels.slack import SlackChannel
from hive_core.config import ChannelConfig


@pytest.fixture
def slack_config():
    return ChannelConfig(
        id="slack-personal", type="communication", provider="slack",
        config={"webhook_url": "https://hooks.slack.com/services/T/B/xxx", "default_channel": "#alerts"},
        permissions=["send", "receive"], agents=["pa-agent"]
    )


@pytest.fixture
def slack_channel(slack_config):
    return SlackChannel(config=slack_config)


def test_slack_channel_creation(slack_channel):
    assert slack_channel.channel_id == "slack-personal"
    assert slack_channel.webhook_url == "https://hooks.slack.com/services/T/B/xxx"


@pytest.mark.asyncio
async def test_send_message(slack_channel):
    with patch("hive_core.channels.slack.aiohttp") as mock_aiohttp:
        mock_session = AsyncMock()
        mock_aiohttp.ClientSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_aiohttp.ClientSession.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = AsyncMock()

        await slack_channel.send("Hello from Hive!")
        mock_session.post.assert_called_once()


def test_format_message(slack_channel):
    payload = slack_channel._format_payload("Test message", channel="#general")
    assert payload["text"] == "Test message"
    assert payload["channel"] == "#general"


def test_format_message_uses_default_channel(slack_channel):
    payload = slack_channel._format_payload("Test message")
    assert payload["channel"] == "#alerts"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_slack_channel.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement SlackChannel**

```python
# containers/hive/hive_core/channels/slack.py
import logging
from typing import Optional
from hive_core.config import ChannelConfig

logger = logging.getLogger(__name__)


class SlackChannel:
    """Slack communication channel using webhooks for outbound."""

    def __init__(self, config: ChannelConfig):
        self.channel_id = config.id
        self.webhook_url = config.config.get("webhook_url", "")
        self.bot_token = config.config.get("bot_token", "")
        self.default_channel = config.config.get("default_channel", "#general")
        self.agents = config.agents

    def _format_payload(self, text: str, channel: Optional[str] = None) -> dict:
        return {
            "text": text,
            "channel": channel or self.default_channel,
        }

    async def send(self, text: str, channel: Optional[str] = None):
        """Send a message via Slack webhook."""
        import aiohttp

        payload = self._format_payload(text, channel)
        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Slack send failed ({resp.status}): {body}")
                else:
                    logger.debug(f"Slack message sent to {payload['channel']}")

    async def send_rich(self, blocks: list[dict], text: str = "", channel: Optional[str] = None):
        """Send a rich message with Slack blocks."""
        import aiohttp

        payload = {
            "text": text,
            "channel": channel or self.default_channel,
            "blocks": blocks,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"Slack rich send failed: {resp.status}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_slack_channel.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add containers/hive/hive_core/channels/slack.py tests/unit/hive/test_slack_channel.py
git commit -m "feat(hive): add Slack communication channel"
```

---

### Task 3: WhatsApp Channel (Python side + Node.js Sidecar)

**Files:**
- Create: `containers/hive/hive_core/channels/whatsapp.py`
- Create: `containers/hive/sidecar/package.json`
- Create: `containers/hive/sidecar/index.js`
- Create: `containers/hive/sidecar/whatsapp.js`

- [ ] **Step 1: Create Node.js sidecar package.json**

```json
{
  "name": "hive-sidecar",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "start": "node index.js"
  },
  "dependencies": {
    "@whiskeysockets/baileys": "^6.7.0",
    "express": "^4.21.0",
    "pino": "^9.0.0"
  }
}
```

- [ ] **Step 2: Create sidecar entrypoint (HTTP bridge)**

```javascript
// containers/hive/sidecar/index.js
import express from 'express';
import { WhatsAppClient } from './whatsapp.js';

const app = express();
app.use(express.json());

const PORT = process.env.SIDECAR_PORT || 3001;
const HIVE_CORE_URL = process.env.HIVE_CORE_URL || 'http://localhost:8080';

let waClient = null;

// Initialize WhatsApp client
app.post('/whatsapp/init', async (req, res) => {
    const { authStatePath } = req.body;
    try {
        waClient = new WhatsAppClient(authStatePath, HIVE_CORE_URL);
        const qrCode = await waClient.connect();
        res.json({ status: 'connecting', qr_code: qrCode });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Send WhatsApp message
app.post('/whatsapp/send', async (req, res) => {
    const { to, message } = req.body;
    if (!waClient) {
        return res.status(400).json({ error: 'WhatsApp not initialized' });
    }
    try {
        await waClient.sendMessage(to, message);
        res.json({ status: 'sent' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Get connection status
app.get('/whatsapp/status', (req, res) => {
    res.json({
        connected: waClient?.isConnected() ?? false,
        phone: waClient?.phoneNumber ?? null,
    });
});

// Health check
app.get('/health', (req, res) => {
    res.json({ status: 'ok' });
});

app.listen(PORT, () => {
    console.log(`Hive sidecar listening on port ${PORT}`);
});
```

- [ ] **Step 3: Create Baileys WhatsApp client**

```javascript
// containers/hive/sidecar/whatsapp.js
import makeWASocket, {
    useMultiFileAuthState,
    DisconnectReason,
} from '@whiskeysockets/baileys';
import pino from 'pino';

const logger = pino({ level: 'warn' });

export class WhatsAppClient {
    constructor(authStatePath, hiveCoreUrl) {
        this.authStatePath = authStatePath;
        this.hiveCoreUrl = hiveCoreUrl;
        this.sock = null;
        this.phoneNumber = null;
        this._connected = false;
    }

    isConnected() {
        return this._connected;
    }

    async connect() {
        const { state, saveCreds } = await useMultiFileAuthState(this.authStatePath);

        let qrCode = null;

        this.sock = makeWASocket({
            auth: state,
            logger,
            printQRInTerminal: false,
        });

        // Handle QR code for pairing
        this.sock.ev.on('connection.update', (update) => {
            const { connection, qr, lastDisconnect } = update;

            if (qr) {
                qrCode = qr;
            }

            if (connection === 'open') {
                this._connected = true;
                this.phoneNumber = this.sock.user?.id?.split(':')[0] || null;
                console.log('WhatsApp connected:', this.phoneNumber);
            }

            if (connection === 'close') {
                this._connected = false;
                const reason = lastDisconnect?.error?.output?.statusCode;
                if (reason !== DisconnectReason.loggedOut) {
                    // Reconnect
                    setTimeout(() => this.connect(), 5000);
                }
            }
        });

        // Save auth credentials on update
        this.sock.ev.on('creds.update', saveCreds);

        // Forward incoming messages to Hive Core
        this.sock.ev.on('messages.upsert', async ({ messages }) => {
            for (const msg of messages) {
                if (msg.key.fromMe) continue;
                const text = msg.message?.conversation ||
                    msg.message?.extendedTextMessage?.text || '';
                if (!text) continue;

                try {
                    await fetch(`${this.hiveCoreUrl}/channel/incoming`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            channel_id: 'whatsapp',
                            from: msg.key.remoteJid,
                            text: text,
                            timestamp: msg.messageTimestamp,
                        }),
                    });
                } catch (err) {
                    console.error('Failed to forward message to Hive Core:', err);
                }
            }
        });

        // Wait briefly for QR code generation
        await new Promise(resolve => setTimeout(resolve, 2000));
        return qrCode;
    }

    async sendMessage(to, text) {
        if (!this.sock || !this._connected) {
            throw new Error('WhatsApp not connected');
        }
        // Ensure JID format
        const jid = to.includes('@') ? to : `${to}@s.whatsapp.net`;
        await this.sock.sendMessage(jid, { text });
    }

    async disconnect() {
        if (this.sock) {
            await this.sock.logout();
            this._connected = false;
        }
    }
}
```

- [ ] **Step 4: Create Python WhatsApp channel wrapper**

```python
# containers/hive/hive_core/channels/whatsapp.py
import logging
from typing import Optional
import aiohttp
from hive_core.config import ChannelConfig

logger = logging.getLogger(__name__)

SIDECAR_URL = "http://localhost:3001"


class WhatsAppChannel:
    """WhatsApp communication channel via Baileys Node.js sidecar."""

    def __init__(self, config: ChannelConfig):
        self.channel_id = config.id
        self.phone_number = config.config.get("phone_number", "")
        self.auth_state_path = config.config.get("auth_state_path", "/tmp/wa-auth")
        self.agents = config.agents
        self._connected = False

    async def initialize(self) -> Optional[str]:
        """Initialize WhatsApp connection. Returns QR code if pairing needed."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{SIDECAR_URL}/whatsapp/init",
                json={"authStatePath": self.auth_state_path},
            ) as resp:
                data = await resp.json()
                if data.get("qr_code"):
                    return data["qr_code"]
                self._connected = True
                return None

    async def send(self, to: str, text: str):
        """Send a WhatsApp message."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{SIDECAR_URL}/whatsapp/send",
                json={"to": to, "message": text},
            ) as resp:
                if resp.status != 200:
                    body = await resp.json()
                    logger.error(f"WhatsApp send failed: {body}")
                else:
                    logger.debug(f"WhatsApp message sent to {to}")

    async def get_status(self) -> dict:
        """Get WhatsApp connection status."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{SIDECAR_URL}/whatsapp/status") as resp:
                return await resp.json()
```

- [ ] **Step 5: Commit**

```bash
git add containers/hive/hive_core/channels/whatsapp.py containers/hive/sidecar/package.json containers/hive/sidecar/index.js containers/hive/sidecar/whatsapp.js
git commit -m "feat(hive): add WhatsApp channel with Baileys Node.js sidecar"
```

---

### Task 4: Channel Manager

**Files:**
- Create: `containers/hive/hive_core/channels/manager.py`
- Create: `tests/unit/hive/test_channel_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/hive/test_channel_manager.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from hive_core.channels.manager import ChannelManager
from hive_core.config import ChannelConfig, HiveConfig
from hive_core.bus import MessageBus


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def manager(bus):
    return ChannelManager(bus=bus)


def test_manager_starts_empty(manager):
    assert len(manager.communication_channels) == 0
    assert len(manager.mcp_pool.connections) == 0


@pytest.mark.asyncio
async def test_register_slack_channel(manager):
    config = ChannelConfig(
        id="slack-1", type="communication", provider="slack",
        config={"webhook_url": "https://hooks.slack.com/T/B/x", "default_channel": "#test"},
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
    with patch.object(manager.mcp_pool, "connect", new_callable=AsyncMock) as mock_connect:
        from hive_core.channels.mcp_pool import MCPConnection
        mock_connect.return_value = MCPConnection(
            channel_id="mcp-1", tools=[{"name": "get_price"}], client=MagicMock()
        )
        await manager.register_channel(config)
        mock_connect.assert_called_once_with(config)


@pytest.mark.asyncio
async def test_send_to_channel(manager):
    config = ChannelConfig(
        id="slack-1", type="communication", provider="slack",
        config={"webhook_url": "https://hooks.slack.com/T/B/x", "default_channel": "#test"},
        permissions=["send"], agents=["pa-agent"]
    )
    await manager.register_channel(config)

    with patch.object(manager.communication_channels["slack-1"], "send", new_callable=AsyncMock) as mock_send:
        await manager.send("slack-1", "Hello!")
        mock_send.assert_called_once_with("Hello!")


def test_list_channels(manager):
    # No async needed for listing
    channels = manager.list_channels()
    assert channels == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_channel_manager.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement ChannelManager**

```python
# containers/hive/hive_core/channels/manager.py
import logging
from typing import Any
from hive_core.bus import MessageBus, Message
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
        self.communication_channels: dict[str, Any] = {}  # id -> SlackChannel | WhatsAppChannel
        self._channel_configs: list[ChannelConfig] = []

    async def register_channel(self, config: ChannelConfig):
        """Register a new channel (communication or data)."""
        self._channel_configs.append(config)

        if config.type == "data" and config.provider == "mcp":
            await self.mcp_pool.connect(config)
        elif config.type == "communication":
            if config.provider == "slack":
                self.communication_channels[config.id] = SlackChannel(config)
            elif config.provider == "whatsapp-baileys":
                channel = WhatsAppChannel(config)
                self.communication_channels[config.id] = channel
            else:
                logger.warning(f"Unknown communication provider: {config.provider}")

        logger.info(f"Channel registered: {config.id} ({config.provider})")

    async def unregister_channel(self, channel_id: str):
        """Remove a channel."""
        if channel_id in self.communication_channels:
            del self.communication_channels[channel_id]
        elif channel_id in self.mcp_pool.connections:
            self.mcp_pool.disconnect(channel_id)
        self._channel_configs = [c for c in self._channel_configs if c.id != channel_id]

    async def send(self, channel_id: str, text: str, **kwargs):
        """Send a message via a communication channel."""
        channel = self.communication_channels.get(channel_id)
        if not channel:
            logger.error(f"Channel {channel_id} not found")
            return
        await channel.send(text, **kwargs)

    def list_channels(self) -> list[dict]:
        """List all registered channels with their status."""
        result = []
        for config in self._channel_configs:
            status = "connected"
            if config.type == "data":
                status = "connected" if config.id in self.mcp_pool.connections else "disconnected"
            result.append({
                "id": config.id,
                "type": config.type,
                "provider": config.provider,
                "status": status,
                "agents": config.agents,
            })
        return result

    def get_mcp_tools_for_agent(self, agent_id: str) -> list[dict]:
        """Get all MCP tools available to a specific agent."""
        return self.mcp_pool.get_tools_for_agent(agent_id)

    async def shutdown(self):
        """Disconnect all channels."""
        self.mcp_pool.disconnect_all()
        self.communication_channels.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_channel_manager.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add containers/hive/hive_core/channels/manager.py tests/unit/hive/test_channel_manager.py
git commit -m "feat(hive): add ChannelManager orchestrating MCP + communication channels"
```

---

### Task 5: Update Dockerfile for Node.js Sidecar

**Files:**
- Modify: `containers/hive/Dockerfile`
- Modify: `containers/hive/requirements.txt`

- [ ] **Step 1: Update Dockerfile to install sidecar**

```dockerfile
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 for channel bridge sidecar
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Node.js sidecar deps
COPY sidecar/package.json sidecar/
RUN cd sidecar && npm install --production

# Copy application code
COPY . .

EXPOSE 8080 3001

# Start both Python app and Node.js sidecar
CMD ["sh", "-c", "node sidecar/index.js & python app.py"]
```

- [ ] **Step 2: Add aiohttp to requirements.txt**

```text
bedrock-agentcore==1.2.0
strands-agents==1.28.0
strands-agents-tools==0.2.19
mcp==1.9.0
fastapi==0.115.0
uvicorn==0.34.0
apscheduler==3.11.0
aiohttp==3.11.0
boto3==1.42.83
```

- [ ] **Step 3: Verify container builds**

Run: `cd containers/hive && docker build --platform linux/arm64 -t hive-test .`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add containers/hive/Dockerfile containers/hive/requirements.txt
git commit -m "feat(hive): update Dockerfile with Node.js sidecar and aiohttp"
```

---

### Task 6: Wire Channels into HiveSession

**Files:**
- Modify: `containers/hive/app.py`

- [ ] **Step 1: Update HiveSession to initialize channels**

In `containers/hive/app.py`, add to `HiveSession.__init__`:

```python
from hive_core.channels.manager import ChannelManager

# In __init__:
self.channel_manager = ChannelManager(bus=self.bus)
```

In `HiveSession.initialize()`, after loading config, add:

```python
# Initialize channels
for ch_config in self.config.channels:
    try:
        await self.channel_manager.register_channel(ch_config)
    except Exception as e:
        logger.warning(f"Failed to initialize channel {ch_config.id}: {e}")
```

Add WebSocket handlers for channel operations:

```python
elif msg_type == "add_channel" and session:
    from hive_core.config import ChannelConfig
    ch_config = ChannelConfig.from_dict(data.get("channel", {}))
    await session.channel_manager.register_channel(ch_config)
    session.config.channels.append(ch_config)
    session.state.save_config(session.config.to_dict())
    await websocket.send_json({"type": "channel_added", "channel_id": ch_config.id})

elif msg_type == "remove_channel" and session:
    channel_id = data.get("channel_id")
    await session.channel_manager.unregister_channel(channel_id)
    session.config.channels = [c for c in session.config.channels if c.id != channel_id]
    session.state.save_config(session.config.to_dict())
    await websocket.send_json({"type": "channel_removed", "channel_id": channel_id})

elif msg_type == "list_channels" and session:
    channels = session.channel_manager.list_channels()
    await websocket.send_json({"type": "channels", "channels": channels})
```

In `HiveSession.shutdown()`, add:

```python
await self.channel_manager.shutdown()
```

- [ ] **Step 2: Commit**

```bash
git add containers/hive/app.py
git commit -m "feat(hive): wire ChannelManager into HiveSession lifecycle"
```

---
