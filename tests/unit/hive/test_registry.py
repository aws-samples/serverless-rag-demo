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
