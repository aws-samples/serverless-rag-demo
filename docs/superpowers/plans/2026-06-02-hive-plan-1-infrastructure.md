# Hive Plan 1: Infrastructure & Core Runtime

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the Hive CDK stack with per-user container orchestration, S3 state, DynamoDB user mapping, and the Hive Core Python runtime skeleton.

**Architecture:** Opt-in `HiveStack` in CDK creates S3 state bucket, KMS key, DynamoDB user-container mapping, and AgentCore runtime. The container runs a FastAPI process that manages WebSocket connections, loads user state from S3, and exposes the message bus.

**Tech Stack:** CDK Python, AgentCore, FastAPI, asyncio, boto3, S3, DynamoDB, KMS

---

## File Structure

```
infrastructure/hive_stack.py              — CDK stack (S3, KMS, DynamoDB, IAM, AgentCore)
containers/hive/Dockerfile                — ARM64 container definition
containers/hive/requirements.txt          — Python dependencies
containers/hive/app.py                    — AgentCore entrypoint + WebSocket handler
containers/hive/hive_core/__init__.py     — Package init
containers/hive/hive_core/state.py        — S3 state manager (load/save/wipe)
containers/hive/hive_core/bus.py          — Async message bus
containers/hive/hive_core/event_log.py    — Append-only event log
containers/hive/hive_core/config.py       — User config schema + defaults
tests/unit/hive/__init__.py               — Test package
tests/unit/hive/test_state.py             — State manager tests
tests/unit/hive/test_bus.py               — Message bus tests
tests/unit/hive/test_event_log.py         — Event log tests
tests/unit/hive/test_config.py            — Config schema tests
app.py                                    — Modified: conditional HiveStack
deploy.sh                                 — Modified: Hive opt-in prompt
artifacts/chat-ui/src/runtime-config.ts   — Modified: hiveEnabled flag
```

---

### Task 1: S3 State Manager

**Files:**
- Create: `containers/hive/hive_core/__init__.py`
- Create: `containers/hive/hive_core/state.py`
- Create: `tests/unit/hive/__init__.py`
- Create: `tests/unit/hive/test_state.py`

- [ ] **Step 1: Write failing tests for StateManager**

```python
# tests/unit/hive/__init__.py
# (empty)

# tests/unit/hive/test_state.py
import json
import pytest
from unittest.mock import MagicMock, patch
from hive_core.state import StateManager


@pytest.fixture
def mock_s3():
    with patch("hive_core.state.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        yield mock_client


@pytest.fixture
def state_mgr(mock_s3):
    return StateManager(bucket="hive-state-test", user_id="user-123", kms_key_id="key-abc")


def test_load_config_returns_default_when_not_found(state_mgr, mock_s3):
    from botocore.exceptions import ClientError
    mock_s3.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey"}}, "GetObject"
    )
    config = state_mgr.load_config()
    assert config["agents"] == []
    assert config["channels"] == []


def test_load_config_returns_stored_config(state_mgr, mock_s3):
    stored = {"agents": [{"id": "pa-agent"}], "channels": []}
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: json.dumps(stored).encode())
    }
    config = state_mgr.load_config()
    assert config["agents"][0]["id"] == "pa-agent"


def test_save_config_writes_to_s3(state_mgr, mock_s3):
    config = {"agents": [], "channels": [{"id": "slack-1"}]}
    state_mgr.save_config(config)
    mock_s3.put_object.assert_called_once()
    call_kwargs = mock_s3.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "hive-state-test"
    assert call_kwargs["Key"] == "users/user-123/config.json"
    assert "slack-1" in call_kwargs["Body"]


def test_save_secrets_encrypts_with_kms(state_mgr, mock_s3):
    secrets = {"slack_token": "xoxb-123"}
    state_mgr.save_secrets(secrets)
    call_kwargs = mock_s3.put_object.call_args[1]
    assert call_kwargs["Key"] == "users/user-123/secrets.enc"
    assert call_kwargs["ServerSideEncryption"] == "aws:kms"
    assert call_kwargs["SSEKMSKeyId"] == "key-abc"


def test_load_secrets_returns_empty_when_not_found(state_mgr, mock_s3):
    from botocore.exceptions import ClientError
    mock_s3.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey"}}, "GetObject"
    )
    secrets = state_mgr.load_secrets()
    assert secrets == {}


def test_wipe_deletes_user_prefix(state_mgr, mock_s3):
    mock_s3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "users/user-123/config.json"},
            {"Key": "users/user-123/secrets.enc"},
        ]
    }
    state_mgr.wipe()
    mock_s3.delete_objects.assert_called_once()


def test_save_script(state_mgr, mock_s3):
    state_mgr.save_script("daily_report.py", "print('hello')")
    call_kwargs = mock_s3.put_object.call_args[1]
    assert call_kwargs["Key"] == "users/user-123/scripts/daily_report.py"
    assert call_kwargs["Body"] == "print('hello')"


def test_load_script(state_mgr, mock_s3):
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"print('world')")
    }
    content = state_mgr.load_script("daily_report.py")
    assert content == "print('world')"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hive_core'`

- [ ] **Step 3: Implement StateManager**

```python
# containers/hive/hive_core/__init__.py
# Hive Core package

# containers/hive/hive_core/state.py
import json
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "agents": [],
    "channels": [],
}


class StateManager:
    """Manages per-user durable state in S3."""

    def __init__(self, bucket: str, user_id: str, kms_key_id: str):
        self.bucket = bucket
        self.user_id = user_id
        self.kms_key_id = kms_key_id
        self.prefix = f"users/{user_id}"
        self.s3 = boto3.client("s3")

    def _get_json(self, key: str, default=None):
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            return json.loads(resp["Body"].read())
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return default if default is not None else {}
            raise

    def _put_json(self, key: str, data: dict, encrypt: bool = False):
        kwargs = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": json.dumps(data),
            "ContentType": "application/json",
        }
        if encrypt:
            kwargs["ServerSideEncryption"] = "aws:kms"
            kwargs["SSEKMSKeyId"] = self.kms_key_id
        self.s3.put_object(**kwargs)

    def load_config(self) -> dict:
        return self._get_json(f"{self.prefix}/config.json", DEFAULT_CONFIG.copy())

    def save_config(self, config: dict):
        self._put_json(f"{self.prefix}/config.json", config)

    def load_secrets(self) -> dict:
        return self._get_json(f"{self.prefix}/secrets.enc", {})

    def save_secrets(self, secrets: dict):
        self._put_json(f"{self.prefix}/secrets.enc", secrets, encrypt=True)

    def save_script(self, name: str, content: str):
        self.s3.put_object(
            Bucket=self.bucket,
            Key=f"{self.prefix}/scripts/{name}",
            Body=content,
        )

    def load_script(self, name: str) -> str:
        resp = self.s3.get_object(
            Bucket=self.bucket, Key=f"{self.prefix}/scripts/{name}"
        )
        return resp["Body"].read().decode()

    def wipe(self):
        """Delete all state for this user."""
        resp = self.s3.list_objects_v2(
            Bucket=self.bucket, Prefix=f"{self.prefix}/"
        )
        if "Contents" not in resp:
            return
        objects = [{"Key": obj["Key"]} for obj in resp["Contents"]]
        self.s3.delete_objects(
            Bucket=self.bucket, Delete={"Objects": objects}
        )
        logger.info(f"Wiped state for user {self.user_id}: {len(objects)} objects deleted")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_state.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add containers/hive/hive_core/__init__.py containers/hive/hive_core/state.py tests/unit/hive/__init__.py tests/unit/hive/test_state.py
git commit -m "feat(hive): add S3 StateManager with load/save/wipe"
```

---

### Task 2: Async Message Bus

**Files:**
- Create: `containers/hive/hive_core/bus.py`
- Create: `tests/unit/hive/test_bus.py`

- [ ] **Step 1: Write failing tests for MessageBus**

```python
# tests/unit/hive/test_bus.py
import asyncio
import pytest
from hive_core.bus import MessageBus, Message


@pytest.fixture
def bus():
    return MessageBus()


@pytest.mark.asyncio
async def test_publish_and_subscribe(bus):
    received = []

    async def handler(msg: Message):
        received.append(msg)

    bus.subscribe("test-agent", handler)
    await bus.publish(Message(
        source="core", target="test-agent", msg_type="task", payload={"query": "hello"}
    ))
    await asyncio.sleep(0.01)
    assert len(received) == 1
    assert received[0].payload["query"] == "hello"


@pytest.mark.asyncio
async def test_broadcast(bus):
    received_a = []
    received_b = []

    async def handler_a(msg: Message):
        received_a.append(msg)

    async def handler_b(msg: Message):
        received_b.append(msg)

    bus.subscribe("agent-a", handler_a)
    bus.subscribe("agent-b", handler_b)
    await bus.broadcast(Message(
        source="core", target="*", msg_type="system", payload={"event": "shutdown"}
    ))
    await asyncio.sleep(0.01)
    assert len(received_a) == 1
    assert len(received_b) == 1


@pytest.mark.asyncio
async def test_unsubscribe(bus):
    received = []

    async def handler(msg: Message):
        received.append(msg)

    bus.subscribe("agent-x", handler)
    bus.unsubscribe("agent-x")
    await bus.publish(Message(
        source="core", target="agent-x", msg_type="task", payload={}
    ))
    await asyncio.sleep(0.01)
    assert len(received) == 0


@pytest.mark.asyncio
async def test_message_logged_to_history(bus):
    bus.subscribe("agent-y", lambda msg: asyncio.sleep(0))
    msg = Message(source="core", target="agent-y", msg_type="task", payload={"q": "test"})
    await bus.publish(msg)
    await asyncio.sleep(0.01)
    assert len(bus.history) == 1
    assert bus.history[0].source == "core"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_bus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hive_core.bus'`

- [ ] **Step 3: Implement MessageBus**

```python
# containers/hive/hive_core/bus.py
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

MessageHandler = Callable[["Message", ], Awaitable[None]]


@dataclass
class Message:
    source: str
    target: str  # agent_id or "*" for broadcast
    msg_type: str  # "task", "response", "system", "agent_request"
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class MessageBus:
    """In-process async message bus for agent communication."""

    def __init__(self):
        self._subscribers: dict[str, MessageHandler] = {}
        self.history: list[Message] = []

    def subscribe(self, agent_id: str, handler: MessageHandler):
        self._subscribers[agent_id] = handler
        logger.debug(f"Agent '{agent_id}' subscribed to bus")

    def unsubscribe(self, agent_id: str):
        self._subscribers.pop(agent_id, None)
        logger.debug(f"Agent '{agent_id}' unsubscribed from bus")

    async def publish(self, message: Message):
        """Send message to a specific agent."""
        self.history.append(message)
        handler = self._subscribers.get(message.target)
        if handler:
            asyncio.create_task(handler(message))
        else:
            logger.warning(f"No subscriber for target '{message.target}'")

    async def broadcast(self, message: Message):
        """Send message to all subscribers."""
        self.history.append(message)
        for agent_id, handler in self._subscribers.items():
            asyncio.create_task(handler(message))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_bus.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add containers/hive/hive_core/bus.py tests/unit/hive/test_bus.py
git commit -m "feat(hive): add async MessageBus with pub/sub and history"
```

---

### Task 3: Event Log

**Files:**
- Create: `containers/hive/hive_core/event_log.py`
- Create: `tests/unit/hive/test_event_log.py`

- [ ] **Step 1: Write failing tests for EventLog**

```python
# tests/unit/hive/test_event_log.py
import json
import pytest
from unittest.mock import MagicMock, patch
from hive_core.event_log import EventLog


@pytest.fixture
def mock_s3():
    with patch("hive_core.event_log.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        yield mock_client


@pytest.fixture
def event_log(mock_s3):
    return EventLog(bucket="hive-state-test", user_id="user-123")


def test_append_event(event_log):
    event_log.append("pa-agent", "task_started", {"query": "hello"})
    assert len(event_log.buffer) == 1
    assert event_log.buffer[0]["agent"] == "pa-agent"
    assert event_log.buffer[0]["event"] == "task_started"


def test_flush_writes_to_s3(event_log, mock_s3):
    event_log.append("pa-agent", "task_started", {"query": "hello"})
    event_log.append("market-agent", "mcp_call", {"tool": "get_price"})
    event_log.flush()
    mock_s3.put_object.assert_called_once()
    call_kwargs = mock_s3.put_object.call_args[1]
    assert "event-log/" in call_kwargs["Key"]
    body = call_kwargs["Body"]
    lines = body.strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["agent"] == "pa-agent"


def test_flush_clears_buffer(event_log, mock_s3):
    event_log.append("pa-agent", "done", {})
    event_log.flush()
    assert len(event_log.buffer) == 0


def test_get_recent_returns_buffer(event_log):
    event_log.append("a", "e1", {})
    event_log.append("b", "e2", {})
    event_log.append("c", "e3", {})
    recent = event_log.get_recent(2)
    assert len(recent) == 2
    assert recent[0]["agent"] == "b"
    assert recent[1]["agent"] == "c"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_event_log.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement EventLog**

```python
# containers/hive/hive_core/event_log.py
import json
import logging
import time
from datetime import datetime, timezone
import boto3

logger = logging.getLogger(__name__)


class EventLog:
    """Append-only event log for agent activity. Powers the UI graph."""

    def __init__(self, bucket: str, user_id: str):
        self.bucket = bucket
        self.user_id = user_id
        self.buffer: list[dict] = []
        self.s3 = boto3.client("s3")

    def append(self, agent: str, event: str, data: dict):
        entry = {
            "timestamp": time.time(),
            "agent": agent,
            "event": event,
            "data": data,
        }
        self.buffer.append(entry)

    def get_recent(self, n: int = 50) -> list[dict]:
        return self.buffer[-n:]

    def flush(self):
        """Write buffered events to S3 as JSONL (appended to today's log)."""
        if not self.buffer:
            return

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"users/{self.user_id}/event-log/{today}.jsonl"
        body = "\n".join(json.dumps(e) for e in self.buffer)

        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/x-ndjson",
        )
        logger.info(f"Flushed {len(self.buffer)} events to {key}")
        self.buffer.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_event_log.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add containers/hive/hive_core/event_log.py tests/unit/hive/test_event_log.py
git commit -m "feat(hive): add append-only EventLog with S3 flush"
```

---

### Task 4: User Config Schema & Defaults

**Files:**
- Create: `containers/hive/hive_core/config.py`
- Create: `tests/unit/hive/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/hive/test_config.py
import pytest
from hive_core.config import (
    HiveConfig, AgentConfig, ChannelConfig,
    default_config, validate_config, DEFAULT_AGENTS,
)


def test_default_config_has_three_agents():
    config = default_config()
    assert len(config.agents) == 3
    agent_ids = [a.id for a in config.agents]
    assert "pa-agent" in agent_ids
    assert "reminder-agent" in agent_ids
    assert "market-agent" in agent_ids


def test_default_agents_have_correct_autonomy():
    config = default_config()
    for agent in config.agents:
        assert agent.autonomy == "ask"


def test_validate_config_rejects_invalid_autonomy():
    config = default_config()
    config.agents[0].autonomy = "yolo"
    errors = validate_config(config)
    assert len(errors) > 0
    assert "autonomy" in errors[0].lower()


def test_validate_config_rejects_duplicate_agent_ids():
    config = default_config()
    config.agents.append(AgentConfig(
        id="pa-agent", name="Duplicate", type="custom",
        system_prompt="test", model="x", tools=[], channels=[],
        mcp_channels=[], autonomy="ask"
    ))
    errors = validate_config(config)
    assert any("duplicate" in e.lower() for e in errors)


def test_validate_config_accepts_valid_config():
    config = default_config()
    errors = validate_config(config)
    assert errors == []


def test_config_to_dict_roundtrip():
    config = default_config()
    d = config.to_dict()
    restored = HiveConfig.from_dict(d)
    assert len(restored.agents) == len(config.agents)
    assert restored.agents[0].id == config.agents[0].id


def test_channel_config_serialization():
    ch = ChannelConfig(
        id="slack-1", type="communication", provider="slack",
        config={"webhook_url": "encrypted:abc"},
        permissions=["send", "receive"], agents=["pa-agent"]
    )
    d = ch.to_dict()
    assert d["provider"] == "slack"
    restored = ChannelConfig.from_dict(d)
    assert restored.id == "slack-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement config module**

```python
# containers/hive/hive_core/config.py
from dataclasses import dataclass, field, asdict
from typing import Any

VALID_AUTONOMY = ("ask", "notify", "silent")
VALID_CHANNEL_TYPES = ("communication", "data")
DEFAULT_MODEL = "global.anthropic.claude-sonnet-4-6-v1:0"


@dataclass
class AgentConfig:
    id: str
    name: str
    type: str  # "default" | "custom"
    system_prompt: str
    model: str
    tools: list[str]
    channels: list[str]
    mcp_channels: list[str]
    autonomy: str = "ask"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AgentConfig":
        return cls(**d)


@dataclass
class ChannelConfig:
    id: str
    type: str  # "communication" | "data"
    provider: str
    config: dict[str, Any]
    permissions: list[str]
    agents: list[str]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ChannelConfig":
        return cls(**d)


@dataclass
class HiveConfig:
    agents: list[AgentConfig] = field(default_factory=list)
    channels: list[ChannelConfig] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agents": [a.to_dict() for a in self.agents],
            "channels": [c.to_dict() for c in self.channels],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HiveConfig":
        return cls(
            agents=[AgentConfig.from_dict(a) for a in d.get("agents", [])],
            channels=[ChannelConfig.from_dict(c) for c in d.get("channels", [])],
        )


DEFAULT_AGENTS = [
    AgentConfig(
        id="pa-agent",
        name="Personal Assistant",
        type="default",
        system_prompt="You are a personal assistant. Help with general tasks, writing, summaries, and code execution. Be concise and helpful.",
        model=DEFAULT_MODEL,
        tools=["code_executor", "file_manager", "web_search"],
        channels=[],
        mcp_channels=[],
        autonomy="ask",
    ),
    AgentConfig(
        id="reminder-agent",
        name="Reminder Agent",
        type="default",
        system_prompt="You manage reminders, schedules, and recurring tasks. Create, list, and manage cron jobs. Always confirm scheduling details with the user.",
        model=DEFAULT_MODEL,
        tools=["cron_manager", "notification_sender"],
        channels=[],
        mcp_channels=[],
        autonomy="ask",
    ),
    AgentConfig(
        id="market-agent",
        name="Market Agent",
        type="default",
        system_prompt="You analyze markets, track stocks/crypto, summarize financial news, and provide portfolio insights. Use data channels for real-time data.",
        model=DEFAULT_MODEL,
        tools=["web_search", "data_analyzer"],
        channels=[],
        mcp_channels=[],
        autonomy="ask",
    ),
]


def default_config() -> HiveConfig:
    return HiveConfig(agents=list(DEFAULT_AGENTS), channels=[])


def validate_config(config: HiveConfig) -> list[str]:
    errors = []
    seen_ids = set()

    for agent in config.agents:
        if agent.autonomy not in VALID_AUTONOMY:
            errors.append(f"Agent '{agent.id}': autonomy must be one of {VALID_AUTONOMY}")
        if agent.id in seen_ids:
            errors.append(f"Duplicate agent id: '{agent.id}'")
        seen_ids.add(agent.id)

    for channel in config.channels:
        if channel.type not in VALID_CHANNEL_TYPES:
            errors.append(f"Channel '{channel.id}': type must be one of {VALID_CHANNEL_TYPES}")

    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_config.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add containers/hive/hive_core/config.py tests/unit/hive/test_config.py
git commit -m "feat(hive): add HiveConfig schema with defaults and validation"
```

---

### Task 5: Container Skeleton (Dockerfile + app.py)

**Files:**
- Create: `containers/hive/Dockerfile`
- Create: `containers/hive/requirements.txt`
- Create: `containers/hive/app.py`

- [ ] **Step 1: Create requirements.txt**

```text
bedrock-agentcore==1.2.0
strands-agents==1.28.0
strands-agents-tools==0.2.19
mcp==1.9.0
fastapi==0.115.0
uvicorn==0.34.0
apscheduler==3.11.0
boto3==1.42.83
```

- [ ] **Step 2: Create Dockerfile**

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

COPY . .

EXPOSE 8080

CMD ["python", "app.py"]
```

- [ ] **Step 3: Create app.py (AgentCore entrypoint with WebSocket)**

```python
# containers/hive/app.py
import asyncio
import json
import logging
import os
from bedrock_agentcore import BedrockAgentCoreApp
from hive_core.state import StateManager
from hive_core.bus import MessageBus, Message
from hive_core.event_log import EventLog
from hive_core.config import HiveConfig, default_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BUCKET = os.getenv("HIVE_STATE_BUCKET", "hive-state-test")
KMS_KEY_ID = os.getenv("HIVE_KMS_KEY_ID", "")
REGION = os.getenv("REGION", "us-east-1")

app = BedrockAgentCoreApp()


class HiveSession:
    """Per-user Hive session. Created on WebSocket connect."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.state = StateManager(bucket=BUCKET, user_id=user_id, kms_key_id=KMS_KEY_ID)
        self.bus = MessageBus()
        self.event_log = EventLog(bucket=BUCKET, user_id=user_id)
        self.config: HiveConfig = default_config()

    async def initialize(self):
        """Load state from S3 and set up agents."""
        stored = self.state.load_config()
        if stored.get("agents"):
            self.config = HiveConfig.from_dict(stored)
        else:
            self.config = default_config()
            self.state.save_config(self.config.to_dict())
        logger.info(f"Session initialized for {self.user_id} with {len(self.config.agents)} agents")


@app.websocket
async def websocket_handler(websocket, context):
    """Hive WebSocket handler."""
    await websocket.accept()
    session = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "init":
                user_id = data.get("user_id", "anonymous")
                session = HiveSession(user_id)
                await session.initialize()
                await websocket.send_json({
                    "type": "init_complete",
                    "config": session.config.to_dict(),
                })

            elif msg_type == "chat" and session:
                query = data.get("query", "")
                session.event_log.append("user", "message", {"query": query})
                # Route to core agent (implemented in Plan 2)
                await websocket.send_json({
                    "type": "ack",
                    "message": f"Received: {query}",
                })

            elif msg_type == "get_events" and session:
                events = session.event_log.get_recent(data.get("count", 50))
                await websocket.send_json({"type": "events", "events": events})

            elif msg_type == "wipe" and session:
                session.state.wipe()
                session = None
                await websocket.send_json({"type": "wiped"})

    except Exception as e:
        if "disconnect" not in str(e).lower():
            logger.error(f"WebSocket error: {e}")
    finally:
        if session:
            session.event_log.flush()
        await websocket.close()


if __name__ == "__main__":
    app.run(log_level="info")
```

- [ ] **Step 4: Verify container builds**

Run: `cd containers/hive && docker build --platform linux/arm64 -t hive-test .`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add containers/hive/Dockerfile containers/hive/requirements.txt containers/hive/app.py
git commit -m "feat(hive): add container skeleton with AgentCore WebSocket handler"
```

---

### Task 6: CDK HiveStack

**Files:**
- Create: `infrastructure/hive_stack.py`
- Modify: `app.py`
- Modify: `deploy.sh`

- [ ] **Step 1: Create HiveStack**

```python
# infrastructure/hive_stack.py
import os
from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    Duration,
    aws_s3 as s3,
    aws_kms as kms,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_ecr_assets as ecr_assets,
    Aspects,
)
from constructs import Construct
import cdk_nag as _cdk_nag


class HiveStack(Stack):

    def __init__(
        self, scope: Construct, construct_id: str, *,
        cognito_identity_pool_id: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Aspects.of(self).add(_cdk_nag.AwsSolutionsChecks())

        env_name = self.node.try_get_context("environment_name")
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT", "123456789012")
        region = os.getenv("CDK_DEFAULT_REGION", "us-east-1")

        # KMS key for encrypting user secrets
        hive_kms_key = kms.Key(
            self, f"srd-hive-key-{env_name}",
            alias=f"srd-hive-{env_name}",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # S3 bucket for per-user state
        state_bucket = s3.Bucket(
            self, f"srd-hive-state-{env_name}",
            bucket_name=f"srd-hive-state-{env_name}-{account_id}",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=hive_kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # DynamoDB table for user -> container mapping
        user_table = dynamodb.Table(
            self, f"srd-hive-users-{env_name}",
            table_name=f"srd-hive-users-{env_name}",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
        )

        # Container image
        hive_image = ecr_assets.DockerImageAsset(
            self, f"srd-hive-image-{env_name}",
            directory=os.path.join(os.getcwd(), "containers/hive"),
            platform=ecr_assets.Platform.LINUX_ARM64,
        )

        # IAM role for Hive runtime
        hive_role = iam.Role(
            self, f"srd-hive-role-{env_name}",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            ),
            inline_policies={
                "HivePolicy": iam.PolicyDocument(statements=[
                    # ECR pull
                    iam.PolicyStatement(
                        actions=[
                            "ecr:GetAuthorizationToken",
                            "ecr:BatchGetImage",
                            "ecr:GetDownloadUrlForLayer",
                        ],
                        resources=["*"],
                    ),
                    # Bedrock model access
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        resources=[
                            f"arn:aws:bedrock:{region}:{account_id}:inference-profile/*",
                            f"arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
                        ],
                    ),
                    # S3 state access (scoped to bucket)
                    iam.PolicyStatement(
                        actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
                        resources=[
                            state_bucket.bucket_arn,
                            f"{state_bucket.bucket_arn}/*",
                        ],
                    ),
                    # KMS access
                    iam.PolicyStatement(
                        actions=["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"],
                        resources=[hive_kms_key.key_arn],
                    ),
                    # DynamoDB access
                    iam.PolicyStatement(
                        actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"],
                        resources=[user_table.table_arn],
                    ),
                ]),
            },
        )

        # Outputs
        self.hive_image_uri = hive_image.image_uri
        self.hive_role_arn = hive_role.role_arn
        self.state_bucket_name = state_bucket.bucket_name
        self.kms_key_id = hive_kms_key.key_id

        CfnOutput(self, f"hive-image-{env_name}",
                  value=hive_image.image_uri,
                  description="Hive container image URI")
        CfnOutput(self, f"hive-role-{env_name}",
                  value=hive_role.role_arn,
                  description="Hive IAM role ARN")
        CfnOutput(self, f"hive-state-bucket-{env_name}",
                  value=state_bucket.bucket_name,
                  description="Hive S3 state bucket")
        CfnOutput(self, f"hive-kms-key-{env_name}",
                  value=hive_kms_key.key_id,
                  description="Hive KMS key ID")

        _cdk_nag.NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id="AwsSolutions-IAM5",
                reason="ECR pull requires wildcard; S3 scoped to hive bucket"),
        ])
```

- [ ] **Step 2: Modify app.py to conditionally include HiveStack**

Add after line 68 (after `cf_stack.add_dependency(agentcore_stack)`):

```python
# Stack 6 (optional): Hive Multi-Agent Platform
hive_enabled = app.node.try_get_context("hive_enabled") == "true"
if hive_enabled:
    from infrastructure.hive_stack import HiveStack
    hive_stack = HiveStack(
        app, f"SRD-Hive-{env_name}",
        cognito_identity_pool_id=cognito_stack.identity_pool_id,
        env=env,
    )
    hive_stack.add_dependency(cognito_stack)
    Tags.of(hive_stack).add("project", "serverless-rag-demo-v2")
```

- [ ] **Step 3: Modify deploy.sh to add Hive opt-in prompt**

Insert after OCU_MODE selection (line 45), before the summary display:

```bash
# Step 3b: Hive (Multi-Agent Platform)
echo ""
echo "  [3b] Enable Hive (Multi-Agent Platform)?"
echo "       Adds per-user agent containers with channel support (Slack, WhatsApp, MCP)"
echo "       Additional cost: ~\$0.05/hr per active user + S3/KMS"
read -p "       Enable? [y/N]: " HIVE_CHOICE
HIVE_CHOICE="${HIVE_CHOICE:-N}"
if [[ "$HIVE_CHOICE" == "y" || "$HIVE_CHOICE" == "Y" ]]; then
    HIVE_ENABLED="true"
else
    HIVE_ENABLED="false"
fi
```

Update the summary (step 4 display) to include:
```bash
echo "      Hive:        $HIVE_ENABLED"
```

Update CDK_CONTEXT to include:
```bash
CDK_CONTEXT="--context environment_name=$ENV_NAME --context is_aoss=yes --context embed_model_id=amazon.titan-embed-text-v2:0 --context ocu_mode=$OCU_MODE --context deployer_arn=$DEPLOYER_ARN --context hive_enabled=$HIVE_ENABLED"
```

Add deployment step (after Step D or equivalent):
```bash
if [[ "$HIVE_ENABLED" == "true" ]]; then
    echo "  [E] Deploying Hive Multi-Agent Platform..."
    cdk deploy "SRD-Hive-$ENV_NAME" $CDK_CONTEXT --require-approval never --outputs-file cdk-outputs.json
fi
```

- [ ] **Step 4: Modify runtime-config.ts to include hiveEnabled**

Add to the `RuntimeConfig` interface:
```typescript
hiveEnabled?: boolean;
hiveRuntimeArn?: string;
```

- [ ] **Step 5: Verify CDK synth**

Run: `cdk synth --context environment_name=test --context hive_enabled=true --context is_aoss=yes --context embed_model_id=amazon.titan-embed-text-v2:0 --context ocu_mode=demo --context deployer_arn=arn:aws:iam::123456789012:user/test 2>&1 | head -20`
Expected: No errors, shows SRD-Hive-test template

- [ ] **Step 6: Commit**

```bash
git add infrastructure/hive_stack.py app.py deploy.sh artifacts/chat-ui/src/runtime-config.ts
git commit -m "feat(hive): add CDK HiveStack with opt-in deploy"
```

---
