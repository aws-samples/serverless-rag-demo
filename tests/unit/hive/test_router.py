import pytest
from unittest.mock import MagicMock, AsyncMock
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
async def test_route_dispatches_to_bus(router, bus):
    import asyncio
    target = await router.route("user-123", "what is AAPL stock price?")
    assert target == "market-agent"
