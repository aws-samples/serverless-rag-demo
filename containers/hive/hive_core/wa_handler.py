import asyncio
import json
import logging
import time
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
        guardrails: dict | None = None,
    ):
        self.channel = channel
        self._route = route_fn
        self._get_response = get_response_fn
        self._ws_notify = ws_notify_fn
        self._guardrails = guardrails or {}
        self._pending_approvals: dict[str, dict] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._processing = False

    def _is_allowed(self, sender: str, from_name: str = "", phone_jid: str = "") -> bool:
        """Check if sender is on the allowlist (if enabled).

        Matches against: contact name (case-insensitive), phone number, JID, or LID.
        Name matching is the primary mechanism since WhatsApp uses opaque LIDs.
        """
        # Reload allowlist from channel config each time (supports hot-update)
        raw = getattr(self.channel, "_raw_config", {})
        allowlist_enabled = raw.get("allowlist_enabled") == "true"

        if not allowlist_enabled:
            return True  # No filtering, allow all

        try:
            allowlist = json.loads(raw.get("allowlist", "[]"))
        except (json.JSONDecodeError, TypeError):
            allowlist = []

        if not allowlist:
            return True  # Empty allowlist with enabled flag = allow all

        # Collect all JID/phone identifiers to check
        identifiers = [sender]
        if phone_jid and phone_jid != sender:
            identifiers.append(phone_jid)

        from_name_lower = from_name.lower() if from_name else ""

        for entry in allowlist:
            entry_clean = entry.strip()
            if not entry_clean:
                continue
            entry_lower = entry_clean.lower()

            # 1. Name match (case-insensitive)
            # - Exact match
            # - Entry is prefix of name (e.g. "Fraser" matches "Fraser Sequeira")
            # - Single-word entry matches first name
            if from_name_lower:
                if entry_lower == from_name_lower:
                    return True
                if from_name_lower.startswith(entry_lower + " "):
                    return True
                # Single-word allowlist entry matches first word of pushName
                if " " not in entry_lower and from_name_lower.split()[0] == entry_lower:
                    return True

            # 2. JID/number match
            entry_number = entry_clean.split("@")[0] if "@" in entry_clean else entry_clean
            entry_number_clean = entry_number.lstrip("+")

            for identifier in identifiers:
                if identifier == entry_clean:
                    return True
                id_number = identifier.split("@")[0] if "@" in identifier else identifier
                id_number_clean = id_number.lstrip("+")
                if id_number_clean == entry_number_clean:
                    return True

        return False

    async def handle_message(self, payload: dict):
        """Queue incoming message for sequential processing."""
        await self._queue.put(payload)
        if not self._processing:
            asyncio.ensure_future(self._process_queue())

    async def _process_queue(self):
        """Process queued messages one at a time (Strands doesn't support concurrency)."""
        if self._processing:
            return
        self._processing = True
        try:
            while not self._queue.empty():
                payload = await self._queue.get()
                try:
                    await self._handle_single_message(payload)
                except Exception as e:
                    logger.error(f"Error processing WA message: {e}")
                    # Send refusal on unhandled errors
                    sender = payload.get("from", "")
                    if sender:
                        refusal = self._guardrails.get(
                            "refusal_message",
                            "Sorry, I'm unable to process that right now.",
                        )
                        try:
                            await self.channel.send(sender, refusal)
                        except Exception:
                            pass
        finally:
            self._processing = False

    async def _handle_single_message(self, payload: dict):
        """Process a single incoming WhatsApp message based on mode."""
        sender = payload["from"]
        message = payload["message"]
        from_name = payload.get("from_name", "")
        phone_jid = payload.get("phone_jid", "")  # Resolved phone from LID mapping

        # Allowlist filtering: check sender, resolved phone, and name
        if not self._is_allowed(sender, from_name, phone_jid):
            raw = getattr(self.channel, "_raw_config", {})
            al = raw.get("allowlist", "[]")
            logger.info(f"WA incoming from {from_name} ({sender}, phone={phone_jid}) — not on allowlist {al}, ignoring")
            return

        mode = self.channel.get_mode_for_sender(sender)

        logger.info(f"WA incoming from {from_name} ({sender}), mode={mode}")

        if mode in ("redirect-to-agent", "silent", "notify"):
            # Route through Hive with channel/contact context for persona
            target = await self._route(message, self.channel.channel_id, sender)
            response = await self._get_response()
            result_text = ""
            if response:
                result_text = response.get("result", str(response))

            # If agent produced no response (timeout), send refusal message
            if not result_text:
                result_text = self._guardrails.get(
                    "refusal_message",
                    "Sorry, I'm unable to process that right now.",
                )

            # Send reply via WhatsApp
            await self.channel.send(sender, result_text)

            # Notify UI with generic channel events
            await self._ws_notify({
                "type": "channel_incoming",
                "channel_id": self.channel.channel_id,
                "provider": "whatsapp",
                "contact": sender,
                "contact_name": from_name or sender,
                "message": message,
                "timestamp": int(time.time()),
                "reply": result_text,
                "metadata": {"mode": mode},
            })

            await self._ws_notify({
                "type": "channel_outgoing",
                "channel_id": self.channel.channel_id,
                "provider": "whatsapp",
                "contact": sender,
                "contact_name": from_name or sender,
                "message": result_text,
                "timestamp": int(time.time()),
            })

        elif mode == "ask":
            # Route to get proposed response, but don't send yet
            target = await self._route(message, self.channel.channel_id, sender)
            response = await self._get_response()
            result_text = ""
            if response:
                result_text = response.get("result", str(response))

            if not result_text:
                result_text = self._guardrails.get(
                    "refusal_message",
                    "Sorry, I'm unable to process that right now.",
                )

            # Store pending approval
            approval_id = f"{sender}:{payload.get('timestamp', '')}"
            self._pending_approvals[approval_id] = {
                "sender": sender,
                "response": result_text,
            }

            # Push to UI for approval (uses wa_incoming for approval flow)
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
