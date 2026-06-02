# containers/hive/hive_core/agents/pa.py
from hive_core.agents.base import HiveAgent
from hive_core.bus import MessageBus
from hive_core.event_log import EventLog
from hive_core.executor import CodeExecutor
from hive_core.tools.channel_send import send_channel_message, read_channel_messages, list_channel_contacts


class PersonalAssistantAgent(HiveAgent):
    """General-purpose agent with code execution capabilities."""

    def __init__(self, bus: MessageBus, event_log: EventLog, executor: CodeExecutor):
        super().__init__(
            agent_id="pa-agent",
            name="Personal Assistant",
            system_prompt=(
                "You are a personal assistant. Help with general tasks, writing, "
                "summaries, and code execution. When the user asks you to write code, "
                "write it and offer to execute it. Be concise and helpful. "
                "You can send messages through connected channels using the send_channel_message tool. "
                "For WhatsApp, the 'to' field must be the phone number with @s.whatsapp.net suffix "
                "(e.g. '61412345678@s.whatsapp.net'). Ask the user for the recipient if not specified."
            ),
            model_id="global.anthropic.claude-sonnet-4-6",
            tools=[send_channel_message, read_channel_messages, list_channel_contacts],
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
