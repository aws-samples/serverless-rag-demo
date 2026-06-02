# containers/hive/hive_core/agents/reminder.py
import uuid
from hive_core.agents.base import HiveAgent
from hive_core.bus import MessageBus
from hive_core.event_log import EventLog
from hive_core.scheduler import HiveScheduler, CronJob


class ReminderAgent(HiveAgent):
    """Manages reminders, schedules, and recurring tasks."""

    def __init__(self, bus: MessageBus, event_log: EventLog, scheduler: HiveScheduler):
        super().__init__(
            agent_id="reminder-agent",
            name="Reminder Agent",
            system_prompt=(
                "You manage reminders, schedules, and recurring tasks. "
                "Create, list, and manage cron jobs. Always confirm scheduling "
                "details with the user before creating a job."
            ),
            model_id="global.anthropic.claude-sonnet-4-6",
            tools=[],
            bus=bus,
            event_log=event_log,
        )
        self.scheduler = scheduler

    async def process(self, payload: dict):
        if payload.get("action") == "create_reminder":
            return self._create_reminder(payload)
        query = payload.get("query", "").lower()
        if "list" in query and ("reminder" in query or "schedule" in query or "job" in query):
            jobs = self.scheduler.list_jobs()
            return {"jobs": [j.to_dict() for j in jobs]}
        return await super().process(payload)

    def _create_reminder(self, payload: dict) -> dict:
        job = CronJob(
            id=f"reminder-{uuid.uuid4().hex[:8]}",
            name=payload.get("name", "Reminder"),
            schedule=payload.get("schedule", ""),
            action="send_message",
            payload={"message": payload.get("message", "")},
            agent_id="reminder-agent",
            notify_channel=payload.get("notify_channel", ""),
        )
        self.scheduler.add_job(job)
        self.scheduler.persist()
        return {"created": job.to_dict()}
