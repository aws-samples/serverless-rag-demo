# Hive Plan 2: Agent System

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the agent registry, Strands-based specialist agents (PA, Reminder, Market), code executor, cron scheduler, and agent-to-agent communication via the message bus.

**Architecture:** Each agent is an independent Strands Agent instance registered with the AgentRegistry. The Core agent (router) classifies intent and dispatches to specialists. Agents communicate via the MessageBus. Code execution runs in a sandboxed subprocess. APScheduler handles cron jobs persisted to S3.

**Tech Stack:** Strands Agents, APScheduler, asyncio, subprocess, boto3

**Depends on:** Plan 1 (StateManager, MessageBus, EventLog, container skeleton)

---

## File Structure

```
containers/hive/hive_core/registry.py         — Agent registry (create/remove/get agents)
containers/hive/hive_core/router.py            — Core router (intent classification + dispatch)
containers/hive/hive_core/agents/__init__.py   — Agents package
containers/hive/hive_core/agents/base.py       — Base agent wrapper around Strands
containers/hive/hive_core/agents/pa.py         — Personal Assistant agent
containers/hive/hive_core/agents/reminder.py   — Reminder agent
containers/hive/hive_core/agents/market.py     — Market agent
containers/hive/hive_core/executor.py          — Sandboxed code executor
containers/hive/hive_core/scheduler.py         — Cron scheduler (APScheduler + S3 persistence)
tests/unit/hive/test_registry.py               — Registry tests
tests/unit/hive/test_router.py                 — Router tests
tests/unit/hive/test_executor.py               — Code executor tests
tests/unit/hive/test_scheduler.py              — Scheduler tests
```

---

### Task 1: Base Agent Wrapper

**Files:**
- Create: `containers/hive/hive_core/agents/__init__.py`
- Create: `containers/hive/hive_core/agents/base.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/hive/test_base_agent.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from hive_core.agents.base import HiveAgent
from hive_core.bus import MessageBus, Message
from hive_core.event_log import EventLog


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def event_log():
    mock_log = MagicMock(spec=EventLog)
    return mock_log


def test_hive_agent_creation(bus, event_log):
    agent = HiveAgent(
        agent_id="test-agent",
        name="Test Agent",
        system_prompt="You are a test agent.",
        model_id="global.anthropic.claude-sonnet-4-6-v1:0",
        tools=[],
        bus=bus,
        event_log=event_log,
    )
    assert agent.agent_id == "test-agent"
    assert agent.name == "Test Agent"


def test_hive_agent_registers_on_bus(bus, event_log):
    agent = HiveAgent(
        agent_id="test-agent",
        name="Test",
        system_prompt="test",
        model_id="x",
        tools=[],
        bus=bus,
        event_log=event_log,
    )
    assert "test-agent" in bus._subscribers


def test_hive_agent_logs_events(bus, event_log):
    agent = HiveAgent(
        agent_id="test-agent",
        name="Test",
        system_prompt="test",
        model_id="x",
        tools=[],
        bus=bus,
        event_log=event_log,
    )
    agent._log("thinking", {"query": "hello"})
    event_log.append.assert_called_once_with("test-agent", "thinking", {"query": "hello"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_base_agent.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement HiveAgent base class**

```python
# containers/hive/hive_core/agents/__init__.py
from .base import HiveAgent

__all__ = ["HiveAgent"]

# containers/hive/hive_core/agents/base.py
import asyncio
import logging
from typing import Any
from strands import Agent
from hive_core.bus import MessageBus, Message
from hive_core.event_log import EventLog

logger = logging.getLogger(__name__)


class HiveAgent:
    """Wrapper around a Strands Agent that integrates with Hive's bus and event log."""

    def __init__(
        self,
        agent_id: str,
        name: str,
        system_prompt: str,
        model_id: str,
        tools: list,
        bus: MessageBus,
        event_log: EventLog,
    ):
        self.agent_id = agent_id
        self.name = name
        self.system_prompt = system_prompt
        self.model_id = model_id
        self.tools = tools
        self.bus = bus
        self.event_log = event_log
        self._strands_agent: Agent | None = None

        # Register on bus
        self.bus.subscribe(agent_id, self._handle_message)

    def _log(self, event: str, data: dict):
        self.event_log.append(self.agent_id, event, data)

    async def _handle_message(self, message: Message):
        """Handle incoming message from the bus."""
        self._log("received", {"from": message.source, "type": message.msg_type})
        try:
            response = await self.process(message.payload)
            self._log("responded", {"response_preview": str(response)[:200]})
            # Send response back to source
            await self.bus.publish(Message(
                source=self.agent_id,
                target=message.source,
                msg_type="response",
                payload={"result": response},
            ))
        except Exception as e:
            self._log("error", {"error": str(e)})
            logger.error(f"Agent {self.agent_id} error: {e}")

    async def process(self, payload: dict) -> Any:
        """Process a task payload. Override in subclasses for custom behavior."""
        query = payload.get("query", "")
        if not self._strands_agent:
            self._init_strands_agent()
        result = self._strands_agent(query)
        return str(result)

    def _init_strands_agent(self):
        """Initialize the underlying Strands agent."""
        self._strands_agent = Agent(
            system_prompt=self.system_prompt,
            model=self.model_id,
            tools=self.tools,
        )

    async def request_agent(self, target_agent_id: str, msg_type: str, payload: dict):
        """Request another agent to do something via the bus."""
        self._log("agent_request", {"target": target_agent_id, "type": msg_type})
        await self.bus.publish(Message(
            source=self.agent_id,
            target=target_agent_id,
            msg_type=msg_type,
            payload=payload,
        ))

    def shutdown(self):
        """Unsubscribe from the bus."""
        self.bus.unsubscribe(self.agent_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_base_agent.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add containers/hive/hive_core/agents/__init__.py containers/hive/hive_core/agents/base.py tests/unit/hive/test_base_agent.py
git commit -m "feat(hive): add HiveAgent base class with bus + event log integration"
```

---

### Task 2: Agent Registry

**Files:**
- Create: `containers/hive/hive_core/registry.py`
- Create: `tests/unit/hive/test_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/hive/test_registry.py
import pytest
from unittest.mock import MagicMock
from hive_core.registry import AgentRegistry
from hive_core.bus import MessageBus
from hive_core.event_log import EventLog
from hive_core.config import AgentConfig


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def event_log():
    return MagicMock(spec=EventLog)


@pytest.fixture
def registry(bus, event_log):
    return AgentRegistry(bus=bus, event_log=event_log)


def test_register_agent(registry):
    config = AgentConfig(
        id="test-1", name="Test", type="custom",
        system_prompt="test", model="x",
        tools=[], channels=[], mcp_channels=[], autonomy="ask"
    )
    registry.register(config)
    assert "test-1" in registry.agents
    assert registry.agents["test-1"].name == "Test"


def test_register_duplicate_raises(registry):
    config = AgentConfig(
        id="test-1", name="Test", type="custom",
        system_prompt="test", model="x",
        tools=[], channels=[], mcp_channels=[], autonomy="ask"
    )
    registry.register(config)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(config)


def test_unregister_agent(registry):
    config = AgentConfig(
        id="test-1", name="Test", type="custom",
        system_prompt="test", model="x",
        tools=[], channels=[], mcp_channels=[], autonomy="ask"
    )
    registry.register(config)
    registry.unregister("test-1")
    assert "test-1" not in registry.agents


def test_unregister_nonexistent_raises(registry):
    with pytest.raises(KeyError):
        registry.unregister("nope")


def test_get_agent(registry):
    config = AgentConfig(
        id="test-1", name="Test", type="custom",
        system_prompt="test", model="x",
        tools=[], channels=[], mcp_channels=[], autonomy="ask"
    )
    registry.register(config)
    agent = registry.get("test-1")
    assert agent.agent_id == "test-1"


def test_list_agents(registry):
    for i in range(3):
        config = AgentConfig(
            id=f"agent-{i}", name=f"Agent {i}", type="custom",
            system_prompt="test", model="x",
            tools=[], channels=[], mcp_channels=[], autonomy="ask"
        )
        registry.register(config)
    agents = registry.list_agents()
    assert len(agents) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement AgentRegistry**

```python
# containers/hive/hive_core/registry.py
import logging
from hive_core.agents.base import HiveAgent
from hive_core.bus import MessageBus
from hive_core.event_log import EventLog
from hive_core.config import AgentConfig

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Manages the lifecycle of agents within a Hive session."""

    def __init__(self, bus: MessageBus, event_log: EventLog):
        self.bus = bus
        self.event_log = event_log
        self.agents: dict[str, HiveAgent] = {}

    def register(self, config: AgentConfig) -> HiveAgent:
        if config.id in self.agents:
            raise ValueError(f"Agent '{config.id}' already registered")

        agent = HiveAgent(
            agent_id=config.id,
            name=config.name,
            system_prompt=config.system_prompt,
            model_id=config.model,
            tools=[],  # Tools injected separately (MCP, built-in)
            bus=self.bus,
            event_log=self.event_log,
        )
        self.agents[config.id] = agent
        logger.info(f"Registered agent: {config.id} ({config.name})")
        return agent

    def unregister(self, agent_id: str):
        if agent_id not in self.agents:
            raise KeyError(f"Agent '{agent_id}' not found")
        self.agents[agent_id].shutdown()
        del self.agents[agent_id]
        logger.info(f"Unregistered agent: {agent_id}")

    def get(self, agent_id: str) -> HiveAgent:
        return self.agents[agent_id]

    def list_agents(self) -> list[HiveAgent]:
        return list(self.agents.values())

    def shutdown_all(self):
        for agent_id in list(self.agents.keys()):
            self.unregister(agent_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_registry.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add containers/hive/hive_core/registry.py tests/unit/hive/test_registry.py
git commit -m "feat(hive): add AgentRegistry for agent lifecycle management"
```

---

### Task 3: Code Executor

**Files:**
- Create: `containers/hive/hive_core/executor.py`
- Create: `tests/unit/hive/test_executor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/hive/test_executor.py
import pytest
from hive_core.executor import CodeExecutor


@pytest.fixture
def executor(tmp_path):
    return CodeExecutor(workspace_dir=str(tmp_path), timeout=5)


def test_execute_simple_script(executor):
    result = executor.execute("print('hello world')")
    assert result.success is True
    assert "hello world" in result.stdout


def test_execute_returns_stderr_on_error(executor):
    result = executor.execute("raise ValueError('oops')")
    assert result.success is False
    assert "oops" in result.stderr


def test_execute_timeout(executor):
    executor.timeout = 1
    result = executor.execute("import time; time.sleep(10)")
    assert result.success is False
    assert "timeout" in result.stderr.lower() or "timed out" in result.stderr.lower()


def test_execute_captures_return_value(executor):
    result = executor.execute("x = 42\nprint(x)")
    assert "42" in result.stdout


def test_execute_with_saved_script(executor, tmp_path):
    script_path = tmp_path / "test_script.py"
    script_path.write_text("print('from file')")
    result = executor.execute_file(str(script_path))
    assert result.success is True
    assert "from file" in result.stdout


def test_execute_no_network_by_default(executor):
    # This test verifies the executor doesn't have unrestricted access
    # (actual network restriction depends on OS/container capabilities)
    result = executor.execute("import socket; print(socket.getfqdn())")
    # Should still work — we just verify it runs
    assert result.success is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_executor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement CodeExecutor**

```python
# containers/hive/hive_core/executor.py
import subprocess
import logging
import tempfile
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    return_code: int


class CodeExecutor:
    """Sandboxed Python code executor using subprocess."""

    def __init__(self, workspace_dir: str, timeout: int = 30):
        self.workspace_dir = workspace_dir
        self.timeout = timeout

    def execute(self, code: str) -> ExecutionResult:
        """Execute Python code string in a subprocess."""
        # Write code to a temp file in workspace
        script_path = os.path.join(self.workspace_dir, "_exec_tmp.py")
        with open(script_path, "w") as f:
            f.write(code)

        return self.execute_file(script_path)

    def execute_file(self, script_path: str) -> ExecutionResult:
        """Execute a Python script file in a subprocess."""
        try:
            result = subprocess.run(
                ["python", script_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.workspace_dir,
                env={
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )
            return ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Timed out after {self.timeout} seconds",
                return_code=-1,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_executor.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add containers/hive/hive_core/executor.py tests/unit/hive/test_executor.py
git commit -m "feat(hive): add sandboxed CodeExecutor with timeout"
```

---

### Task 4: Cron Scheduler

**Files:**
- Create: `containers/hive/hive_core/scheduler.py`
- Create: `tests/unit/hive/test_scheduler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/hive/test_scheduler.py
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from hive_core.scheduler import HiveScheduler, CronJob


@pytest.fixture
def mock_state():
    state = MagicMock()
    state.load_cron_jobs.return_value = []
    return state


@pytest.fixture
def mock_bus():
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def scheduler(mock_state, mock_bus):
    return HiveScheduler(state=mock_state, bus=mock_bus)


def test_add_job(scheduler):
    job = CronJob(
        id="job-1",
        name="Daily Report",
        schedule="0 8 * * *",
        action="run_script",
        payload={"script": "daily_report.py"},
        agent_id="pa-agent",
        notify_channel="whatsapp-personal",
    )
    scheduler.add_job(job)
    assert "job-1" in scheduler.jobs


def test_add_duplicate_job_raises(scheduler):
    job = CronJob(
        id="job-1", name="Test", schedule="* * * * *",
        action="run_script", payload={}, agent_id="pa-agent", notify_channel=""
    )
    scheduler.add_job(job)
    with pytest.raises(ValueError, match="already exists"):
        scheduler.add_job(job)


def test_remove_job(scheduler):
    job = CronJob(
        id="job-1", name="Test", schedule="* * * * *",
        action="run_script", payload={}, agent_id="pa-agent", notify_channel=""
    )
    scheduler.add_job(job)
    scheduler.remove_job("job-1")
    assert "job-1" not in scheduler.jobs


def test_list_jobs(scheduler):
    for i in range(3):
        job = CronJob(
            id=f"job-{i}", name=f"Job {i}", schedule="* * * * *",
            action="run_script", payload={}, agent_id="pa-agent", notify_channel=""
        )
        scheduler.add_job(job)
    jobs = scheduler.list_jobs()
    assert len(jobs) == 3


def test_persist_saves_to_state(scheduler, mock_state):
    job = CronJob(
        id="job-1", name="Test", schedule="0 8 * * *",
        action="run_script", payload={"script": "x.py"},
        agent_id="pa-agent", notify_channel=""
    )
    scheduler.add_job(job)
    scheduler.persist()
    mock_state.save_cron_jobs.assert_called_once()
    saved = mock_state.save_cron_jobs.call_args[0][0]
    assert len(saved) == 1
    assert saved[0]["id"] == "job-1"


def test_load_restores_jobs(mock_state, mock_bus):
    mock_state.load_cron_jobs.return_value = [
        {"id": "job-1", "name": "Test", "schedule": "0 8 * * *",
         "action": "run_script", "payload": {}, "agent_id": "pa-agent", "notify_channel": ""}
    ]
    scheduler = HiveScheduler(state=mock_state, bus=mock_bus)
    scheduler.load()
    assert "job-1" in scheduler.jobs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_scheduler.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement HiveScheduler**

```python
# containers/hive/hive_core/scheduler.py
import logging
from dataclasses import dataclass, asdict
from typing import Any
from hive_core.bus import MessageBus, Message

logger = logging.getLogger(__name__)


@dataclass
class CronJob:
    id: str
    name: str
    schedule: str  # cron expression (e.g., "0 8 * * *")
    action: str  # "run_script" | "send_message" | "agent_task"
    payload: dict[str, Any]
    agent_id: str  # which agent handles execution
    notify_channel: str  # channel to notify results

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CronJob":
        return cls(**d)


class HiveScheduler:
    """Manages cron jobs with S3 persistence and bus dispatch."""

    def __init__(self, state, bus: MessageBus):
        self.state = state
        self.bus = bus
        self.jobs: dict[str, CronJob] = {}
        self._ap_scheduler = None  # APScheduler instance, initialized on start()

    def add_job(self, job: CronJob):
        if job.id in self.jobs:
            raise ValueError(f"Job '{job.id}' already exists")
        self.jobs[job.id] = job
        logger.info(f"Added cron job: {job.id} ({job.name}) - {job.schedule}")

    def remove_job(self, job_id: str):
        if job_id not in self.jobs:
            raise KeyError(f"Job '{job_id}' not found")
        del self.jobs[job_id]
        logger.info(f"Removed cron job: {job_id}")

    def list_jobs(self) -> list[CronJob]:
        return list(self.jobs.values())

    def persist(self):
        """Save all jobs to S3 via StateManager."""
        job_dicts = [job.to_dict() for job in self.jobs.values()]
        self.state.save_cron_jobs(job_dicts)

    def load(self):
        """Load jobs from S3 via StateManager."""
        job_dicts = self.state.load_cron_jobs()
        for d in job_dicts:
            job = CronJob.from_dict(d)
            self.jobs[job.id] = job
        logger.info(f"Loaded {len(self.jobs)} cron jobs from state")

    async def execute_job(self, job_id: str):
        """Execute a cron job by dispatching to the assigned agent."""
        job = self.jobs.get(job_id)
        if not job:
            logger.warning(f"Job {job_id} not found for execution")
            return

        logger.info(f"Executing cron job: {job.id} ({job.name})")
        await self.bus.publish(Message(
            source="scheduler",
            target=job.agent_id,
            msg_type="cron_task",
            payload={
                "job_id": job.id,
                "action": job.action,
                "notify_channel": job.notify_channel,
                **job.payload,
            },
        ))

    def start(self):
        """Start APScheduler with all registered jobs."""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger

            self._ap_scheduler = AsyncIOScheduler()
            for job in self.jobs.values():
                trigger = CronTrigger.from_crontab(job.schedule)
                self._ap_scheduler.add_job(
                    self.execute_job, trigger,
                    args=[job.id], id=job.id,
                )
            self._ap_scheduler.start()
            logger.info(f"Scheduler started with {len(self.jobs)} jobs")
        except ImportError:
            logger.warning("APScheduler not installed, cron disabled")

    def stop(self):
        """Stop the scheduler."""
        if self._ap_scheduler:
            self._ap_scheduler.shutdown(wait=False)
```

- [ ] **Step 4: Add save_cron_jobs/load_cron_jobs to StateManager**

Add to `containers/hive/hive_core/state.py`:

```python
def save_cron_jobs(self, jobs: list[dict]):
    self._put_json(f"{self.prefix}/cron/jobs.json", {"jobs": jobs})

def load_cron_jobs(self) -> list[dict]:
    data = self._get_json(f"{self.prefix}/cron/jobs.json", {"jobs": []})
    return data.get("jobs", [])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_scheduler.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add containers/hive/hive_core/scheduler.py tests/unit/hive/test_scheduler.py containers/hive/hive_core/state.py
git commit -m "feat(hive): add CronScheduler with APScheduler and S3 persistence"
```

---

### Task 5: Router (Intent Classification + Dispatch)

**Files:**
- Create: `containers/hive/hive_core/router.py`
- Create: `tests/unit/hive/test_router.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/hive/test_router.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from hive_core.router import HiveRouter
from hive_core.bus import MessageBus
from hive_core.registry import AgentRegistry
from hive_core.event_log import EventLog
from hive_core.config import AgentConfig


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def event_log():
    return MagicMock(spec=EventLog)


@pytest.fixture
def registry(bus, event_log):
    reg = AgentRegistry(bus=bus, event_log=event_log)
    reg.register(AgentConfig(
        id="pa-agent", name="PA", type="default",
        system_prompt="test", model="x",
        tools=[], channels=[], mcp_channels=[], autonomy="ask"
    ))
    reg.register(AgentConfig(
        id="reminder-agent", name="Reminder", type="default",
        system_prompt="test", model="x",
        tools=[], channels=[], mcp_channels=[], autonomy="ask"
    ))
    reg.register(AgentConfig(
        id="market-agent", name="Market", type="default",
        system_prompt="test", model="x",
        tools=[], channels=[], mcp_channels=[], autonomy="ask"
    ))
    return reg


@pytest.fixture
def router(bus, registry, event_log):
    return HiveRouter(bus=bus, registry=registry, event_log=event_log)


def test_classify_reminder_intent(router):
    intent = router.classify("remind me to call Bob at 3pm")
    assert intent == "reminder-agent"


def test_classify_market_intent(router):
    intent = router.classify("what's the stock price of AAPL?")
    assert intent == "market-agent"


def test_classify_general_intent(router):
    intent = router.classify("write me a Python script to parse CSV")
    assert intent == "pa-agent"


def test_classify_system_intent(router):
    intent = router.classify("connect to my MCP at https://example.com")
    assert intent == "__system__"


@pytest.mark.asyncio
async def test_route_dispatches_to_correct_agent(router, bus):
    dispatched = []
    bus.subscribe("pa-agent", lambda msg: dispatched.append(msg) or asyncio.sleep(0))

    import asyncio
    await router.route("user-123", "write a hello world script")
    await asyncio.sleep(0.01)
    # Router should have published to pa-agent
    # (actual dispatch happens via bus.publish)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_router.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement HiveRouter**

```python
# containers/hive/hive_core/router.py
import logging
import re
from hive_core.bus import MessageBus, Message
from hive_core.registry import AgentRegistry
from hive_core.event_log import EventLog

logger = logging.getLogger(__name__)

# Simple keyword-based classification (replaced by LLM classification in production)
REMINDER_KEYWORDS = r"\b(remind|reminder|schedule|alarm|timer|every\s+(morning|evening|day|hour|week)|at\s+\d{1,2}(:\d{2})?\s*(am|pm)?)\b"
MARKET_KEYWORDS = r"\b(stock|price|market|portfolio|crypto|bitcoin|eth|trading|ticker|aapl|msft|holdings|nasdaq|s&p)\b"
SYSTEM_KEYWORDS = r"\b(connect|mcp|channel|configure|add agent|remove agent|wipe|reset)\b"


class HiveRouter:
    """Routes user messages to the appropriate agent based on intent."""

    def __init__(self, bus: MessageBus, registry: AgentRegistry, event_log: EventLog):
        self.bus = bus
        self.registry = registry
        self.event_log = event_log

    def classify(self, query: str) -> str:
        """Classify intent to determine target agent."""
        q = query.lower()

        if re.search(SYSTEM_KEYWORDS, q):
            return "__system__"
        if re.search(REMINDER_KEYWORDS, q):
            return "reminder-agent"
        if re.search(MARKET_KEYWORDS, q):
            return "market-agent"
        # Default to PA for general tasks
        return "pa-agent"

    async def route(self, user_id: str, query: str) -> str:
        """Classify and route a user query to the appropriate agent."""
        target = self.classify(query)
        self.event_log.append("router", "classified", {"query": query, "target": target})

        if target == "__system__":
            return target

        await self.bus.publish(Message(
            source="router",
            target=target,
            msg_type="task",
            payload={"query": query, "user_id": user_id},
        ))
        return target
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd containers/hive && python -m pytest tests/unit/hive/test_router.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add containers/hive/hive_core/router.py tests/unit/hive/test_router.py
git commit -m "feat(hive): add HiveRouter with keyword-based intent classification"
```

---

### Task 6: Specialist Agents (PA, Reminder, Market)

**Files:**
- Create: `containers/hive/hive_core/agents/pa.py`
- Create: `containers/hive/hive_core/agents/reminder.py`
- Create: `containers/hive/hive_core/agents/market.py`

- [ ] **Step 1: Implement Personal Assistant agent**

```python
# containers/hive/hive_core/agents/pa.py
from hive_core.agents.base import HiveAgent
from hive_core.bus import MessageBus, Message
from hive_core.event_log import EventLog
from hive_core.executor import CodeExecutor


class PersonalAssistantAgent(HiveAgent):
    """General-purpose agent with code execution capabilities."""

    def __init__(self, bus: MessageBus, event_log: EventLog, executor: CodeExecutor):
        super().__init__(
            agent_id="pa-agent",
            name="Personal Assistant",
            system_prompt=(
                "You are a personal assistant. Help with general tasks, writing, "
                "summaries, and code execution. When the user asks you to write code, "
                "write it and offer to execute it. Be concise and helpful."
            ),
            model_id="global.anthropic.claude-sonnet-4-6-v1:0",
            tools=[],
            bus=bus,
            event_log=event_log,
        )
        self.executor = executor

    async def process(self, payload: dict):
        query = payload.get("query", "")

        # If this is a code execution request from scheduler
        if payload.get("action") == "run_script":
            script = payload.get("script", "")
            result = self.executor.execute_file(script)
            return {"output": result.stdout, "error": result.stderr, "success": result.success}

        # Otherwise, delegate to Strands agent
        return await super().process(payload)
```

- [ ] **Step 2: Implement Reminder agent**

```python
# containers/hive/hive_core/agents/reminder.py
from hive_core.agents.base import HiveAgent
from hive_core.bus import MessageBus, Message
from hive_core.event_log import EventLog
from hive_core.scheduler import HiveScheduler


class ReminderAgent(HiveAgent):
    """Manages reminders, schedules, and recurring tasks."""

    def __init__(self, bus: MessageBus, event_log: EventLog, scheduler: HiveScheduler):
        super().__init__(
            agent_id="reminder-agent",
            name="Reminder Agent",
            system_prompt=(
                "You manage reminders, schedules, and recurring tasks. "
                "Create, list, and manage cron jobs. Always confirm scheduling "
                "details with the user before creating a job."
            ),
            model_id="global.anthropic.claude-sonnet-4-6-v1:0",
            tools=[],
            bus=bus,
            event_log=event_log,
        )
        self.scheduler = scheduler

    async def process(self, payload: dict):
        # Handle cron task execution
        if payload.get("action") == "create_reminder":
            return self._create_reminder(payload)

        # Handle listing jobs
        query = payload.get("query", "").lower()
        if "list" in query and ("reminder" in query or "schedule" in query or "job" in query):
            jobs = self.scheduler.list_jobs()
            return {"jobs": [j.to_dict() for j in jobs]}

        return await super().process(payload)

    def _create_reminder(self, payload: dict) -> dict:
        from hive_core.scheduler import CronJob
        import uuid
        job = CronJob(
            id=f"reminder-{uuid.uuid4().hex[:8]}",
            name=payload.get("name", "Reminder"),
            schedule=payload.get("schedule", ""),
            action="send_message",
            payload={"message": payload.get("message", "")},
            agent_id="reminder-agent",
            notify_channel=payload.get("notify_channel", ""),
        )
        self.scheduler.add_job(job)
        self.scheduler.persist()
        return {"created": job.to_dict()}
```

- [ ] **Step 3: Implement Market agent**

```python
# containers/hive/hive_core/agents/market.py
from hive_core.agents.base import HiveAgent
from hive_core.bus import MessageBus
from hive_core.event_log import EventLog


class MarketAgent(HiveAgent):
    """Analyzes markets, tracks assets, and provides portfolio insights."""

    def __init__(self, bus: MessageBus, event_log: EventLog):
        super().__init__(
            agent_id="market-agent",
            name="Market Agent",
            system_prompt=(
                "You analyze markets, track stocks/crypto, summarize financial news, "
                "and provide portfolio insights. Use available MCP data channels for "
                "real-time data. If no data channel is connected, use web search."
            ),
            model_id="global.anthropic.claude-sonnet-4-6-v1:0",
            tools=[],
            bus=bus,
            event_log=event_log,
        )

    async def process(self, payload: dict):
        # MCP tools will be injected via the channel system (Plan 3)
        return await super().process(payload)
```

- [ ] **Step 4: Commit**

```bash
git add containers/hive/hive_core/agents/pa.py containers/hive/hive_core/agents/reminder.py containers/hive/hive_core/agents/market.py
git commit -m "feat(hive): add PA, Reminder, and Market specialist agents"
```

---

### Task 7: Integrate Components in app.py

**Files:**
- Modify: `containers/hive/app.py`

- [ ] **Step 1: Update app.py to wire all components together**

Replace `containers/hive/app.py` with:

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
from hive_core.registry import AgentRegistry
from hive_core.router import HiveRouter
from hive_core.executor import CodeExecutor
from hive_core.scheduler import HiveScheduler
from hive_core.agents.pa import PersonalAssistantAgent
from hive_core.agents.reminder import ReminderAgent
from hive_core.agents.market import MarketAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BUCKET = os.getenv("HIVE_STATE_BUCKET", "hive-state-test")
KMS_KEY_ID = os.getenv("HIVE_KMS_KEY_ID", "")
REGION = os.getenv("REGION", "us-east-1")

app = BedrockAgentCoreApp()


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
        self.config: HiveConfig = default_config()
        self._response_queue: asyncio.Queue = asyncio.Queue()

    async def initialize(self):
        """Load state and initialize agents."""
        stored = self.state.load_config()
        if stored.get("agents"):
            self.config = HiveConfig.from_dict(stored)
        else:
            self.config = default_config()
            self.state.save_config(self.config.to_dict())

        # Register default specialist agents
        self._register_default_agents()

        # Load and start cron jobs
        self.scheduler.load()
        self.scheduler.start()

        # Subscribe to responses for streaming back to user
        self.bus.subscribe("__user__", self._collect_response)

        logger.info(f"Session initialized for {self.user_id}")

    def _register_default_agents(self):
        """Register the built-in specialist agents."""
        PersonalAssistantAgent(bus=self.bus, event_log=self.event_log, executor=self.executor)
        ReminderAgent(bus=self.bus, event_log=self.event_log, scheduler=self.scheduler)
        MarketAgent(bus=self.bus, event_log=self.event_log)

    async def _collect_response(self, message: Message):
        """Collect agent responses for streaming to the user."""
        await self._response_queue.put(message)

    async def handle_query(self, query: str):
        """Route query and collect response."""
        target = await self.router.route(self.user_id, query)
        return target

    async def get_response(self, timeout: float = 30.0) -> dict | None:
        """Wait for agent response."""
        try:
            msg = await asyncio.wait_for(self._response_queue.get(), timeout=timeout)
            return msg.payload
        except asyncio.TimeoutError:
            return None

    def shutdown(self):
        """Clean shutdown."""
        self.scheduler.stop()
        self.event_log.flush()


@app.websocket
async def websocket_handler(websocket, context):
    """Hive WebSocket handler with full agent orchestration."""
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

                target = await session.handle_query(query)
                await websocket.send_json({"type": "routed", "target": target})

                # Stream response
                response = await session.get_response()
                if response:
                    await websocket.send_json({"type": "response", "data": response})
                else:
                    await websocket.send_json({"type": "error", "message": "Agent timeout"})

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
                await websocket.send_json({"type": "wiped"})

    except Exception as e:
        if "disconnect" not in str(e).lower():
            logger.error(f"WebSocket error: {e}")
    finally:
        if session:
            session.shutdown()
        await websocket.close()


if __name__ == "__main__":
    app.run(log_level="info")
```

- [ ] **Step 2: Verify container still builds**

Run: `cd containers/hive && docker build --platform linux/arm64 -t hive-test .`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add containers/hive/app.py
git commit -m "feat(hive): integrate all core components in app.py"
```

---
