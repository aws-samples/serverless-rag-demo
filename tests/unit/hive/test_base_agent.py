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
