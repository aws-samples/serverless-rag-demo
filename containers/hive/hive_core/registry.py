import logging
from hive_core.agents.base import HiveAgent
from hive_core.bus import MessageBus
from hive_core.event_log import EventLog
from hive_core.config import AgentConfig

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Manages the lifecycle of agents within a Hive session."""

    def __init__(self, bus: MessageBus, event_log: EventLog):
        self.bus = bus
        self.event_log = event_log
        self.agents: dict[str, HiveAgent] = {}

    def register(self, config: AgentConfig) -> HiveAgent:
        if config.id in self.agents:
            raise ValueError(f"Agent '{config.id}' already registered")

        agent = HiveAgent(
            agent_id=config.id,
            name=config.name,
            system_prompt=config.system_prompt,
            model_id=config.model,
            tools=[],
            bus=self.bus,
            event_log=self.event_log,
        )
        self.agents[config.id] = agent
        logger.info(f"Registered agent: {config.id} ({config.name})")
        return agent

    def unregister(self, agent_id: str):
        if agent_id not in self.agents:
            raise KeyError(f"Agent '{agent_id}' not found")
        self.agents[agent_id].shutdown()
        del self.agents[agent_id]
        logger.info(f"Unregistered agent: {agent_id}")

    def get(self, agent_id: str) -> HiveAgent:
        return self.agents[agent_id]

    def list_agents(self) -> list[HiveAgent]:
        return list(self.agents.values())

    def shutdown_all(self):
        for agent_id in list(self.agents.keys()):
            self.unregister(agent_id)
