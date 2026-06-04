import asyncio
import logging
import time
from typing import Any
from hive_core.bus import MessageBus, Message
from hive_core.event_log import EventLog
from hive_core.guardrails import (
    ExecutionContext,
    build_guardrails_prompt,
    clear_execution_context,
    resolve_tier,
    set_execution_context,
)

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
        self._persona: dict = {}
        self._guardrails: dict = {}
        self._active_channel_id: str = ""

        # Lifecycle state
        self.status: str = "running"  # running | stopped
        self.started_at: float = time.time()
        self.last_activity: float = 0.0
        self.message_count: int = 0

        # Register on bus
        self.bus.subscribe(agent_id, self._handle_message)

    def get_info(self) -> dict:
        """Return agent status info for the UI."""
        return {
            "id": self.agent_id,
            "name": self.name,
            "status": self.status,
            "model": self.model_id,
            "started_at": self.started_at,
            "last_activity": self.last_activity,
            "message_count": self.message_count,
            "has_strands": self._strands_agent is not None,
        }

    def stop(self):
        """Stop the agent — unsubscribe from bus, release Strands memory."""
        if self.status == "stopped":
            return
        self.bus.unsubscribe(self.agent_id)
        self._strands_agent = None
        self.status = "stopped"
        self._log("stopped", {})
        logger.info(f"Agent {self.agent_id} stopped")

    def start(self):
        """Start the agent — re-subscribe to bus."""
        if self.status == "running":
            return
        self.bus.subscribe(self.agent_id, self._handle_message)
        self.status = "running"
        self.started_at = time.time()
        self._log("started", {})
        logger.info(f"Agent {self.agent_id} started")

    def restart(self):
        """Restart the agent — stop and start, clearing Strands state."""
        self.stop()
        self.start()

    def set_persona(self, persona: dict):
        """Set the user's persona config. Forces agent re-init on next process call."""
        self._persona = persona
        self._strands_agent = None

    def set_guardrails(self, guardrails: dict):
        """Set the user's guardrails config. Forces agent re-init on next process call."""
        self._guardrails = guardrails
        self._strands_agent = None

    def _build_effective_persona(self, channel_id: str = "", contact_jid: str = "") -> str:
        """Build the effective persona string from base + channel + contact overrides."""
        if not self._persona or not self._persona.get("persona"):
            return ""
        parts = [self._persona["persona"]]
        if channel_id and channel_id in self._persona.get("channel_overrides", {}):
            parts.append(self._persona["channel_overrides"][channel_id])
        if channel_id and contact_jid:
            key = f"{channel_id}::{contact_jid}"
            if key in self._persona.get("contact_overrides", {}):
                parts.append(self._persona["contact_overrides"][key])
        return "\n\n".join(parts)

    def _log(self, event: str, data: dict):
        self.event_log.append(self.agent_id, event, data)

    async def _handle_message(self, message: Message):
        """Handle incoming message from the bus."""
        self.last_activity = time.time()
        self.message_count += 1
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
            # Always publish a response so callers don't hang on the queue
            await self.bus.publish(Message(
                source=self.agent_id,
                target=message.source,
                msg_type="response",
                payload={"result": "", "error": str(e)},
            ))

    async def process(self, payload: dict) -> Any:
        """Process a task payload. Override in subclasses for custom behavior."""
        query = payload.get("query", "")
        context = payload.get("context", "")
        channel_id = payload.get("channel_id", "")
        contact_jid = payload.get("contact_jid", "")

        if context:
            query = f"{context}\n\nUser: {query}"

        # Re-init agent if channel context changed (different system prompt needed)
        if channel_id != self._active_channel_id or not self._strands_agent:
            self._init_strands_agent(channel_id, contact_jid)
            self._active_channel_id = channel_id

        # Contact-level override injected as query prefix (avoids re-init per contact)
        if channel_id and contact_jid:
            key = f"{channel_id}::{contact_jid}"
            contact_override = self._persona.get("contact_overrides", {}).get(key, "")
            if contact_override:
                query = f"[Context for this contact: {contact_override}]\n\n{query}"

        # Set guardrails execution context
        tier = resolve_tier(contact_jid, self._guardrails)
        policies = self._guardrails.get("policies", {}).get(tier, {})
        refusal = self._guardrails.get("refusal_message", "")
        exec_ctx = ExecutionContext(
            sender_jid=contact_jid,
            sender_tier=tier,
            channel_id=channel_id,
            policies=policies,
            refusal_message=refusal,
        )
        set_execution_context(exec_ctx)

        try:
            # Strands Agent.__call__ is synchronous — run in thread to avoid blocking event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._strands_agent, query)
            return str(result)
        finally:
            clear_execution_context()

    def _init_strands_agent(self, channel_id: str = "", contact_jid: str = ""):
        """Initialize the underlying Strands agent."""
        if StrandsAgent is None:
            raise ImportError(
                "strands package is required to use _init_strands_agent. "
                "Install it with: pip install strands-agents"
            )
        import os
        region = os.getenv("REGION", "us-east-1")
        model = BedrockModel(model_id=self.model_id, region_name=region)

        # Build effective system prompt with persona
        base_persona = self._persona.get("persona", "") if self._persona else ""
        channel_override = ""
        if channel_id and self._persona:
            channel_override = self._persona.get("channel_overrides", {}).get(channel_id, "")
        persona_block = "\n\n".join(filter(None, [base_persona, channel_override]))
        effective_prompt = self.system_prompt
        if persona_block:
            effective_prompt = f"<persona>\n{persona_block}\n</persona>\n\n{self.system_prompt}"

        # Inject guardrails prompt between persona and role prompt
        if self._guardrails and self._guardrails.get("enabled", False):
            tier = resolve_tier(contact_jid, self._guardrails)
            policies = self._guardrails.get("policies", {}).get(tier, {})
            refusal = self._guardrails.get("refusal_message", "")
            guardrails_block = build_guardrails_prompt(tier, contact_jid, policies, refusal)
            # Insert guardrails after persona block (before role instructions)
            if persona_block:
                effective_prompt = (
                    f"<persona>\n{persona_block}\n</persona>\n\n"
                    f"{guardrails_block}\n\n"
                    f"{self.system_prompt}"
                )
            else:
                effective_prompt = f"{guardrails_block}\n\n{self.system_prompt}"

        # Merge static tools with any MCP tools mapped to this agent
        all_tools = list(self.tools)
        try:
            from hive_core.tools.mcp_bridge import create_mcp_tools_for_agent
            mcp_tools = create_mcp_tools_for_agent(self.agent_id)
            if mcp_tools:
                all_tools.extend(mcp_tools)
                logger.info(f"Agent {self.agent_id}: {len(mcp_tools)} MCP tools loaded")
        except Exception as e:
            logger.warning(f"Failed to load MCP tools for {self.agent_id}: {e}")

        self._strands_agent = StrandsAgent(
            system_prompt=effective_prompt,
            model=model,
            tools=all_tools,
        )

    def reload_tools(self):
        """Force re-initialization of Strands agent (e.g., after MCP channels change)."""
        self._strands_agent = None

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
        """Unsubscribe from the bus and release resources."""
        self.stop()
