# containers/hive/hive_core/agents/reminder.py
import uuid
from strands import tool
from hive_core.agents.base import HiveAgent
from hive_core.bus import MessageBus
from hive_core.event_log import EventLog
from hive_core.scheduler import HiveScheduler, CronJob
from hive_core.tools.channel_send import send_channel_message

# Module-level reference to the scheduler (set by ReminderAgent.__init__)
_scheduler_ref: HiveScheduler | None = None


@tool
def schedule_message(channel_id: str, to: str, message: str, delay_minutes: int = 1) -> dict:
    """Schedule a one-time message to be sent after a delay.

    Args:
        channel_id: The channel to send through (e.g. "test" for WhatsApp)
        to: The recipient. For WhatsApp: phone number (e.g. "61430962621") or with suffix "61430962621@s.whatsapp.net"
        message: The message text to send
        delay_minutes: Minutes from now to send the message (default 1)

    Returns:
        dict with job details
    """
    global _scheduler_ref
    if not _scheduler_ref:
        return {"success": False, "error": "Scheduler not initialized"}

    # Normalize WhatsApp JID
    recipient = to if "@" in to else f"{to}@s.whatsapp.net"

    job = CronJob(
        id=f"once-{uuid.uuid4().hex[:8]}",
        name=f"Send to {to}",
        schedule="",  # Empty = one-time
        action="send_message",
        payload={"message": message, "to": recipient},
        agent_id="reminder-agent",
        notify_channel=channel_id,
    )
    _scheduler_ref.schedule_once(job, delay_seconds=delay_minutes * 60)
    return {"success": True, "job_id": job.id, "send_in": f"{delay_minutes} minutes", "to": recipient, "channel": channel_id}


class ReminderAgent(HiveAgent):
    """Manages reminders, schedules, and recurring tasks."""

    def __init__(self, bus: MessageBus, event_log: EventLog, scheduler: HiveScheduler):
        global _scheduler_ref
        _scheduler_ref = scheduler
        super().__init__(
            agent_id="reminder-agent",
            name="Reminder Agent",
            system_prompt=(
                "You manage reminders, schedules, and recurring tasks.\n"
                "Tools available:\n"
                "- schedule_message: Schedule a one-time message to be sent after a delay\n"
                "- send_channel_message: Send a message immediately\n"
                "When a user asks to schedule a message, use schedule_message with the channel_id, "
                "recipient, message text, and delay in minutes. "
                "The channel_id is the name of the configured channel (e.g. 'test' for WhatsApp)."
            ),
            model_id="global.anthropic.claude-sonnet-4-6",
            tools=[send_channel_message, schedule_message],
            bus=bus,
            event_log=event_log,
        )
        self.scheduler = scheduler

    async def process(self, payload: dict):
        if payload.get("action") == "create_reminder":
            return self._create_reminder(payload)

        # Handle cron job execution: directly send the message
        if payload.get("action") == "send_message":
            return await self._execute_send(payload)

        query = payload.get("query", "").lower()
        if "list" in query and ("reminder" in query or "schedule" in query or "job" in query):
            jobs = self.scheduler.list_jobs()
            return {"jobs": [j.to_dict() for j in jobs]}
        return await super().process(payload)

    async def _execute_send(self, payload: dict) -> dict:
        """Execute a scheduled send_message action directly (async-safe).

        Uses the channel manager directly instead of the sync Strands tool
        to avoid deadlocking the event loop when called from the scheduler.
        """
        from hive_core.tools.channel_send import _channel_manager

        channel_id = payload.get("notify_channel", "")
        to = payload.get("to", payload.get("recipient", ""))
        message = payload.get("message", "")

        if not channel_id or not to or not message:
            return {"success": False, "error": f"Missing fields: channel={channel_id}, to={to}, message={message}"}

        # Normalize WhatsApp JID
        if "@" not in to:
            to = f"{to}@s.whatsapp.net"

        if not _channel_manager:
            return {"success": False, "error": "No channel manager available"}

        ch = _channel_manager.communication_channels.get(channel_id)
        if not ch:
            available = list(_channel_manager.communication_channels.keys())
            return {"success": False, "error": f"Channel '{channel_id}' not found. Available: {available}"}

        try:
            await ch.send(to, message)
            result = {"success": True, "channel_id": channel_id, "to": to}
            self._log("job_delivered", {"channel": channel_id, "to": to, "result": result})
            return result
        except Exception as e:
            result = {"success": False, "error": str(e)}
            self._log("job_delivery_failed", {"channel": channel_id, "to": to, "error": str(e)})
            return result

    def _create_reminder(self, payload: dict) -> dict:
        job = CronJob(
            id=f"reminder-{uuid.uuid4().hex[:8]}",
            name=payload.get("name", "Reminder"),
            schedule=payload.get("schedule", ""),
            action="send_message",
            payload={
                "message": payload.get("message", ""),
                "to": payload.get("to", payload.get("recipient", "")),
            },
            agent_id="reminder-agent",
            notify_channel=payload.get("notify_channel", ""),
        )
        self.scheduler.add_job(job)
        self.scheduler.persist()
        return {"created": job.to_dict()}
