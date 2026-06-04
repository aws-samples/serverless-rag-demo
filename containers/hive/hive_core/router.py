import json
import logging
import os
from hive_core.bus import MessageBus, Message
from hive_core.registry import AgentRegistry
from hive_core.event_log import EventLog

logger = logging.getLogger(__name__)

ROUTER_PROMPT_TEMPLATE = """You are a message router. Given a user message, decide which agent should handle it.

Available agents:
- pa-agent: General assistant. Handles conversations, writing, code, sending messages NOW, reading messages, listing contacts, and anything that doesn't fit other agents.
- reminder-agent: Handles scheduling, reminders, timers, delayed/future messages (e.g. "in 5 minutes", "tomorrow at 9am", "every Monday").
- market-agent: Handles stock prices, market data, portfolio, crypto, trading queries.
{custom_agents}- __system__: Internal system commands (connect, configure channels, add/remove agents, wipe, reset).

Rules:
- If the user wants to send a message AT A FUTURE TIME or on a schedule, route to reminder-agent.
- If the user wants to send a message RIGHT NOW, route to pa-agent.
- Respond with ONLY the agent ID, nothing else.

User message: {query}"""


class HiveRouter:
    """Routes user messages to the appropriate agent using an LLM."""

    def __init__(self, bus: MessageBus, registry: AgentRegistry, event_log: EventLog):
        self.bus = bus
        self.registry = registry
        self.event_log = event_log
        self._context_fn = None
        self._bedrock = None
        self._custom_agents: list[dict] = []  # [{id, description}]

    def set_context_provider(self, fn):
        """Set a function that returns runtime context string for agents."""
        self._context_fn = fn

    def set_custom_agents(self, agents: list[dict]):
        """Update the list of custom agents for routing."""
        self._custom_agents = agents

    def _get_bedrock(self):
        if not self._bedrock:
            import boto3
            region = os.getenv("REGION", "us-east-1")
            self._bedrock = boto3.client("bedrock-runtime", region_name=region)
        return self._bedrock

    def classify(self, query: str) -> str:
        """Use LLM to classify the query to the right agent."""
        try:
            # Build custom agents section for prompt
            custom_lines = ""
            for ca in self._custom_agents:
                custom_lines += f"- {ca['id']}: {ca['description']}\n"

            prompt = ROUTER_PROMPT_TEMPLATE.format(
                query=query,
                custom_agents=custom_lines,
            )

            client = self._get_bedrock()
            response = client.converse(
                modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 20, "temperature": 0},
            )
            result = response["output"]["message"]["content"][0]["text"].strip().lower()
            # Validate it's a known agent
            valid = {"pa-agent", "reminder-agent", "market-agent", "__system__"}
            valid.update(ca["id"] for ca in self._custom_agents)
            if result in valid:
                return result
            # Try to extract from response if model was verbose
            for agent_id in valid:
                if agent_id in result:
                    return agent_id
            logger.warning(f"Router LLM returned unknown agent: {result}, defaulting to pa-agent")
            return "pa-agent"
        except Exception as e:
            logger.error(f"Router LLM failed: {e}, defaulting to pa-agent")
            return "pa-agent"

    async def route(self, user_id: str, query: str, channel_id: str = "", contact_jid: str = "") -> str:
        target = self.classify(query)
        self.event_log.append("router", "classified", {"query": query, "target": target})
        if target == "__system__":
            return target
        context = self._context_fn() if self._context_fn else ""
        await self.bus.publish(Message(
            source="__user__",
            target=target,
            msg_type="task",
            payload={
                "query": query,
                "user_id": user_id,
                "context": context,
                "channel_id": channel_id,
                "contact_jid": contact_jid,
            },
        ))
        return target
