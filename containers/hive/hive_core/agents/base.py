import asyncio
import logging
from typing import Any
from hive_core.bus import MessageBus, Message
from hive_core.event_log import EventLog

logger = logging.getLogger(__name__)

# Lazy import: strands may not be installed in test environments
try:
    from strands import Agent as StrandsAgent
    from strands.models import BedrockModel
except ImportError:
    StrandsAgent = None
    BedrockModel = None


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
        self._strands_agent: Any = None

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
        context = payload.get("context", "")
        if context:
            query = f"{context}\n\nUser: {query}"
        if not self._strands_agent:
            self._init_strands_agent()
        # Strands Agent.__call__ is synchronous — run in thread to avoid blocking event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._strands_agent, query)
        return str(result)

    def _init_strands_agent(self):
        """Initialize the underlying Strands agent."""
        if StrandsAgent is None:
            raise ImportError(
                "strands package is required to use _init_strands_agent. "
                "Install it with: pip install strands-agents"
            )
        import os
        region = os.getenv("REGION", "us-east-1")
        model = BedrockModel(model_id=self.model_id, region_name=region)
        self._strands_agent = StrandsAgent(
            system_prompt=self.system_prompt,
            model=model,
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
