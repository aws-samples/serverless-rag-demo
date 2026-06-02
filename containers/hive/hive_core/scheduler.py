import logging
from dataclasses import dataclass, asdict
from typing import Any
from hive_core.bus import MessageBus, Message

logger = logging.getLogger(__name__)


@dataclass
class CronJob:
    id: str
    name: str
    schedule: str
    action: str
    payload: dict[str, Any]
    agent_id: str
    notify_channel: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CronJob":
        return cls(**d)


class HiveScheduler:
    """Manages cron jobs with S3 persistence and bus dispatch."""

    def __init__(self, state, bus: MessageBus):
        self.state = state
        self.bus = bus
        self.jobs: dict[str, CronJob] = {}
        self._ap_scheduler = None

    def add_job(self, job: CronJob):
        if job.id in self.jobs:
            raise ValueError(f"Job '{job.id}' already exists")
        self.jobs[job.id] = job
        logger.info(f"Added cron job: {job.id} ({job.name}) - {job.schedule}")

    def remove_job(self, job_id: str):
        if job_id not in self.jobs:
            raise KeyError(f"Job '{job_id}' not found")
        del self.jobs[job_id]
        logger.info(f"Removed cron job: {job_id}")

    def list_jobs(self) -> list[CronJob]:
        return list(self.jobs.values())

    def persist(self):
        job_dicts = [job.to_dict() for job in self.jobs.values()]
        self.state.save_cron_jobs(job_dicts)

    def load(self):
        job_dicts = self.state.load_cron_jobs()
        for d in job_dicts:
            job = CronJob.from_dict(d)
            self.jobs[job.id] = job
        logger.info(f"Loaded {len(self.jobs)} cron jobs from state")

    async def execute_job(self, job_id: str):
        job = self.jobs.get(job_id)
        if not job:
            return
        await self.bus.publish(Message(
            source="scheduler",
            target=job.agent_id,
            msg_type="cron_task",
            payload={
                "job_id": job.id,
                "action": job.action,
                "notify_channel": job.notify_channel,
                **job.payload,
            },
        ))

    def start(self):
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger
            self._ap_scheduler = AsyncIOScheduler()
            for job in self.jobs.values():
                trigger = CronTrigger.from_crontab(job.schedule)
                self._ap_scheduler.add_job(self.execute_job, trigger, args=[job.id], id=job.id)
            self._ap_scheduler.start()
        except ImportError:
            logger.warning("APScheduler not installed, cron disabled")

    def stop(self):
        if self._ap_scheduler:
            self._ap_scheduler.shutdown(wait=False)
