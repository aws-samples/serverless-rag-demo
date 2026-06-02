# containers/hive/hive_core/agents/market.py
from hive_core.agents.base import HiveAgent
from hive_core.bus import MessageBus
from hive_core.event_log import EventLog


class MarketAgent(HiveAgent):
    """Analyzes markets, tracks assets, and provides portfolio insights."""

    def __init__(self, bus: MessageBus, event_log: EventLog):
        super().__init__(
            agent_id="market-agent",
            name="Market Agent",
            system_prompt=(
                "You analyze markets, track stocks/crypto, summarize financial news, "
                "and provide portfolio insights. Use available MCP data channels for "
                "real-time data. If no data channel is connected, use web search."
            ),
            model_id="global.anthropic.claude-sonnet-4-6-v1:0",
            tools=[],
            bus=bus,
            event_log=event_log,
        )

    async def process(self, payload: dict):
        return await super().process(payload)
