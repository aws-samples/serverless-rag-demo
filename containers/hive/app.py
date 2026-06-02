# containers/hive/app.py
import asyncio
import json
import logging
import os
from bedrock_agentcore import BedrockAgentCoreApp
from hive_core.state import StateManager
from hive_core.bus import MessageBus, Message
from hive_core.event_log import EventLog
from hive_core.config import HiveConfig, default_config
from hive_core.registry import AgentRegistry
from hive_core.router import HiveRouter
from hive_core.executor import CodeExecutor
from hive_core.scheduler import HiveScheduler
from hive_core.agents.pa import PersonalAssistantAgent
from hive_core.agents.reminder import ReminderAgent
from hive_core.agents.market import MarketAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BUCKET = os.getenv("HIVE_STATE_BUCKET", "hive-state-test")
KMS_KEY_ID = os.getenv("HIVE_KMS_KEY_ID", "")
REGION = os.getenv("REGION", "us-east-1")

app = BedrockAgentCoreApp()


class HiveSession:
    """Per-user Hive session with full agent orchestration."""

    def __init__(self, user_id: str, workspace_dir: str = "/tmp/hive"):
        self.user_id = user_id
        self.state = StateManager(bucket=BUCKET, user_id=user_id, kms_key_id=KMS_KEY_ID)
        self.bus = MessageBus()
        self.event_log = EventLog(bucket=BUCKET, user_id=user_id)
        self.executor = CodeExecutor(workspace_dir=workspace_dir)
        self.scheduler = HiveScheduler(state=self.state, bus=self.bus)
        self.registry = AgentRegistry(bus=self.bus, event_log=self.event_log)
        self.router = HiveRouter(bus=self.bus, registry=self.registry, event_log=self.event_log)
        self.config: HiveConfig = default_config()
        self._response_queue: asyncio.Queue = asyncio.Queue()

    async def initialize(self):
        """Load state and initialize agents."""
        stored = self.state.load_config()
        if stored.get("agents"):
            self.config = HiveConfig.from_dict(stored)
        else:
            self.config = default_config()
            self.state.save_config(self.config.to_dict())

        self._register_default_agents()
        self.scheduler.load()
        self.scheduler.start()
        self.bus.subscribe("__user__", self._collect_response)
        logger.info(f"Session initialized for {self.user_id}")

    def _register_default_agents(self):
        PersonalAssistantAgent(bus=self.bus, event_log=self.event_log, executor=self.executor)
        ReminderAgent(bus=self.bus, event_log=self.event_log, scheduler=self.scheduler)
        MarketAgent(bus=self.bus, event_log=self.event_log)

    async def _collect_response(self, message: Message):
        await self._response_queue.put(message)

    async def handle_query(self, query: str):
        target = await self.router.route(self.user_id, query)
        return target

    async def get_response(self, timeout: float = 60.0) -> dict | None:
        try:
            msg = await asyncio.wait_for(self._response_queue.get(), timeout=timeout)
            return msg.payload
        except asyncio.TimeoutError:
            logger.error("Agent response timeout after 60s")
            return None

    def shutdown(self):
        self.scheduler.stop()
        self.event_log.flush()


@app.websocket
async def websocket_handler(websocket, context):
    """Hive WebSocket handler with full agent orchestration."""
    await websocket.accept()
    session = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "init":
                user_id = data.get("user_id", "anonymous")
                session = HiveSession(user_id)
                await session.initialize()
                await websocket.send_json({
                    "type": "init_complete",
                    "config": session.config.to_dict(),
                })

            elif msg_type == "chat" and session:
                query = data.get("query", "")
                session.event_log.append("user", "message", {"query": query})
                target = await session.handle_query(query)
                await websocket.send_json({"type": "routed", "target": target})
                response = await session.get_response()
                if response:
                    await websocket.send_json({"type": "response", "data": response})
                else:
                    await websocket.send_json({"type": "error", "message": "Agent timeout"})

            elif msg_type == "get_events" and session:
                events = session.event_log.get_recent(data.get("count", 50))
                await websocket.send_json({"type": "events", "events": events})

            elif msg_type == "get_config" and session:
                await websocket.send_json({
                    "type": "config",
                    "config": session.config.to_dict(),
                })

            elif msg_type == "wipe" and session:
                session.shutdown()
                session.state.wipe()
                session = None
                await websocket.send_json({"type": "wiped"})

    except Exception as e:
        if "disconnect" not in str(e).lower():
            logger.error(f"WebSocket error: {e}")
    finally:
        if session:
            session.shutdown()


if __name__ == "__main__":
    app.run(host="0.0.0.0", log_level="info")
