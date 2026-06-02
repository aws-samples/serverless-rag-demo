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
            task = asyncio.create_task(handler(message))
            task.add_done_callback(self._task_done)
        else:
            logger.warning(f"No subscriber for target '{message.target}'")

    def _task_done(self, task: asyncio.Task):
        """Log any exceptions from message handler tasks."""
        if task.exception():
            logger.error(f"Message handler failed: {task.exception()}", exc_info=task.exception())

    async def broadcast(self, message: Message):
        """Send message to all subscribers."""
        self.history.append(message)
        for agent_id, handler in self._subscribers.items():
            asyncio.create_task(handler(message))
