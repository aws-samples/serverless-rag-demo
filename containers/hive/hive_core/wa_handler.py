import asyncio
import logging
from typing import Any, Callable, Awaitable

from hive_core.channels.whatsapp import WhatsAppChannel
from hive_core.guardrails import resolve_tier

logger = logging.getLogger(__name__)


class WhatsAppIncomingHandler:
    """Handles incoming WhatsApp messages based on channel mode config."""

    def __init__(
        self,
        channel: WhatsAppChannel,
        route_fn: Callable[[str, str, str], Awaitable[str]],
        get_response_fn: Callable[[], Awaitable[dict | None]],
        ws_notify_fn: Callable[[dict], Awaitable[None]],
    ):
        self.channel = channel
        self._route = route_fn
        self._get_response = get_response_fn
        self._ws_notify = ws_notify_fn
        self._pending_approvals: dict[str, dict] = {}

    async def handle_message(self, payload: dict):
        """Process an incoming WhatsApp message based on mode."""
        sender = payload["from"]
        message = payload["message"]
        from_name = payload.get("from_name", "")
        mode = self.channel.get_mode_for_sender(sender)

        logger.info(f"WA incoming from {from_name} ({sender}), mode={mode}")

        if mode in ("redirect-to-agent", "silent", "notify"):
            # Route through Hive with channel/contact context for persona
            target = await self._route(message, self.channel.channel_id, sender)
            response = await self._get_response()
            result_text = ""
            if response:
                result_text = response.get("result", str(response))

            # Send reply via WhatsApp
            if result_text:
                await self.channel.send(sender, result_text)

            # Notify UI if mode requires it
            if mode == "notify":
                await self._ws_notify({
                    "type": "wa_incoming",
                    "channel_id": self.channel.channel_id,
                    "from": sender,
                    "from_name": from_name,
                    "message": message,
                    "mode": mode,
                    "response": result_text,
                })

        elif mode == "ask":
            # Route to get proposed response, but don't send yet
            target = await self._route(message, self.channel.channel_id, sender)
            response = await self._get_response()
            result_text = ""
            if response:
                result_text = response.get("result", str(response))

            # Store pending approval
            approval_id = f"{sender}:{payload.get('timestamp', '')}"
            self._pending_approvals[approval_id] = {
                "sender": sender,
                "response": result_text,
            }

            # Push to UI for approval
            await self._ws_notify({
                "type": "wa_incoming",
                "channel_id": self.channel.channel_id,
                "from": sender,
                "from_name": from_name,
                "message": message,
                "mode": "ask",
                "proposed_response": result_text,
                "approval_id": approval_id,
            })

    async def handle_approval(self, approval_id: str, action: str, edited_response: str = ""):
        """Handle user approval/rejection of a proposed response."""
        pending = self._pending_approvals.pop(approval_id, None)
        if not pending:
            logger.warning(f"No pending approval: {approval_id}")
            return

        if action == "send":
            await self.channel.send(pending["sender"], pending["response"])
        elif action == "edit":
            await self.channel.send(pending["sender"], edited_response)
        # "reject" = do nothing
