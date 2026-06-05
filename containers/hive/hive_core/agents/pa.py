# containers/hive/hive_core/agents/pa.py
from hive_core.agents.base import HiveAgent
from hive_core.bus import MessageBus
from hive_core.event_log import EventLog
from hive_core.executor import CodeExecutor
from hive_core.tools.channel_send import send_channel_message, read_channel_messages, list_channel_contacts
from hive_core.tools.hive_ops import (
    list_hive_agents, list_hive_channels, get_hive_status,
    add_mcp_channel, remove_channel, run_code, spawn_dynamic_agent,
)


class PersonalAssistantAgent(HiveAgent):
    """General-purpose agent with code execution capabilities."""

    def __init__(self, bus: MessageBus, event_log: EventLog, executor: CodeExecutor):
        super().__init__(
            agent_id="pa-agent",
            name="Personal Assistant",
            system_prompt=(
                "You are a personal assistant running on Hive — a multi-agent platform. "
                "Help with general tasks, writing, summaries, and code execution. "
                "When the user asks you to write code, write it and offer to execute it. Be concise and helpful.\n\n"
                "SELF-AWARENESS: You know about the hive you're running on. Use these tools to introspect:\n"
                "- list_hive_agents: See all agents in this hive\n"
                "- list_hive_channels: See all connected channels\n"
                "- get_hive_status: Overall hive status summary\n\n"
                "SELF-MANAGEMENT (owner only — guardrailed):\n"
                "- add_mcp_channel: Connect a new MCP server as a data channel\n"
                "- remove_channel: Disconnect a channel\n"
                "- run_code: Execute Python code in a sandbox\n"
                "- spawn_dynamic_agent: Create a temporary agent for a subtask\n\n"
                "CHANNEL TOOLS:\n"
                "- send_channel_message: Send a message through a channel\n"
                "- read_channel_messages: Read recent messages from a contact on a channel\n"
                "- list_channel_contacts: List contacts with recent message activity\n"
                "For WhatsApp, the 'to'/'contact' field must be the phone number with @s.whatsapp.net suffix "
                "(e.g. '61412345678@s.whatsapp.net'). Use list_channel_contacts first if you need to find contacts. "
                "Ask the user for the recipient/contact if not specified."
            ),
            model_id="global.anthropic.claude-sonnet-4-6",
            tools=[
                send_channel_message, read_channel_messages, list_channel_contacts,
                list_hive_agents, list_hive_channels, get_hive_status,
                add_mcp_channel, remove_channel, run_code, spawn_dynamic_agent,
            ],
            bus=bus,
            event_log=event_log,
        )
        self.executor = executor

    async def process(self, payload: dict):
        query = payload.get("query", "")
        if payload.get("action") == "run_script":
            script = payload.get("script", "")
            result = self.executor.execute_file(script)
            return {"output": result.stdout, "error": result.stderr, "success": result.success}
        return await super().process(payload)
