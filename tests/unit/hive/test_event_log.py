import json
import pytest
from unittest.mock import MagicMock, patch
from hive_core.event_log import EventLog


@pytest.fixture
def mock_s3():
    with patch("hive_core.event_log.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        yield mock_client


@pytest.fixture
def event_log(mock_s3):
    return EventLog(bucket="hive-state-test", user_id="user-123")


def test_append_event(event_log):
    event_log.append("pa-agent", "task_started", {"query": "hello"})
    assert len(event_log.buffer) == 1
    assert event_log.buffer[0]["agent"] == "pa-agent"
    assert event_log.buffer[0]["event"] == "task_started"


def test_flush_writes_to_s3(event_log, mock_s3):
    event_log.append("pa-agent", "task_started", {"query": "hello"})
    event_log.append("market-agent", "mcp_call", {"tool": "get_price"})
    event_log.flush()
    mock_s3.put_object.assert_called_once()
    call_kwargs = mock_s3.put_object.call_args[1]
    assert "event-log/" in call_kwargs["Key"]
    body = call_kwargs["Body"]
    lines = body.strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["agent"] == "pa-agent"


def test_flush_clears_buffer(event_log, mock_s3):
    event_log.append("pa-agent", "done", {})
    event_log.flush()
    assert len(event_log.buffer) == 0


def test_get_recent_returns_buffer(event_log):
    event_log.append("a", "e1", {})
    event_log.append("b", "e2", {})
    event_log.append("c", "e3", {})
    recent = event_log.get_recent(2)
    assert len(recent) == 2
    assert recent[0]["agent"] == "b"
    assert recent[1]["agent"] == "c"
