# WhatsApp Baileys Channel Integration

## Goal

Wire up end-to-end WhatsApp messaging for the Hive multi-agent platform using Baileys (unofficial WhatsApp Web client), running as a Node.js sidecar inside the Hive container with auth state persisted to S3.

## Architecture

Node.js Baileys sidecar process inside the Hive container communicates with the Python app via HTTP on localhost. Auth state is persisted to S3 so QR scanning is only needed once. Incoming WhatsApp messages are routed through the Hive agent system with configurable behavior per-channel and per-contact.

## Components

### 1. Baileys Sidecar (`containers/hive/sidecar/`)

A Node.js Express server running on `localhost:3001` inside the Hive container.

**Responsibilities:**
- Manage WhatsApp Web connection via `@whiskeysockets/baileys`
- Expose REST API: `POST /init`, `POST /send`, `GET /status`, `GET /qr`
- On startup, attempt to restore auth state from `/tmp/wa-auth`
- Forward incoming messages to Python app via `POST http://localhost:8080/internal/wa-message`
- Return QR code as base64 data URI when pairing is needed
- Handle reconnection automatically using persisted auth keys

**API:**
- `POST /init` — Start Baileys connection, return `{ status: "qr_needed" | "connected", qr?: string }`
- `POST /send` — Send message `{ to: "jid", message: string }` → `{ success: bool }`
- `GET /status` — Return `{ connected: bool, phone: string }`
- `GET /qr` — Return current QR code if in pairing state `{ qr: string | null }`
- `POST /shutdown` — Graceful disconnect

### 2. Auth State Persistence (Python)

On `register_channel` / session init:
- Download auth state from `s3://{HIVE_STATE_BUCKET}/users/{user_id}/wa-auth/` to `/tmp/wa-auth`

On shutdown / periodic:
- Upload `/tmp/wa-auth` to S3

This allows Baileys to reconnect without QR re-scan after container restarts (multi-device auth keys persist).

### 3. WhatsApp Channel (`hive_core/channels/whatsapp.py`)

Updated Python class that:
- Starts the sidecar process (`node sidecar/index.js`) on `register_channel`
- Restores auth state from S3 before starting sidecar
- Calls `POST /init` on sidecar, relays QR code to UI via WebSocket
- Handles incoming messages (received via internal HTTP endpoint) based on mode
- Persists auth state to S3 on shutdown
- Applies contact overrides for mode selection
- Adds configurable prefix to outgoing agent responses

### 4. Internal HTTP Endpoint (`/internal/wa-message`)

A new FastAPI/Starlette route on the main app (port 8080) that receives incoming WhatsApp messages from the sidecar:

```
POST /internal/wa-message
{
  "from": "919876543210@s.whatsapp.net",
  "from_name": "John",
  "message": "Hey, what time is the meeting?",
  "timestamp": 1780372000,
  "is_group": false,
  "group_id": null
}
```

This endpoint is internal-only (localhost), not exposed externally.

### 5. WebSocket Protocol Extensions

New message types between Hive backend and UI:

| Type | Direction | Payload |
|------|-----------|---------|
| `wa_qr` | server→client | `{ channel_id, qr: "data:image/png;base64,..." }` |
| `wa_connected` | server→client | `{ channel_id, phone }` |
| `wa_incoming` | server→client | `{ channel_id, from, from_name, message, mode }` |
| `wa_approve` | client→server | `{ channel_id, from, response, action: "send"\|"edit"\|"reject" }` |
| `wa_status` | server→client | `{ channel_id, connected: bool }` |

### 6. UI Changes

After saving channel in the wizard:
- Display QR code as a scannable image in a modal
- Once `wa_connected` received, dismiss modal, show green status indicator on channel
- Incoming messages (for `ask`/`notify` modes) appear in the chat panel with a WhatsApp badge
- For `ask` mode: show the proposed agent response with Approve / Edit / Reject buttons
- Channel status visible in the Channels tab

## Channel Config Schema

```json
{
  "id": "whazbot",
  "type": "communication",
  "provider": "whatsapp-baileys",
  "config": {
    "phone_number": "+917977989204",
    "incoming_mode": "redirect-to-agent",
    "reply_prefix": "",
    "contact_overrides": {
      "919876543210@s.whatsapp.net": {
        "mode": "ask",
        "label": "Boss"
      }
    }
  },
  "permissions": ["read", "send"],
  "agents": ["pa-agent", "reminder-agent", "market-agent"]
}
```

## Incoming Message Modes

| Mode | Behavior |
|------|----------|
| `ask` | Show in UI with proposed response, wait for user approval |
| `notify` | Auto-route to agent, respond via WhatsApp, show exchange in UI |
| `silent` | Auto-route and respond, no UI notification |
| `redirect-to-agent` | Full Hive takeover: route through HiveRouter, agent handles autonomously |

For `redirect-to-agent` vs `silent`: functionally identical except `redirect-to-agent` is the semantic intent (Hive owns the conversation). Both auto-route and auto-respond without UI notification.

## Message Flow

### Outgoing (agent → WhatsApp)

```
Agent response → ChannelManager.send(channel_id, text)
  → Add reply_prefix if configured
  → POST to sidecar /send endpoint
  → Baileys sends via WhatsApp Web
```

### Incoming (WhatsApp → agent)

```
WhatsApp message → Baileys sidecar receives
  → POST http://localhost:8080/internal/wa-message
  → Python handler:
    1. Lookup channel config
    2. Determine mode: contact_overrides[sender].mode || config.incoming_mode
    3. Based on mode:
       - "redirect-to-agent" / "silent": route through HiveRouter, send response back via WhatsApp
       - "notify": same + push wa_incoming to UI WebSocket
       - "ask": push wa_incoming to UI with proposed response, wait for wa_approve
```

### QR Code Pairing Flow

```
User clicks "Save Channel" in wizard
  → Backend: register_channel()
  → Download auth state from S3 (if exists)
  → Start sidecar process
  → POST /init to sidecar
  → If no auth state: sidecar returns QR
  → Backend sends wa_qr to UI WebSocket
  → UI shows QR modal
  → User scans with phone
  → Baileys connects, POSTs status update
  → Backend sends wa_connected to UI
  → UI dismisses modal, shows connected status
  → Backend uploads auth state to S3
```

## File Structure

```
containers/hive/
  sidecar/
    package.json
    index.js          # Express server + Baileys connection management
  hive_core/
    channels/
      whatsapp.py     # Updated: process management, auth persistence, message handling
      manager.py      # Updated: call initialize(), relay QR
  app.py              # Updated: internal /wa-message route, wa_approve handler
artifacts/chat-ui/
  src/components/hive/
    wa-qr-modal.tsx   # QR code display modal
    hive-layout.tsx   # Updated: handle wa_* message types
    channel-config.tsx # Updated: trigger QR flow after save
    types.ts          # Updated: new message types
```

## Constraints

- Baileys is unofficial — WhatsApp may break compatibility at any time
- Container idles out after 15 min on AgentCore; messages received while idle are lost
- Auth state in S3 allows reconnection without QR, but WhatsApp may invalidate sessions after extended inactivity (days/weeks)
- Internal HTTP endpoint must NOT be exposed externally (localhost only)
- Sidecar process lifecycle tied to the Python app lifecycle

## Dependencies

- `@whiskeysockets/baileys` (Node.js, already have Node in Dockerfile)
- `express` (Node.js sidecar HTTP server)
- `qrcode` (Node.js, generate QR as data URI)
- `aiohttp` (Python, HTTP client for sidecar communication) — add to requirements.txt
- No new infrastructure required (runs inside existing container)
