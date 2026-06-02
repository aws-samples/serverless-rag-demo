import pytest
from hive_core.config import (
    HiveConfig, AgentConfig, ChannelConfig,
    default_config, validate_config, DEFAULT_AGENTS,
)


def test_default_config_has_three_agents():
    config = default_config()
    assert len(config.agents) == 3
    agent_ids = [a.id for a in config.agents]
    assert "pa-agent" in agent_ids
    assert "reminder-agent" in agent_ids
    assert "market-agent" in agent_ids


def test_default_agents_have_correct_autonomy():
    config = default_config()
    for agent in config.agents:
        assert agent.autonomy == "ask"


def test_validate_config_rejects_invalid_autonomy():
    config = default_config()
    config.agents[0].autonomy = "yolo"
    errors = validate_config(config)
    assert len(errors) > 0
    assert "autonomy" in errors[0].lower()


def test_validate_config_rejects_duplicate_agent_ids():
    config = default_config()
    config.agents.append(AgentConfig(
        id="pa-agent", name="Duplicate", type="custom",
        system_prompt="test", model="x", tools=[], channels=[],
        mcp_channels=[], autonomy="ask"
    ))
    errors = validate_config(config)
    assert any("duplicate" in e.lower() for e in errors)


def test_validate_config_accepts_valid_config():
    config = default_config()
    errors = validate_config(config)
    assert errors == []


def test_config_to_dict_roundtrip():
    config = default_config()
    d = config.to_dict()
    restored = HiveConfig.from_dict(d)
    assert len(restored.agents) == len(config.agents)
    assert restored.agents[0].id == config.agents[0].id


def test_channel_config_serialization():
    ch = ChannelConfig(
        id="slack-1", type="communication", provider="slack",
        config={"webhook_url": "encrypted:abc"},
        permissions=["send", "receive"], agents=["pa-agent"]
    )
    d = ch.to_dict()
    assert d["provider"] == "slack"
    restored = ChannelConfig.from_dict(d)
    assert restored.id == "slack-1"
