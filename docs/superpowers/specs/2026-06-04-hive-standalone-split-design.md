# Hive Standalone Project — Design Spec

**Date:** 2026-06-04
**Status:** Draft
**Branch:** feature/hive-multi-agent (source)
**Target:** New repo `hive` (fresh start, no history carried)

---

## Goal

Extract Hive from `serverless-rag-demo` into a standalone open-source project that others can clone and deploy to their own AWS account. Developer-focused, README-driven, single `deploy.sh` command.

## Decisions

| Decision | Choice |
|----------|--------|
| Project name | Hive |
| Target audience | Developers (clone + deploy) |
| Repo structure | Monorepo (backend + UI + infra) |
| Extraction method | Fresh repo, copy code (no history) |
| Compute platform | AgentCore only |
| Channels | WhatsApp + Slack + MCP (all three) |
| Auth | Own Cognito User Pool + Identity Pool |
| Default model | `global.anthropic.claude-sonnet-4-6-v1` |
| License | Apache 2.0 |

---

## Repository Structure

```
hive/
├── README.md
├── LICENSE
├── deploy.sh                  # Single entry: deploy, update, destroy
├── config.yaml                # User config (region, stage, model, etc.)
├── cdk.json
├── app.py                     # CDK app entry
├── requirements.txt           # CDK dependencies
├── infrastructure/
│   └── hive_stack.py          # Single stack: Cognito, S3, KMS, CloudFront, IAM
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py                 # FastAPI + WebSocket server
│   ├── hive_core/
│   │   ├── __init__.py
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── pa.py
│   │   │   ├── reminder.py
│   │   │   └── market.py
│   │   ├── channels/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── whatsapp.py
│   │   │   ├── slack.py
│   │   │   └── mcp.py
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── channel_send.py
│   │   │   └── mcp_bridge.py
│   │   ├── bus.py
│   │   ├── config.py
│   │   ├── event_log.py
│   │   ├── guardrails.py
│   │   ├── registry.py
│   │   ├── router.py
│   │   ├── scheduler.py
│   │   └── state.py
│   └── sidecar/
│       ├── index.js
│       ├── package.json
│       └── package-lock.json
├── ui/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── common/
│       │   └── hive-ws.ts
│       ├── components/
│       │   ├── chat-panel.tsx
│       │   ├── channel-config-panel.tsx
│       │   ├── channel-message-feed.tsx
│       │   ├── guardrails-editor.tsx
│       │   ├── hive-layout.tsx
│       │   ├── job-viewer.tsx
│       │   ├── persona-editor.tsx
│       │   ├── session-panel.tsx
│       │   ├── types.ts
│       │   └── wa-qr-modal.tsx
│       └── auth/
│           └── amplify-auth.ts
└── docs/
    ├── architecture.md
    ├── channels.md
    ├── guardrails.md
    └── adding-agents.md
```

---

## Infrastructure (Single CDK Stack)

The `hive_stack.py` creates everything needed:

1. **Cognito User Pool** — Email/password signup, no hosted UI (Amplify SDK handles login in the React app)
2. **Cognito Identity Pool** — Authenticated role with permission to invoke the AgentCore endpoint (SigV4)
3. **S3 State Bucket** — `hive-state-{account}-{region}` for session persistence (config, auth, events)
4. **KMS Key** — Encrypts sensitive state (WhatsApp auth tokens, channel secrets)
5. **S3 UI Bucket + CloudFront** — Hosts the built React app
6. **IAM Role for AgentCore** — Permissions for Bedrock model invocation, S3, KMS, ECR

The CDK stack does NOT create the AgentCore runtime (imperative API, handled by `deploy.sh`).

---

## Deploy Script (`deploy.sh`)

Interactive wizard flow:

```
1. Check prerequisites (AWS CLI, CDK, Docker, Node.js)
2. Prompt for: region, stage name (default: "prod")
3. Read/create config.yaml
4. CDK deploy (creates Cognito, S3, KMS, CloudFront, IAM)
5. Docker build + ECR push (backend container)
6. AgentCore create-or-update runtime
   - lifecycle: 4hr idle / 8hr max
   - env vars: HIVE_STATE_BUCKET, HIVE_KMS_KEY_ID
7. AgentCore create endpoint (if new)
8. UI build (npm install + vite build)
9. Generate runtime-config.json (Cognito IDs, AgentCore endpoint URL)
10. S3 sync UI + CloudFront invalidation
11. Print: UI URL, runtime ID, status
```

Supports `./deploy.sh destroy` to tear down.

---

## Authentication Flow

1. User opens CloudFront URL → React app loads
2. Amplify SDK presents login form (email + password)
3. On auth success, Amplify gets Cognito tokens → exchanges for Identity Pool credentials (temporary AWS SigV4 creds)
4. UI uses SigV4 creds to open WebSocket to AgentCore endpoint
5. AgentCore authenticates the request via IAM policy on the Identity Pool role

No API Gateway or custom auth layer needed — AgentCore's native SigV4 auth handles it.

---

## Genericization

| Current (personal) | Standalone |
|---|---|
| `"I'm not able to do that on Fraser's behalf."` | `"I'm not authorized to do that."` (configurable in UI) |
| `srd-*` naming | `hive-{stage}-*` |
| Hardcoded model `us.anthropic.claude-sonnet-4-6-v1` | Default `global.anthropic.claude-sonnet-4-6-v1`, configurable per-agent in UI |
| PA prompt with personal context | Generic PA prompt, persona set via UI |
| Shared Cognito from RAG demo | Own Cognito in stack |
| Shared CloudFront | Own CloudFront in stack |
| `environment_name` CDK context | `stage` parameter in config.yaml |

---

## Model Configuration

- Default: `global.anthropic.claude-sonnet-4-6-v1`
- Configurable per-agent via UI (Session tab → agent Actions → Edit Model)
- Also settable in `config.yaml` as `default_model` for initial deploy
- Backend stores model choice in agent state; persists across container restarts

---

## Channels (All Three)

### WhatsApp
- Baileys sidecar (Node.js, runs inside the same container on :3001)
- QR code pairing via UI modal
- S3-persisted auth state (survives container restarts)
- LID↔phone mapping, contact name resolution

### Slack
- Slack Bot Token + App Token (Socket Mode)
- Configured via UI channel panel
- No sidecar needed (direct Slack SDK in Python)

### MCP
- Connects to external MCP servers (configured via UI)
- Request/response mapped to channel_outgoing/channel_incoming events
- Tools bridged into Strands agents

---

## What Ships

- Multi-agent framework (PA, Reminder, Market + custom agents via UI)
- All 3 channels (WhatsApp, Slack, MCP)
- Guardrails (tier-based per-sender enforcement)
- Persona system (UI-editable, injected into agent prompts)
- Job scheduler (APScheduler, reminders, recurring tasks)
- Session panel (agent lifecycle: stop/start/restart, edit prompt, edit model)
- Channel message feed (real-time, provider badges)
- WebSocket-based reactive UI (Cloudscape components)
- AgentCore lifecycle config (4hr idle, 8hr max)

## What Gets Dropped

- All RAG/KB/AOSS/indexing code
- Document chat, sentiment, OCR, PII pages
- Multi-stack CDK app (5+ stacks)
- CodeBuild CI/CD pipeline
- Shared Cognito and CloudFront references
- `srd-*` naming
- All non-Hive UI routes and components

---

## What's New (doesn't exist yet)

- `config.yaml` — user configuration file
- Standalone `deploy.sh` wizard with prerequisite checks
- Own Cognito stack (User Pool + Identity Pool + IAM roles)
- Own CloudFront + S3 for UI
- `ui/src/auth/amplify-auth.ts` — login/signup flow
- `README.md` — quickstart, prerequisites, architecture overview
- `docs/` — architecture, channels, guardrails, adding-agents guides

---

## Out of Scope

- Multi-user / multi-tenant (single user per deployment)
- CI/CD pipeline (users deploy manually via `deploy.sh`)
- Custom domain / Route53 setup
- Billing alerts or cost controls
- Mobile app
- Migration tooling from serverless-rag-demo
