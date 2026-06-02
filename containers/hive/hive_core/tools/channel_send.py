"""Strands tool for agents to send messages through configured channels."""
import asyncio
import logging

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
