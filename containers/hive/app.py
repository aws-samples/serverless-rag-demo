# containers/hive/app.py
import asyncio
import json
import logging
import os
from bedrock_agentcore import BedrockAgentCoreApp
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from hive_core.state import StateManager
from hive_core.bus import MessageBus, Message
from hive_core.event_log import EventLog
from hive_core.config import HiveConfig, ChannelConfig, AgentConfig, default_config
from hive_core.agents.base import HiveAgent
from hive_core.registry import AgentRegistry
from hive_core.router import HiveRouter
from hive_core.executor import CodeExecutor
from hive_core.scheduler import HiveScheduler
from hive_core.agents.pa import PersonalAssistantAgent
from hive_core.agents.reminder import ReminderAgent
from hive_core.agents.market import MarketAgent
from hive_core.channels.manager import ChannelManager
from hive_core.tools.channel_send import set_channel_manager as _set_channel_manager_ref
from hive_core.tools.mcp_bridge import set_mcp_pool as _set_mcp_pool_ref
from hive_core.wa_handler import WhatsAppIncomingHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BUCKET = os.getenv("HIVE_STATE_BUCKET", "hive-state-test")
KMS_KEY_ID = os.getenv("HIVE_KMS_KEY_ID", "")
REGION = os.getenv("REGION", "us-east-1")

app = BedrockAgentCoreApp()

# Global reference to active session (single-user per container)
_active_session = None
_active_websocket = None


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
        self.channel_manager = ChannelManager(bus=self.bus, bucket=BUCKET, user_id=user_id)
        self.config: HiveConfig = default_config()
        self._response_queue: asyncio.Queue = asyncio.Queue()
        self.wa_handler: WhatsAppIncomingHandler | None = None

    async def initialize(self):
        """Load state and initialize agents."""
        stored = self.state.load_config()
        if stored.get("agents"):
            self.config = HiveConfig.from_dict(stored)
        else:
            self.config = default_config()
            self.state.save_config(self.config.to_dict())

        self._register_default_agents()
        # Load and apply persona to all agents
        self.persona = self.state.load_persona()
        for agent in self._agents:
            agent.set_persona(self.persona)
        # Load and apply guardrails to all agents
        self.guardrails = self.state.load_guardrails()
        for agent in self._agents:
            agent.set_guardrails(self.guardrails)
        await self._restore_channels()
        _set_channel_manager_ref(self.channel_manager)
        _set_mcp_pool_ref(self.channel_manager.mcp_pool)
        self.router.set_context_provider(self._build_context)
        self._sync_router_custom_agents()
        self.scheduler.load()
        self.scheduler.start()
        self.bus.subscribe("__user__", self._collect_response)
        logger.info(f"Session initialized for {self.user_id}")

    async def _restore_channels(self):
        """Re-register stored channels on session init."""
        for ch_cfg in self.config.channels:
            try:
                result = await self.channel_manager.register_channel(ch_cfg)
                if ch_cfg.provider == "whatsapp-baileys":
                    wa_channel = self.channel_manager.get_whatsapp_channel(ch_cfg.id)
                    if wa_channel:
                        self.setup_wa_handler(wa_channel)
                logger.info(f"Restored channel: {ch_cfg.id} ({result.get('status', 'ok')})")
            except Exception as e:
                logger.warning(f"Failed to restore channel {ch_cfg.id}: {e}")

    def _register_default_agents(self):
        from hive_core.tools.channel_send import send_channel_message, read_channel_messages, list_channel_contacts
        self._agents = [
            PersonalAssistantAgent(bus=self.bus, event_log=self.event_log, executor=self.executor),
            ReminderAgent(bus=self.bus, event_log=self.event_log, scheduler=self.scheduler),
            MarketAgent(bus=self.bus, event_log=self.event_log),
        ]
        # Restore custom agents from config
        for agent_cfg in self.config.agents:
            if agent_cfg.type == "custom":
                custom_agent = HiveAgent(
                    agent_id=agent_cfg.id,
                    name=agent_cfg.name,
                    system_prompt=agent_cfg.system_prompt,
                    model_id=agent_cfg.model,
                    tools=[send_channel_message, read_channel_messages, list_channel_contacts],
                    bus=self.bus,
                    event_log=self.event_log,
                )
                self._agents.append(custom_agent)
                logger.info(f"Restored custom agent: {agent_cfg.id}")

    def _sync_router_custom_agents(self):
        """Update the router with current custom agent list."""
        custom = [
            {"id": a.id, "description": a.system_prompt[:100]}
            for a in self.config.agents if a.type == "custom"
        ]
        self.router.set_custom_agents(custom)

    def _reload_agent_tools(self):
        """Force all agents to re-initialize with updated MCP tools."""
        for agent in self._agents:
            agent.reload_tools()

    def _build_context(self) -> str:
        """Build runtime context string for agents (channels, agents, capabilities)."""
        parts = []
        if self.config.channels:
            ch_lines = []
            for ch in self.config.channels:
                status = " [active]"
                comm_ch = self.channel_manager.communication_channels.get(ch.id)
                if not comm_ch:
                    status = " [not initialized]"
                ch_lines.append(f"  - {ch.id} ({ch.provider}, {ch.type}){status}")
            parts.append("Configured channels:\n" + "\n".join(ch_lines))
        agents_str = ", ".join(a.id for a in self.config.agents) if hasattr(self.config, 'agents') else ""
        if agents_str:
            parts.append(f"Available agents: {agents_str}")
        return "\n".join(parts) if parts else ""

    async def _collect_response(self, message: Message):
        await self._response_queue.put(message)

    async def handle_query(self, query: str, channel_id: str = "", contact_jid: str = ""):
        target = await self.router.route(self.user_id, query, channel_id=channel_id, contact_jid=contact_jid)
        return target

    async def get_response(self, timeout: float = 60.0) -> dict | None:
        try:
            msg = await asyncio.wait_for(self._response_queue.get(), timeout=timeout)
            return msg.payload
        except asyncio.TimeoutError:
            logger.error("Agent response timeout after 60s")
            return None

    def setup_wa_handler(self, channel):
        """Wire up WhatsApp incoming handler for a channel."""
        async def ws_notify(data):
            global _active_websocket
            if _active_websocket:
                try:
                    await _active_websocket.send_json(data)
                except Exception:
                    pass

        async def route_with_context(query: str, channel_id: str = "", contact_jid: str = ""):
            return await self.handle_query(query, channel_id=channel_id, contact_jid=contact_jid)

        self.wa_handler = WhatsAppIncomingHandler(
            channel=channel,
            route_fn=route_with_context,
            get_response_fn=self.get_response,
            ws_notify_fn=ws_notify,
            guardrails=self.guardrails,
        )

    def shutdown(self):
        self.scheduler.stop()
        self.event_log.flush()


@app.websocket
async def websocket_handler(websocket, context):
    """Hive WebSocket handler with full agent orchestration."""
    global _active_session, _active_websocket
    await websocket.accept()
    _active_websocket = websocket
    session = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "init":
                user_id = data.get("user_id", "anonymous")
                session = HiveSession(user_id)
                await session.initialize()
                _active_session = session
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

            elif msg_type == "add_channel" and session:
                channel_data = data.get("channel", {})
                channel_cfg = ChannelConfig.from_dict(channel_data)
                result = await session.channel_manager.register_channel(channel_cfg)
                session.config.channels.append(channel_cfg)
                session.state.save_config(session.config.to_dict())
                session.event_log.append("system", "channel_added", {"id": channel_cfg.id})

                # If MCP data channel, reload agent tools
                if channel_cfg.type == "data" and channel_cfg.provider == "mcp":
                    _set_mcp_pool_ref(session.channel_manager.mcp_pool)
                    session._reload_agent_tools()

                # If WhatsApp, set up handler and relay QR/status
                if channel_cfg.provider == "whatsapp-baileys":
                    wa_channel = session.channel_manager.get_whatsapp_channel(channel_cfg.id)
                    if wa_channel:
                        session.setup_wa_handler(wa_channel)
                    if result.get("status") == "qr_needed":
                        await websocket.send_json({
                            "type": "wa_qr",
                            "channel_id": channel_cfg.id,
                            "qr": result.get("qr", ""),
                        })
                    elif result.get("status") == "connected":
                        await websocket.send_json({
                            "type": "wa_connected",
                            "channel_id": channel_cfg.id,
                            "phone": result.get("phone", ""),
                        })

                await websocket.send_json({
                    "type": "channel_added",
                    "channel": channel_data,
                    "config": session.config.to_dict(),
                })

            elif msg_type == "remove_channel" and session:
                channel_id = data.get("channel_id", "")
                # Check if it's an MCP channel before removing
                cfg = next((c for c in session.config.channels if c.id == channel_id), None)
                await session.channel_manager.unregister_channel(channel_id)
                session.config.channels = [c for c in session.config.channels if c.id != channel_id]
                session.state.save_config(session.config.to_dict())
                session.event_log.append("system", "channel_removed", {"id": channel_id})
                if cfg and cfg.type == "data" and cfg.provider == "mcp":
                    session._reload_agent_tools()
                await websocket.send_json({
                    "type": "channel_removed",
                    "channel_id": channel_id,
                    "config": session.config.to_dict(),
                })

            elif msg_type == "update_channel" and session:
                channel_data = data.get("channel", {})
                channel_id = channel_data.get("id", "")
                # Remove old, re-register new
                await session.channel_manager.unregister_channel(channel_id)
                session.config.channels = [c for c in session.config.channels if c.id != channel_id]
                channel_cfg = ChannelConfig.from_dict(channel_data)
                result = await session.channel_manager.register_channel(channel_cfg)
                session.config.channels.append(channel_cfg)
                session.state.save_config(session.config.to_dict())
                session.event_log.append("system", "channel_updated", {"id": channel_id})

                if channel_cfg.provider == "whatsapp-baileys":
                    wa_channel = session.channel_manager.get_whatsapp_channel(channel_cfg.id)
                    if wa_channel:
                        session.setup_wa_handler(wa_channel)
                    if result.get("status") == "qr_needed":
                        await websocket.send_json({
                            "type": "wa_qr",
                            "channel_id": channel_cfg.id,
                            "qr": result.get("qr", ""),
                        })

                await websocket.send_json({
                    "type": "channel_updated",
                    "channel": channel_data,
                    "config": session.config.to_dict(),
                })

            elif msg_type == "test_channel" and session:
                channel_id = data.get("channel_id", "")
                ch = session.channel_manager.communication_channels.get(channel_id)
                if ch and hasattr(ch, "get_status"):
                    try:
                        status = await ch.get_status()
                        # Sync _connected flag from actual sidecar status
                        if hasattr(ch, "_connected"):
                            ch._connected = status.get("connected", False)
                        await websocket.send_json({"type": "channel_test", "channel_id": channel_id, **status})
                    except Exception as e:
                        await websocket.send_json({"type": "channel_test", "channel_id": channel_id, "connected": False, "message": f"Error: {e}"})
                elif ch:
                    await websocket.send_json({"type": "channel_test", "channel_id": channel_id, "connected": True, "message": "Channel active (no status endpoint)"})
                else:
                    # Channel in config but not in communication_channels
                    cfg = next((c for c in session.config.channels if c.id == channel_id), None)
                    await websocket.send_json({"type": "channel_test", "channel_id": channel_id, "connected": False, "message": f"Channel not initialized ({cfg.provider if cfg else 'unknown'})"})

            elif msg_type == "wa_approve" and session and session.wa_handler:
                approval_id = data.get("approval_id", "")
                action = data.get("action", "reject")
                edited = data.get("response", "")
                await session.wa_handler.handle_approval(approval_id, action, edited)

            elif msg_type == "get_events" and session:
                events = session.event_log.get_recent(data.get("count", 50))
                await websocket.send_json({"type": "events", "events": events})

            elif msg_type == "get_jobs" and session:
                jobs = [j.to_dict() for j in session.scheduler.list_jobs()]
                await websocket.send_json({"type": "jobs", "jobs": jobs})

            elif msg_type == "delete_job" and session:
                job_id = data.get("job_id", "")
                try:
                    session.scheduler.remove_job(job_id)
                    session.scheduler.persist()
                    if session.scheduler._ap_scheduler:
                        try:
                            session.scheduler._ap_scheduler.remove_job(job_id)
                        except Exception:
                            pass
                except KeyError:
                    pass
                jobs = [j.to_dict() for j in session.scheduler.list_jobs()]
                await websocket.send_json({"type": "job_deleted", "job_id": job_id, "jobs": jobs})

            elif msg_type == "add_agent" and session:
                agent_data = data.get("agent", {})
                agent_cfg = AgentConfig.from_dict(agent_data)
                # Add to config and persist
                session.config.agents.append(agent_cfg)
                session.state.save_config(session.config.to_dict())
                # Instantiate the agent
                from hive_core.tools.channel_send import send_channel_message, read_channel_messages, list_channel_contacts
                custom_agent = HiveAgent(
                    agent_id=agent_cfg.id,
                    name=agent_cfg.name,
                    system_prompt=agent_cfg.system_prompt,
                    model_id=agent_cfg.model,
                    tools=[send_channel_message, read_channel_messages, list_channel_contacts],
                    bus=session.bus,
                    event_log=session.event_log,
                )
                custom_agent.set_persona(session.persona)
                custom_agent.set_guardrails(session.guardrails)
                session._agents.append(custom_agent)
                session._sync_router_custom_agents()
                session.event_log.append("system", "agent_added", {"id": agent_cfg.id})
                await websocket.send_json({
                    "type": "agent_added",
                    "agent": agent_data,
                    "config": session.config.to_dict(),
                })

            elif msg_type == "remove_agent" and session:
                agent_id = data.get("agent_id", "")
                # Don't allow removing default agents
                agent_cfg = next((a for a in session.config.agents if a.id == agent_id), None)
                if agent_cfg and agent_cfg.type == "custom":
                    session.config.agents = [a for a in session.config.agents if a.id != agent_id]
                    session.state.save_config(session.config.to_dict())
                    # Shutdown and remove the agent instance
                    agent_instance = next((a for a in session._agents if a.agent_id == agent_id), None)
                    if agent_instance:
                        agent_instance.shutdown()
                        session._agents.remove(agent_instance)
                    session.event_log.append("system", "agent_removed", {"id": agent_id})
                    session._sync_router_custom_agents()
                await websocket.send_json({
                    "type": "agent_removed",
                    "agent_id": agent_id,
                    "config": session.config.to_dict(),
                })

            elif msg_type == "get_config" and session:
                await websocket.send_json({
                    "type": "config",
                    "config": session.config.to_dict(),
                })

            elif msg_type == "get_persona" and session:
                persona = session.state.load_persona()
                await websocket.send_json({"type": "persona", "persona": persona})

            elif msg_type == "save_persona" and session:
                persona_data = data.get("persona", {})
                session.state.save_persona(persona_data)
                session.persona = persona_data
                for agent in session._agents:
                    agent.set_persona(persona_data)
                await websocket.send_json({"type": "persona_saved", "persona": persona_data})

            elif msg_type == "get_guardrails" and session:
                guardrails = session.state.load_guardrails()
                await websocket.send_json({"type": "guardrails", "guardrails": guardrails})

            elif msg_type == "save_guardrails" and session:
                guardrails_data = data.get("guardrails", {})
                session.state.save_guardrails(guardrails_data)
                session.guardrails = guardrails_data
                for agent in session._agents:
                    agent.set_guardrails(guardrails_data)
                await websocket.send_json({"type": "guardrails_saved", "guardrails": guardrails_data})

            elif msg_type == "wipe" and session:
                session.shutdown()
                session.state.wipe()
                session = None
                _active_session = None
                await websocket.send_json({"type": "wiped"})

    except Exception as e:
        if "disconnect" not in str(e).lower():
            logger.error(f"WebSocket error: {e}")
    finally:
        if session:
            session.shutdown()
        _active_session = None
        _active_websocket = None


# Internal HTTP routes for sidecar communication
async def handle_wa_message(request: Request):
    """Receive incoming WhatsApp message from sidecar."""
    global _active_session
    if not _active_session or not _active_session.wa_handler:
        return JSONResponse({"error": "No active session"}, status_code=503)
    payload = await request.json()
    asyncio.create_task(_active_session.wa_handler.handle_message(payload))
    return JSONResponse({"ok": True})


async def handle_wa_event(request: Request):
    """Receive WhatsApp connection events from sidecar (qr, connected, disconnected)."""
    global _active_session, _active_websocket
    payload = await request.json()
    event = payload.get("event")

    if _active_websocket:
        if event == "qr":
            await _active_websocket.send_json({
                "type": "wa_qr",
                "channel_id": "whatsapp",
                "qr": payload.get("qr", ""),
            })
        elif event == "connected":
            await _active_websocket.send_json({
                "type": "wa_connected",
                "channel_id": "whatsapp",
                "phone": payload.get("phone", ""),
            })
            # Update channel state and persist auth
            if _active_session:
                for ch in _active_session.channel_manager.communication_channels.values():
                    if hasattr(ch, "_connected"):
                        ch._connected = True
                    if hasattr(ch, "persist_auth_to_s3"):
                        ch.persist_auth_to_s3()
        elif event == "disconnected":
            if _active_session:
                for ch in _active_session.channel_manager.communication_channels.values():
                    if hasattr(ch, "_connected"):
                        ch._connected = False
            await _active_websocket.send_json({
                "type": "wa_status",
                "channel_id": "whatsapp",
                "connected": False,
            })

    return JSONResponse({"ok": True})


# Register internal routes with the app's underlying ASGI app
app.routes.extend([
    Route("/internal/wa-message", handle_wa_message, methods=["POST"]),
    Route("/internal/wa-event", handle_wa_event, methods=["POST"]),
])


if __name__ == "__main__":
    app.run(host="0.0.0.0", log_level="info")
