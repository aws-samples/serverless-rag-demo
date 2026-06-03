# Hive Persona System Design

## Overview

Per-user configurable persona ("soul") that gets injected into all Hive agent system prompts. Users define their identity, tone, and rules via the UI. Overrides can be applied at channel and contact/group levels.

## S3 Storage

Path: `users/{user_id}/persona.json`

```json
{
  "persona": "I'm Fraser. Speak as me in first person. Witty, concise...",
  "channel_overrides": {
    "whatsapp": "Keep messages short. Use emoji sparingly."
  },
  "contact_overrides": {
    "whatsapp::120363012345@g.us": "This is my work group. Be professional.",
    "whatsapp::61412345678@s.whatsapp.net": "Close friend. Very casual."
  }
}
```

## Runtime Injection

Effective persona is built by concatenating (in order):
1. Base `persona` text
2. Channel override (if `channel_id` present in payload)
3. Contact override (if `channel_id::contact_jid` present)

The effective persona is prepended to the agent's existing system prompt, separated by a newline block:

```
<persona>
{effective_persona}
</persona>

{agent_role_specific_system_prompt}
```

## Backend Changes

### StateManager (`containers/hive/hive_core/state.py`)

Add two methods:

```python
def load_persona(self) -> dict:
    return self._get_json(f"{self.prefix}/persona.json", {
        "persona": "",
        "channel_overrides": {},
        "contact_overrides": {},
    })

def save_persona(self, persona: dict):
    self._put_json(f"{self.prefix}/persona.json", persona)
```

### HiveSession (`containers/hive/app.py`)

- Load persona on `initialize()` and store as `self.persona`
- Pass persona dict to each agent via a new `set_persona()` method
- When persona is saved via WebSocket, update in-memory + S3, and call `reload_tools()` on agents to force re-init with new system prompt

### HiveAgent base (`containers/hive/hive_core/agents/base.py`)

- Add `set_persona(persona_dict)` method that stores the persona config
- Add `_build_effective_persona(channel_id, contact_jid)` method:
  ```python
  def _build_effective_persona(self, channel_id: str = "", contact_jid: str = "") -> str:
      if not self._persona or not self._persona.get("persona"):
          return ""
      parts = [self._persona["persona"]]
      if channel_id and channel_id in self._persona.get("channel_overrides", {}):
          parts.append(self._persona["channel_overrides"][channel_id])
      key = f"{channel_id}::{contact_jid}" if channel_id and contact_jid else ""
      if key and key in self._persona.get("contact_overrides", {}):
          parts.append(self._persona["contact_overrides"][key])
      return "\n\n".join(parts)
  ```
- Modify `process()` to extract `channel_id` and `contact_jid` from payload, build effective persona, and use it when initializing/calling the Strands agent
- The Strands agent is re-created if persona changes (detected by comparing effective persona to what was used at init time), OR persona is injected as a message prefix rather than system prompt change to avoid re-init on every contact switch

**Decision: Inject as system prompt prefix.** Re-create Strands agent when base persona or channel override changes. For contact-level overrides (which change per message), prepend to the user query instead:

```python
async def process(self, payload: dict) -> Any:
    query = payload.get("query", "")
    context = payload.get("context", "")
    channel_id = payload.get("channel_id", "")
    contact_jid = payload.get("contact_jid", "")

    # Build effective persona
    effective = self._build_effective_persona(channel_id, contact_jid)

    if context:
        query = f"{context}\n\nUser: {query}"

    if not self._strands_agent or self._persona_changed(channel_id):
        self._init_strands_agent(channel_id)

    # Contact override goes as query prefix (avoids agent re-init per contact)
    if contact_jid:
        contact_key = f"{channel_id}::{contact_jid}"
        contact_override = self._persona.get("contact_overrides", {}).get(contact_key, "")
        if contact_override:
            query = f"[Context for this contact: {contact_override}]\n\n{query}"

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, self._strands_agent, query)
    return str(result)
```

For `_init_strands_agent`, prepend base persona + channel override to system prompt:

```python
def _init_strands_agent(self, channel_id: str = ""):
    base_persona = self._persona.get("persona", "") if self._persona else ""
    channel_override = ""
    if channel_id and self._persona:
        channel_override = self._persona.get("channel_overrides", {}).get(channel_id, "")

    persona_block = "\n\n".join(filter(None, [base_persona, channel_override]))
    effective_prompt = self.system_prompt
    if persona_block:
        effective_prompt = f"<persona>\n{persona_block}\n</persona>\n\n{self.system_prompt}"

    # ... rest of init with effective_prompt
```

### WebSocket Handler (`app.py`)

Add two new message types:

```python
elif msg_type == "get_persona" and session:
    persona = session.state.load_persona()
    await websocket.send_json({"type": "persona", "persona": persona})

elif msg_type == "save_persona" and session:
    persona_data = data.get("persona", {})
    session.state.save_persona(persona_data)
    session.persona = persona_data
    for agent in session._agents:
        agent.set_persona(persona_data)
        agent.reload_tools()  # forces re-init with new system prompt
    await websocket.send_json({"type": "persona_saved", "persona": persona_data})
```

### WhatsApp Handler (`wa_handler.py`)

When routing incoming messages, include channel_id and contact_jid in the payload:

```python
# In handle_message, when publishing to bus:
payload = {
    "query": message_text,
    "user_id": self.user_id,
    "channel_id": "whatsapp",  # or the actual channel config id
    "contact_jid": sender_jid,
}
```

### Router (`router.py`)

Pass `channel_id` and `contact_jid` through to the agent payload (already flows via `route()` → bus publish).

## UI Changes

### New "Persona" Tab in `hive-layout.tsx`

Add between "Chat" and "Agents" tabs. Contains:

1. **Base Persona** - single `<Textarea>` with placeholder guidance
2. **Channel Overrides** - expandable section with:
   - List of existing overrides (channel dropdown + textarea + delete button)
   - "Add Channel Override" button (dropdown of configured channel IDs)
3. **Contact Overrides** - expandable section with:
   - List of existing overrides (text input for `channel::jid` + textarea + delete button)
   - "Add Contact Override" button (text inputs for channel ID + contact JID)
4. **Save button** - sends `save_persona` WebSocket message

### New Component: `persona-config.tsx`

```tsx
interface PersonaConfigProps {
    persona: PersonaData;
    channels: ChannelConfig[];
    onSave: (persona: PersonaData) => void;
}
```

### Types (`types.ts`)

```typescript
export interface PersonaData {
    persona: string;
    channel_overrides: Record<string, string>;
    contact_overrides: Record<string, string>;  // key format: "channelId::contactJid"
}
```

### WebSocket Messages

- Send: `{ type: "get_persona" }` (on tab open)
- Send: `{ type: "save_persona", persona: PersonaData }`
- Receive: `{ type: "persona", persona: PersonaData }`
- Receive: `{ type: "persona_saved", persona: PersonaData }`

## File Changes Summary

| File | Change |
|------|--------|
| `containers/hive/hive_core/state.py` | Add `load_persona()`, `save_persona()` |
| `containers/hive/hive_core/agents/base.py` | Add `set_persona()`, `_build_effective_persona()`, modify `process()` and `_init_strands_agent()` |
| `containers/hive/app.py` | Load persona on init, add `get_persona`/`save_persona` WebSocket handlers, pass persona to agents |
| `containers/hive/hive_core/router.py` | Pass `channel_id`/`contact_jid` through payload |
| `containers/hive/hive_core/wa_handler.py` | Include `channel_id` and `contact_jid` in routed payload |
| `artifacts/chat-ui/src/components/hive/types.ts` | Add `PersonaData` interface |
| `artifacts/chat-ui/src/components/hive/persona-config.tsx` | New component |
| `artifacts/chat-ui/src/components/hive/hive-layout.tsx` | Add Persona tab, load/save handlers |
