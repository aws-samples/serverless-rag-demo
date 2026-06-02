import logging
import re
from hive_core.bus import MessageBus, Message
from hive_core.registry import AgentRegistry
from hive_core.event_log import EventLog

logger = logging.getLogger(__name__)

REMINDER_KEYWORDS = r"\b(remind|reminder|schedule|alarm|timer|every\s+(morning|evening|day|hour|week)|at\s+\d{1,2}(:\d{2})?\s*(am|pm)?)\b"
MARKET_KEYWORDS = r"\b(stock|price|market|portfolio|crypto|bitcoin|eth|trading|ticker|aapl|msft|holdings|nasdaq|s&p)\b"
SYSTEM_KEYWORDS = r"\b(connect|mcp|channel|configure|add agent|remove agent|wipe|reset)\b"


class HiveRouter:
    """Routes user messages to the appropriate agent based on intent."""

    def __init__(self, bus: MessageBus, registry: AgentRegistry, event_log: EventLog):
        self.bus = bus
        self.registry = registry
        self.event_log = event_log
        self._context_fn = None

    def set_context_provider(self, fn):
        """Set a function that returns runtime context string for agents."""
        self._context_fn = fn

    def classify(self, query: str) -> str:
        q = query.lower()
        if re.search(SYSTEM_KEYWORDS, q):
            return "__system__"
        if re.search(REMINDER_KEYWORDS, q):
            return "reminder-agent"
        if re.search(MARKET_KEYWORDS, q):
            return "market-agent"
        return "pa-agent"

    async def route(self, user_id: str, query: str) -> str:
        target = self.classify(query)
        self.event_log.append("router", "classified", {"query": query, "target": target})
        if target == "__system__":
            return target
        context = self._context_fn() if self._context_fn else ""
        await self.bus.publish(Message(
            source="__user__",
            target=target,
            msg_type="task",
            payload={"query": query, "user_id": user_id, "context": context},
        ))
        return target
