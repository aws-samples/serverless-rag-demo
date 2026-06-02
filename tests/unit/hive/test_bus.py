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
    async def noop(msg):
        pass

    bus.subscribe("agent-y", noop)
    msg = Message(source="core", target="agent-y", msg_type="task", payload={"q": "test"})
    await bus.publish(msg)
    await asyncio.sleep(0.01)
    assert len(bus.history) == 1
    assert bus.history[0].source == "core"
