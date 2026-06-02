import copy
from dataclasses import dataclass, field, asdict
from typing import Any

VALID_AUTONOMY = ("ask", "notify", "silent")
VALID_CHANNEL_TYPES = ("communication", "data")
DEFAULT_MODEL = "global.anthropic.claude-sonnet-4-6-v1:0"


@dataclass
class AgentConfig:
    id: str
    name: str
    type: str  # "default" | "custom"
    system_prompt: str
    model: str
    tools: list[str]
    channels: list[str]
    mcp_channels: list[str]
    autonomy: str = "ask"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AgentConfig":
        return cls(**d)


@dataclass
class ChannelConfig:
    id: str
    type: str  # "communication" | "data"
    provider: str
    config: dict[str, Any]
    permissions: list[str]
    agents: list[str]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ChannelConfig":
        return cls(**d)


@dataclass
class HiveConfig:
    agents: list[AgentConfig] = field(default_factory=list)
    channels: list[ChannelConfig] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agents": [a.to_dict() for a in self.agents],
            "channels": [c.to_dict() for c in self.channels],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HiveConfig":
        return cls(
            agents=[AgentConfig.from_dict(a) for a in d.get("agents", [])],
            channels=[ChannelConfig.from_dict(c) for c in d.get("channels", [])],
        )


DEFAULT_AGENTS = [
    AgentConfig(
        id="pa-agent",
        name="Personal Assistant",
        type="default",
        system_prompt="You are a personal assistant. Help with general tasks, writing, summaries, and code execution. Be concise and helpful.",
        model=DEFAULT_MODEL,
        tools=["code_executor", "file_manager", "web_search"],
        channels=[],
        mcp_channels=[],
        autonomy="ask",
    ),
    AgentConfig(
        id="reminder-agent",
        name="Reminder Agent",
        type="default",
        system_prompt="You manage reminders, schedules, and recurring tasks. Create, list, and manage cron jobs. Always confirm scheduling details with the user.",
        model=DEFAULT_MODEL,
        tools=["cron_manager", "notification_sender"],
        channels=[],
        mcp_channels=[],
        autonomy="ask",
    ),
    AgentConfig(
        id="market-agent",
        name="Market Agent",
        type="default",
        system_prompt="You analyze markets, track stocks/crypto, summarize financial news, and provide portfolio insights. Use data channels for real-time data.",
        model=DEFAULT_MODEL,
        tools=["web_search", "data_analyzer"],
        channels=[],
        mcp_channels=[],
        autonomy="ask",
    ),
]


def default_config() -> HiveConfig:
    return HiveConfig(agents=copy.deepcopy(DEFAULT_AGENTS), channels=[])


def validate_config(config: HiveConfig) -> list[str]:
    errors = []
    seen_ids = set()

    for agent in config.agents:
        if agent.autonomy not in VALID_AUTONOMY:
            errors.append(f"Agent '{agent.id}': autonomy must be one of {VALID_AUTONOMY}")
        if agent.id in seen_ids:
            errors.append(f"Duplicate agent id: '{agent.id}'")
        seen_ids.add(agent.id)

    for channel in config.channels:
        if channel.type not in VALID_CHANNEL_TYPES:
            errors.append(f"Channel '{channel.id}': type must be one of {VALID_CHANNEL_TYPES}")

    return errors
