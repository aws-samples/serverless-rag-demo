import pytest
from unittest.mock import MagicMock, AsyncMock
from hive_core.scheduler import HiveScheduler, CronJob


@pytest.fixture
def mock_state():
    state = MagicMock()
    state.load_cron_jobs.return_value = []
    return state


@pytest.fixture
def mock_bus():
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def scheduler(mock_state, mock_bus):
    return HiveScheduler(state=mock_state, bus=mock_bus)


def test_add_job(scheduler):
    job = CronJob(
        id="job-1",
        name="Daily Report",
        schedule="0 8 * * *",
        action="run_script",
        payload={"script": "daily_report.py"},
        agent_id="pa-agent",
        notify_channel="whatsapp-personal",
    )
    scheduler.add_job(job)
    assert "job-1" in scheduler.jobs


def test_add_duplicate_job_raises(scheduler):
    job = CronJob(
        id="job-1", name="Test", schedule="* * * * *",
        action="run_script", payload={}, agent_id="pa-agent", notify_channel=""
    )
    scheduler.add_job(job)
    with pytest.raises(ValueError, match="already exists"):
        scheduler.add_job(job)


def test_remove_job(scheduler):
    job = CronJob(
        id="job-1", name="Test", schedule="* * * * *",
        action="run_script", payload={}, agent_id="pa-agent", notify_channel=""
    )
    scheduler.add_job(job)
    scheduler.remove_job("job-1")
    assert "job-1" not in scheduler.jobs


def test_list_jobs(scheduler):
    for i in range(3):
        job = CronJob(
            id=f"job-{i}", name=f"Job {i}", schedule="* * * * *",
            action="run_script", payload={}, agent_id="pa-agent", notify_channel=""
        )
        scheduler.add_job(job)
    jobs = scheduler.list_jobs()
    assert len(jobs) == 3


def test_persist_saves_to_state(scheduler, mock_state):
    job = CronJob(
        id="job-1", name="Test", schedule="0 8 * * *",
        action="run_script", payload={"script": "x.py"},
        agent_id="pa-agent", notify_channel=""
    )
    scheduler.add_job(job)
    scheduler.persist()
    mock_state.save_cron_jobs.assert_called_once()
    saved = mock_state.save_cron_jobs.call_args[0][0]
    assert len(saved) == 1
    assert saved[0]["id"] == "job-1"


def test_load_restores_jobs(mock_state, mock_bus):
    mock_state.load_cron_jobs.return_value = [
        {"id": "job-1", "name": "Test", "schedule": "0 8 * * *",
         "action": "run_script", "payload": {}, "agent_id": "pa-agent", "notify_channel": ""}
    ]
    scheduler = HiveScheduler(state=mock_state, bus=mock_bus)
    scheduler.load()
    assert "job-1" in scheduler.jobs
