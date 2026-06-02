# Hive — Multi-Agent Platform Design

**Date:** 2026-06-02
**Status:** Approved
**Branch:** `feature/hive-multi-agent`
**Scope:** Nanobot-inspired multi-agent system with channels, MCP support, and agent visualization

---

## 1. Summary

**Hive** is a per-user, Strands-based microkernel agent platform with configurable specialist agents, a unified channel model (WhatsApp/Slack/MCP), autonomous code execution, internal cron scheduling, and a live animated graph UI. Deployed as an opt-in CDK stack alongside the existing RAG feature.

Inspired by [nanobot](https://github.com/HKUDS/nanobot) — an ultra-lightweight agent runtime — but built on AWS-native infrastructure with Strands Agents as the framework.

---

## 2. Architecture: Microkernel Pattern

```
+-----------------------------------------------------+
|         Hive Container (per user)                   |
|                                                     |
|  +-----------------------------------------------+ |
|  |              Hive Core (Orchestrator)          | |
|  |  - Message Router                             | |
|  |  - Agent Registry                             | |
|  |  - Cron Scheduler                             | |
|  |  - State Manager (S3 read/write)              | |
|  |  - MCP Connection Pool                        | |
|  |  - Channel Manager                            | |
|  +--------------------+------------------------+-+ |
|                       |    Message Bus         |    |
|  +--------------------+----+-------------------+--+ |
|  |         |               |                   |  | |
|  v         v               v                   v  | |
| +----+  +--------+  +----------+  +----------+   | |
| | PA |  |Reminder|  | Market   |  | Custom   |   | |
| |Agent|  | Agent  |  | Agent    |  | Agent(s) |   | |
| +----+  +--------+  +----------+  +----------+   | |
|                                                     |
|  +-----------------------------------------------+ |
|  |              Event Log (append-only)           | |
|  |  -> Powers live UI graph + audit trail         | |
|  +-----------------------------------------------+ |
+-----------------------------------------------------+
```

**Key principles:**
- Hive Core is a Strands agent whose only job is routing, scheduling, and lifecycle
- Each specialist agent is an independent Strands agent registered with the core
- Agents communicate via an in-memory message bus (asyncio queues)
- All messages appended to Event Log (powers UI graph + audit trail)
- True isolation between agents — misbehaving custom agents can't crash others

---

## 3. Unified Channel Model

Both communication endpoints (Slack, WhatsApp, email) and data/tool endpoints (MCP servers) are configured identically.

### Channel Config Schema

```json
{
  "channels": [
    {
      "id": "slack-personal",
      "type": "communication",
      "provider": "slack",
      "config": {
        "webhook_url": "encrypted:...",
        "bot_token": "encrypted:...",
        "default_channel": "#alerts"
      },
      "permissions": ["send", "receive"],
      "agents": ["pa-agent", "reminder-agent"]
    },
    {
      "id": "market-data-mcp",
      "type": "data",
      "provider": "mcp",
      "config": {
        "transport": "sse",
        "url": "https://market-data.example.com/mcp",
        "api_key": "encrypted:..."
      },
      "permissions": ["read"],
      "agents": ["market-agent"]
    },
    {
      "id": "github-mcp",
      "type": "data",
      "provider": "mcp",
      "config": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_TOKEN": "encrypted:..."}
      },
      "permissions": ["read", "write"],
      "agents": ["custom-code-agent"]
    },
    {
      "id": "whatsapp-personal",
      "type": "communication",
      "provider": "whatsapp-baileys",
      "config": {
        "phone_number": "+61...",
        "auth_state_path": "s3://user-state/whatsapp-auth/"
      },
      "permissions": ["send", "receive"],
      "agents": ["pa-agent", "reminder-agent"]
    }
  ]
}
```

### MCP Connection Flow

1. User configures channel in UI (URL/command + secrets)
2. Hive Core encrypts secrets with user's KMS key, stores in S3 state
3. On container boot, MCP Connection Pool reads channel configs
4. For each MCP channel: establishes connection (SSE or stdio), calls `tools/list`
5. Discovered tools registered into assigned agents' Strands tool sets
6. Agent calls MCP tools naturally — no difference from built-in tools

### Dynamic MCP Connection ("connect to this MCP" flow)

1. User says: "Connect to my company's MCP at https://internal.co/mcp, API key is xyz123"
2. Core intercepts (system/config intent, not routed to specialists)
3. Core creates channel config, encrypts secret, stores in state
4. MCP Pool establishes connection, discovers tools
5. Core asks: "Found 12 tools. Which agent should have access?"
6. User picks → tools injected into agent's Strands tool registry → immediately usable

### Communication Channels

- **Outbound:** Agent posts message to bus tagged with channel ID, Channel Manager delivers
- **Inbound:** Channel Manager polls/receives webhooks, posts to bus, Core routes to agent

### WhatsApp via Baileys

- Node.js sidecar runs Baileys socket within the container
- First-time: UI shows QR code, user scans with WhatsApp (linked device)
- Auth state persisted to S3 (survives container recycles)
- Incoming messages -> sidecar posts to Core via local HTTP
- Outbound -> Core sends to sidecar, calls `sock.sendMessage()`
- Note: Baileys is unofficial — caveat surfaced in UI during setup

---

## 4. Agent Configuration & Custom Agents

### Default Agent Roster

| Agent | Purpose | Default Tools | Default Channels |
|-------|---------|---------------|------------------|
| Personal Assistant | General tasks, email drafts, summaries, code writing/execution | code_executor, file_manager, web_search | All communication channels |
| Reminder Agent | Scheduling, alarms, follow-ups, recurring checks | cron_manager, notification_sender | All communication channels |
| Market Agent | Stock/crypto tracking, news summarization, portfolio alerts | web_search, data_analyzer | Market MCP channels |

### Agent Config Schema

```json
{
  "agents": [
    {
      "id": "pa-agent",
      "name": "Personal Assistant",
      "type": "default",
      "system_prompt": "You are a personal assistant...",
      "model": "global.anthropic.claude-sonnet-4-6-v1:0",
      "tools": ["code_executor", "file_manager", "web_search"],
      "channels": ["slack-personal", "whatsapp-personal"],
      "mcp_channels": [],
      "memory": {
        "enabled": true,
        "max_entries": 1000
      },
      "autonomy": "ask"
    }
  ]
}
```

### Autonomy Levels

- **ask** — agent asks user before taking actions
- **notify** — agent acts, then notifies user what it did
- **silent** — fully autonomous, user sees results in event log only

### Creating a Custom Agent (UI flow)

1. User clicks "Add Agent" in Hive dashboard
2. Fills in: name, purpose (becomes system prompt seed), model choice
3. Assigns channels (communication + data/MCP)
4. Sets autonomy level
5. Optionally provides example interactions or instructions
6. Hive Core generates full system prompt from seed, registers agent

### Code Execution (PA Agent)

```
User: "Write a script that pulls my top 5 holdings from the market MCP
       and formats a daily report"

PA Agent:
1. Writes Python script -> saves to user's workspace (S3 state)
2. Executes in sandboxed subprocess within container
3. Returns output to user
4. User says "run this every morning at 8am"
5. PA Agent registers cron job:
   {schedule: "0 8 * * *", action: "run_script",
    script: "daily_report.py", notify_via: "whatsapp-personal"}
```

### Agent-to-Agent Communication

Agents request help from each other via the message bus:

```
Market Agent: "I need to schedule a daily portfolio check"
  -> Posts to bus: {to: "reminder-agent", type: "create_reminder", payload: {...}}
Reminder Agent: Creates cron job, confirms back via bus
  -> Event Log captures the interaction -> UI shows it in the graph
```

---

## 5. State Persistence

Ephemeral compute, durable state. Container can die and come back; memory/scripts/schedules persist in S3.

### S3 Layout (per user)

```
s3://hive-state-{env}/
  users/
    {user_id}/
      config.json          # agent roster, channel configs
      secrets.enc          # encrypted credentials (KMS)
      memory/
        pa-agent.json      # per-agent conversation memory
        reminder-agent.json
        market-agent.json
      scripts/
        daily_report.py
        portfolio_check.py
      cron/
        jobs.json          # scheduled job definitions
      whatsapp-auth/       # Baileys session state
      event-log/
        2026-06-02.jsonl   # append-only event log (rotated daily)
```

### "Wipe Clean" = clear S3 state

User-triggered via UI "Reset Workspace" button. Clears all state for that user prefix.

---

## 6. Container Architecture

```
+-----------------------------------------------------+
|         AgentCore Runtime (ARM64 Docker)             |
|                                                     |
|  +-----------------------------------------+        |
|  |  Python Process: Hive Core              |        |
|  |  - Strands agents (Core + roster)       |        |
|  |  - Message bus (asyncio queues)         |        |
|  |  - Cron scheduler (APScheduler)         |        |
|  |  - MCP client connections               |        |
|  |  - WebSocket handler (user <-> UI)      |        |
|  |  - Code executor (subprocess sandbox)   |        |
|  +-----------------------------------------+        |
|                                                     |
|  +-----------------------------------------+        |
|  |  Node.js Sidecar: Channel Bridge        |        |
|  |  - Baileys (WhatsApp)                   |        |
|  |  - Slack RTM / webhook listener         |        |
|  |  - HTTP bridge to Python process        |        |
|  +-----------------------------------------+        |
|                                                     |
+-----------------------------------------------------+
```

### Container Lifecycle

1. User opens Hive UI -> WebSocket connect request
2. API GW triggers routing Lambda -> checks DynamoDB for existing container
3. If none: AgentCore spins up new container, registers in DynamoDB
4. Container boots -> loads state from S3 -> establishes MCP connections -> ready
5. User disconnects -> container stays warm for 15 min (configurable TTL)
6. TTL expires -> state flushed to S3 -> container terminates
7. Next connection -> fresh container, state reloaded from S3

---

## 7. UI & Live Agent Graph

### Main Layout

```
+-----------------------------------------------------------+
|  Hive                                    [Settings] [User] |
+------------+----------------------------------------------+
|            |                                              |
|  Sidebar   |          Main Area                          |
|            |                                              |
| +--------+ |  +--------------------------------------+   |
| |  Chat  | |  |                                      |   |
| +--------+ |  |     Live Agent Graph                 |   |
| | Agents | |  |     (animated node visualization)    |   |
| +--------+ |  |                                      |   |
| |Channels| |  +--------------------------------------+   |
| +--------+ |                                              |
| |  Jobs  | |  +--------------------------------------+   |
| +--------+ |  |     Chat / Interaction Panel         |   |
| |  Logs  | |  |     (conversation with agents)       |   |
| +--------+ |  +--------------------------------------+   |
|            |                                              |
+------------+----------------------------------------------+
```

### Live Agent Graph (Hero Feature)

- Built with React Flow (node-based, built-in animations)
- **Nodes** = agents (circle with avatar/icon, colored by status)
- **Center node** = Hive Core (router)
- **Edges** = messages between agents, animate when active (pulse/glow)
- **Channel nodes** = smaller periphery nodes (Slack/WhatsApp/MCP icons)
- Click any node -> opens that agent's conversation trace
- Real-time updates via WebSocket from Event Log

### Graph Visual States

| State | Visual |
|-------|--------|
| Agent idle | Grey node, no pulse |
| Agent thinking | Amber node, spinning indicator |
| Agent acting | Green node, edge lights up to target |
| Agent-to-agent | Edge animates between two agent nodes |
| Channel send | Edge animates from agent to channel node |
| Error | Red node, shake animation |

### Chat Panel

- Threaded conversation view
- Messages tagged with responding agent
- Inline code blocks for script outputs
- Expandable "thought process" sections
- File/artifact attachments

### Channel Configuration Screen

- Wizard-style: pick provider -> enter credentials -> test connection -> assign to agents
- MCP: shows discovered tools after connection
- WhatsApp: shows QR code for Baileys pairing
- Slack: OAuth flow or webhook URL
- Connection status indicator (green/red dot)

### Agent Configuration Screen

- Name, avatar, system prompt editor (AI-assisted from short description)
- Model selector dropdown
- Channel assignment checkboxes
- Autonomy level toggle
- "Test Agent" button

---

## 8. Infrastructure (CDK)

### Opt-in Deployment

```bash
# deploy.sh wizard
echo "Enable Hive (Multi-Agent Platform)? [y/N]"
read enable_hive
# Sets CDK context: -c hive_enabled=true/false
```

```python
# app.py
hive_enabled = self.node.try_get_context("hive_enabled") == "true"
if hive_enabled:
    hive_stack = HiveStack(app, f"srd-hive-{env}", ...)
```

### HiveStack Resources

- AgentCore Runtime definition (ARM64, 2GB RAM, 1 vCPU)
- Container scaling: 0 -> N based on active users
- API Gateway WebSocket (user <-> Hive Core)
- S3 bucket (hive-state) with per-user prefix policies
- KMS key (per-environment, user-scoped encryption context)
- Cognito integration (shared auth)
- DynamoDB table: user -> container mapping (TTL-based)
- CloudWatch logs per container

### What's Conditional (hive_enabled=true)

- Entire HiveStack
- WebSocket API GW route for Hive
- UI Hive section (hidden via `runtime-config.json` flag: `"hiveEnabled": true/false`)

### What's Always Deployed

- CloudFront + S3 UI (Hive pages lazy-loaded, hidden in nav if disabled)
- Cognito (shared auth)
- RAG stack (Document Chat works independently)

### Scaling & Cost

- Zero cost when no users active (containers scale to zero)
- ~$0.05/hour per active user container (ARM64, 2GB)
- S3 state: negligible (KB per user)
- KMS: $1/month per key + $0.03/10k requests

---

## 9. Security

- Each container runs with scoped IAM role (only access own user's S3 prefix)
- Code execution: subprocess with restricted permissions (no network unless explicitly granted)
- MCP secrets: encrypted at rest (single KMS key per environment, user-scoped encryption context for isolation), decrypted only in-memory during session
- Baileys auth: encrypted in S3, loaded only into Node.js sidecar
- Secrets stored in user's S3 state prefix, loaded into agent memory for session duration only

---

## 10. Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Framework | Strands Agents + Strands Graph |
| Agent Runtime | Bedrock AgentCore (ARM64 Docker) |
| MCP Client | `mcp` Python SDK (SSE + stdio transports) |
| Message Bus | Python `asyncio.Queue` (in-process) |
| Cron | APScheduler (persistent job store in S3) |
| Code Execution | `subprocess` with resource limits (ulimit) |
| Channel Bridge | Node.js sidecar (Baileys, Slack SDK) |
| IPC (Python <-> Node) | Local HTTP (FastAPI in Python, fetch in Node) |
| UI Framework | React + Cloudscape |
| Graph Visualization | React Flow |
| State Storage | S3 (per-user prefix) |
| Secrets | KMS encryption (per-env key, user-scoped context) |
| User Mapping | DynamoDB (user_id -> container_id, TTL) |
| Auth | Cognito (shared) |
| WebSocket | API Gateway WebSocket |
| Infra | CDK Python (HiveStack, opt-in) |
| Models | Claude Sonnet 4.6 (default), Opus 4.6 (power tasks) |

---

## 11. Boundaries

### Hive Owns

- Agent orchestration
- Channel connections (communication + MCP)
- State persistence (memory, scripts, cron, secrets)
- Code execution sandbox
- Cron scheduling
- Event logging
- Live graph UI

### Hive Does NOT Own

- Cognito (shared)
- CloudFront (shared)
- S3 UI bucket (shared)
- Bedrock model access (shared)
- RAG / Knowledge Base
- AOSS vectors
- Document upload flow

### Interaction with RAG Feature

- Hive agents CAN query Bedrock Knowledge Base (built-in tool)
- RAG/Document Chat remains standalone (works without Hive)
- No circular dependencies between stacks

---

## 12. Out of Scope (v1)

- Multi-user collaboration (agents shared between users)
- Agent marketplace / sharing configs
- Voice channels
- Self-hosted LLM support (Bedrock only)
- Mobile app (web only)
