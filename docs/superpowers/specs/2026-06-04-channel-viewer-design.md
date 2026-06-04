# Channel Viewer — Live Message Feed

## Summary

A new "Messages" tab in the Hive UI showing a real-time FIFO feed of all WhatsApp messages (incoming and outgoing), capped at 50 entries. No persistence — resets on page reload.

## UI Component

**Tab placement:** Between "Chat" and "Persona" tabs.

**Component:** `ChannelMessageFeed` in `artifacts/chat-ui/src/components/hive/channel-message-feed.tsx`

**Layout:** Scrollable list (auto-scrolls to bottom on new messages). Each entry is a compact card:

```
[←] Fraser Sequeira                           12:34 PM
Hey, can you remind me about the meeting?
    → Agent replied: Sure, I'll remind you at 3pm.
```

**Fields per entry:**
- `direction`: "in" | "out"
- `contact_name`: Display name of the sender/recipient
- `contact_jid`: JID/LID (shown as tooltip or subtitle, not primary)
- `message`: Message text
- `reply`: Agent's reply text (only for incoming messages that got a response)
- `channel_id`: Which channel this came through
- `timestamp`: Unix timestamp, displayed as relative or HH:MM

**Styling:**
- Incoming: left-aligned, subtle background
- Outgoing: right-aligned or prefixed with arrow indicator
- Use existing Cloudscape components (Box, SpaceBetween, Badge)

## Data Flow

### WebSocket Events

**Existing event (no change needed):**
```typescript
{ type: "wa_incoming"; channel_id: string; from: string; from_name: string; message: string; mode: string; response?: string }
```

**New event from backend:**
```typescript
{ type: "wa_outgoing"; channel_id: string; to: string; to_name: string; message: string; timestamp: number }
```

### Frontend State

In `hive-layout.tsx`:
```typescript
const [channelMessages, setChannelMessages] = useState<ChannelMessage[]>([]);
```

Type definition in `types.ts`:
```typescript
export interface ChannelMessage {
    id: string;
    direction: "in" | "out";
    contact_name: string;
    contact_jid: string;
    channel_id: string;
    message: string;
    reply?: string;
    timestamp: number;
}
```

Add to `HiveResponse` union:
```typescript
| { type: "wa_outgoing"; channel_id: string; to: string; to_name: string; message: string; timestamp: number }
```

### FIFO Logic

On each new message (incoming or outgoing), append to array and trim to 50:
```typescript
setChannelMessages(prev => [...prev, newMsg].slice(-50));
```

## Backend Changes

### File: `containers/hive/hive_core/wa_handler.py`

In `_handle_single_message`, after the agent sends a reply via `channel.send()`, notify the UI:

```python
await self._ws_notify({
    "type": "wa_outgoing",
    "channel_id": self.channel.channel_id,
    "to": sender,
    "to_name": from_name,
    "message": result_text,
    "timestamp": int(time.time()),
})
```

Also send `wa_outgoing` when the agent proactively sends messages via the `send_channel_message` tool (in `tools/channel_send.py`). This requires the tool to call `ws_notify` after sending — add a module-level notify function reference similar to `_channel_manager`.

### File: `containers/hive/hive_core/tools/channel_send.py`

Add a module-level `_ws_notify_fn` that gets set from `app.py` during session setup. After a successful send, call:
```python
if _ws_notify_fn:
    asyncio.run_coroutine_threadsafe(
        _ws_notify_fn({"type": "wa_outgoing", "channel_id": channel_id, "to": to, "to_name": to, "message": message, "timestamp": int(time.time())}),
        _loop
    )
```

## Scope

- No message persistence (memory only, lost on reload)
- No message search/filter
- No read receipts or delivery status
- No media messages (text only)
- 50 message cap, oldest dropped first
