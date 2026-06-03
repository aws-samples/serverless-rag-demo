"""Strands tools for agents to interact with configured channels."""
import asyncio
import logging
from strands import tool

logger = logging.getLogger(__name__)


# Global references set by app.py when session initializes
_channel_manager = None
_event_loop = None


def set_channel_manager(cm):
    global _channel_manager, _event_loop
    _channel_manager = cm
    try:
        _event_loop = asyncio.get_running_loop()
    except RuntimeError:
        _event_loop = None


def _run_async(coro):
    """Run async coroutine from sync Strands tool context."""
    global _event_loop
    if _event_loop and _event_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, _event_loop)
        return future.result(timeout=10)
    else:
        return asyncio.run(coro)


@tool
def send_channel_message(channel_id: str, to: str, message: str) -> dict:
    """Send a message through a configured channel (WhatsApp, Slack, etc).

    Args:
        channel_id: The channel ID to send through (e.g. "test-wh", "slack-t")
        to: The recipient. For WhatsApp: phone@s.whatsapp.net (e.g. "61412345678@s.whatsapp.net"). For Slack: channel name.
        message: The message text to send.

    Returns:
        dict with success status and details.
    """
    global _channel_manager
    if not _channel_manager:
        return {"success": False, "error": "No channel manager available"}

    ch = _channel_manager.communication_channels.get(channel_id)
    if not ch:
        available = list(_channel_manager.communication_channels.keys())
        return {"success": False, "error": f"Channel '{channel_id}' not found. Available: {available}"}

    # For WhatsApp, check actual sidecar status (don't rely on cached _connected)
    if hasattr(ch, "get_status"):
        try:
            status = _run_async(ch.get_status())
            if not status.get("connected"):
                return {"success": False, "error": f"Channel '{channel_id}' sidecar reports not connected"}
            # Sync the flag
            if hasattr(ch, "_connected"):
                ch._connected = True
        except Exception as e:
            return {"success": False, "error": f"Cannot reach channel sidecar: {e}"}

    try:
        _run_async(ch.send(to, message))
        return {"success": True, "channel_id": channel_id, "to": to, "message_sent": message[:100]}
    except Exception as e:
        logger.error(f"send_channel_message failed: {e}")
        return {"success": False, "error": str(e)}


@tool
def read_channel_messages(channel_id: str, contact: str, limit: int = 10) -> dict:
    """Read recent messages from a contact on a channel (WhatsApp).

    Args:
        channel_id: The channel ID (e.g. "test-wh")
        contact: The contact JID. For WhatsApp: phone@s.whatsapp.net (e.g. "61412345678@s.whatsapp.net"). You can also use just the phone number and @s.whatsapp.net will be appended.
        limit: Number of recent messages to fetch (default 10, max 50).

    Returns:
        dict with messages list, each having: from, text, timestamp, fromMe
    """
    global _channel_manager
    if not _channel_manager:
        return {"success": False, "error": "No channel manager available"}

    ch = _channel_manager.communication_channels.get(channel_id)
    if not ch:
        available = list(_channel_manager.communication_channels.keys())
        return {"success": False, "error": f"Channel '{channel_id}' not found. Available: {available}"}

    if not hasattr(ch, "get_messages"):
        return {"success": False, "error": f"Channel '{channel_id}' does not support reading messages"}

    # Normalize contact JID
    jid = contact if "@" in contact else f"{contact}@s.whatsapp.net"

    try:
        messages = _run_async(ch.get_messages(jid, min(limit, 50)))
        return {"success": True, "channel_id": channel_id, "contact": jid, "messages": messages}
    except Exception as e:
        logger.error(f"read_channel_messages failed: {e}")
        return {"success": False, "error": str(e)}


@tool
def list_channel_contacts(channel_id: str) -> dict:
    """List contacts with recent message activity on a channel (WhatsApp).

    Args:
        channel_id: The channel ID (e.g. "test-wh")

    Returns:
        dict with contacts list, each having: jid, name, last_message, last_timestamp, message_count
    """
    global _channel_manager
    if not _channel_manager:
        return {"success": False, "error": "No channel manager available"}

    ch = _channel_manager.communication_channels.get(channel_id)
    if not ch:
        available = list(_channel_manager.communication_channels.keys())
        return {"success": False, "error": f"Channel '{channel_id}' not found. Available: {available}"}

    if not hasattr(ch, "get_contacts"):
        return {"success": False, "error": f"Channel '{channel_id}' does not support listing contacts"}

    try:
        contacts = _run_async(ch.get_contacts())
        return {"success": True, "channel_id": channel_id, "contacts": contacts}
    except Exception as e:
        logger.error(f"list_channel_contacts failed: {e}")
        return {"success": False, "error": str(e)}
