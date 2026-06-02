# containers/hive/hive_core/agents/pa.py
from hive_core.agents.base import HiveAgent
from hive_core.bus import MessageBus
from hive_core.event_log import EventLog
from hive_core.executor import CodeExecutor


class PersonalAssistantAgent(HiveAgent):
    """General-purpose agent with code execution capabilities."""

    def __init__(self, bus: MessageBus, event_log: EventLog, executor: CodeExecutor):
        super().__init__(
            agent_id="pa-agent",
            name="Personal Assistant",
            system_prompt=(
                "You are a personal assistant. Help with general tasks, writing, "
                "summaries, and code execution. When the user asks you to write code, "
                "write it and offer to execute it. Be concise and helpful."
            ),
            model_id="global.anthropic.claude-sonnet-4-6",
            tools=[],
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
