import json
import pytest
from unittest.mock import MagicMock, patch
from hive_core.state import StateManager


@pytest.fixture
def mock_s3():
    with patch("hive_core.state.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        yield mock_client


@pytest.fixture
def state_mgr(mock_s3):
    return StateManager(bucket="hive-state-test", user_id="user-123", kms_key_id="key-abc")


def test_load_config_returns_default_when_not_found(state_mgr, mock_s3):
    from botocore.exceptions import ClientError
    mock_s3.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey"}}, "GetObject"
    )
    config = state_mgr.load_config()
    assert config["agents"] == []
    assert config["channels"] == []


def test_load_config_returns_stored_config(state_mgr, mock_s3):
    stored = {"agents": [{"id": "pa-agent"}], "channels": []}
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: json.dumps(stored).encode())
    }
    config = state_mgr.load_config()
    assert config["agents"][0]["id"] == "pa-agent"


def test_save_config_writes_to_s3(state_mgr, mock_s3):
    config = {"agents": [], "channels": [{"id": "slack-1"}]}
    state_mgr.save_config(config)
    mock_s3.put_object.assert_called_once()
    call_kwargs = mock_s3.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "hive-state-test"
    assert call_kwargs["Key"] == "users/user-123/config.json"
    assert "slack-1" in call_kwargs["Body"]


def test_save_secrets_encrypts_with_kms(state_mgr, mock_s3):
    secrets = {"slack_token": "xoxb-123"}
    state_mgr.save_secrets(secrets)
    call_kwargs = mock_s3.put_object.call_args[1]
    assert call_kwargs["Key"] == "users/user-123/secrets.enc"
    assert call_kwargs["ServerSideEncryption"] == "aws:kms"
    assert call_kwargs["SSEKMSKeyId"] == "key-abc"


def test_load_secrets_returns_empty_when_not_found(state_mgr, mock_s3):
    from botocore.exceptions import ClientError
    mock_s3.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey"}}, "GetObject"
    )
    secrets = state_mgr.load_secrets()
    assert secrets == {}


def test_wipe_deletes_user_prefix(state_mgr, mock_s3):
    mock_s3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "users/user-123/config.json"},
            {"Key": "users/user-123/secrets.enc"},
        ]
    }
    state_mgr.wipe()
    mock_s3.delete_objects.assert_called_once()


def test_save_script(state_mgr, mock_s3):
    state_mgr.save_script("daily_report.py", "print('hello')")
    call_kwargs = mock_s3.put_object.call_args[1]
    assert call_kwargs["Key"] == "users/user-123/scripts/daily_report.py"
    assert call_kwargs["Body"] == "print('hello')"


def test_load_script(state_mgr, mock_s3):
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"print('world')")
    }
    content = state_mgr.load_script("daily_report.py")
    assert content == "print('world')"
