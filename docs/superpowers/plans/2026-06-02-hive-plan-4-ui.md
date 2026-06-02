# Hive Plan 4: UI & Live Agent Graph

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Hive UI with React + Cloudscape: live agent graph (React Flow), channel configuration wizard, agent management, job viewer, and chat panel with agent attribution.

**Architecture:** New `/hive` route in the existing React app. Conditionally rendered based on `runtime-config.json` `hiveEnabled` flag. WebSocket connection to Hive container streams events that power the live graph. React Flow renders agent nodes with animated edges.

**Tech Stack:** React 18, Cloudscape, React Flow, react-use-websocket (already installed), TypeScript

**Depends on:** Plan 1 (container WebSocket), Plan 2 (agent system), Plan 3 (channels)

---

## File Structure

```
artifacts/chat-ui/src/pages/hive-page.tsx                    — Hive main page (layout container)
artifacts/chat-ui/src/components/hive/hive-layout.tsx         — Main layout (graph + chat split)
artifacts/chat-ui/src/components/hive/agent-graph.tsx          — React Flow live agent graph
artifacts/chat-ui/src/components/hive/agent-graph-nodes.tsx    — Custom node components
artifacts/chat-ui/src/components/hive/chat-panel.tsx           — Chat panel with agent attribution
artifacts/chat-ui/src/components/hive/channel-config.tsx       — Channel configuration wizard
artifacts/chat-ui/src/components/hive/agent-config.tsx         — Agent management panel
artifacts/chat-ui/src/components/hive/job-viewer.tsx           — Cron job viewer
artifacts/chat-ui/src/components/hive/types.ts                 — TypeScript types for Hive
artifacts/chat-ui/src/common/hive-ws.ts                        — Hive WebSocket helper
artifacts/chat-ui/src/app.tsx                                  — Modified: add /hive route
artifacts/chat-ui/package.json                                 — Modified: add reactflow dependency
```

---

### Task 1: TypeScript Types & WebSocket Helper

**Files:**
- Create: `artifacts/chat-ui/src/components/hive/types.ts`
- Create: `artifacts/chat-ui/src/common/hive-ws.ts`

- [ ] **Step 1: Define Hive TypeScript types**

```typescript
// artifacts/chat-ui/src/components/hive/types.ts

export interface AgentConfig {
    id: string;
    name: string;
    type: "default" | "custom";
    system_prompt: string;
    model: string;
    tools: string[];
    channels: string[];
    mcp_channels: string[];
    autonomy: "ask" | "notify" | "silent";
}

export interface ChannelConfig {
    id: string;
    type: "communication" | "data";
    provider: string;
    config: Record<string, string>;
    permissions: string[];
    agents: string[];
}

export interface HiveConfig {
    agents: AgentConfig[];
    channels: ChannelConfig[];
}

export interface HiveEvent {
    timestamp: number;
    agent: string;
    event: string;
    data: Record<string, any>;
}

export interface CronJob {
    id: string;
    name: string;
    schedule: string;
    action: string;
    payload: Record<string, any>;
    agent_id: string;
    notify_channel: string;
}

export type AgentStatus = "idle" | "thinking" | "acting" | "error";

export interface AgentNodeData {
    id: string;
    name: string;
    status: AgentStatus;
    lastEvent?: HiveEvent;
}

export interface ChannelNodeData {
    id: string;
    provider: string;
    type: "communication" | "data";
    status: "connected" | "disconnected";
}

export type HiveMessage =
    | { type: "init"; user_id: string }
    | { type: "chat"; query: string }
    | { type: "get_events"; count?: number }
    | { type: "get_config" }
    | { type: "add_channel"; channel: ChannelConfig }
    | { type: "remove_channel"; channel_id: string }
    | { type: "list_channels" }
    | { type: "wipe" };

export type HiveResponse =
    | { type: "init_complete"; config: HiveConfig }
    | { type: "routed"; target: string }
    | { type: "response"; data: Record<string, any> }
    | { type: "events"; events: HiveEvent[] }
    | { type: "config"; config: HiveConfig }
    | { type: "channel_added"; channel_id: string }
    | { type: "channel_removed"; channel_id: string }
    | { type: "channels"; channels: any[] }
    | { type: "wiped" }
    | { type: "error"; message: string }
    | { type: "ack"; message: string };
```

- [ ] **Step 2: Create Hive WebSocket helper**

```typescript
// artifacts/chat-ui/src/common/hive-ws.ts
import { getAwsCredentials } from "./agentcore-ws";
import { getRuntimeConfig } from "../runtime-config";
import { SignatureV4 } from "@smithy/signature-v4";
import { HttpRequest } from "@smithy/protocol-http";
import { Sha256 } from "@aws-crypto/sha256-js";
import { HiveMessage, HiveResponse } from "../components/hive/types";

export type HiveMessageHandler = (msg: HiveResponse) => void;

let hiveSocket: WebSocket | null = null;

async function presignHiveWebSocketUrl(idToken: string): Promise<string> {
    const config = getRuntimeConfig();
    const region = config.cognitoRegion;
    const runtimeArn = config.hiveRuntimeArn!;
    const credentials = await getAwsCredentials(idToken);

    const host = `bedrock-agentcore.${region}.amazonaws.com`;
    const encodedArn = encodeURIComponent(runtimeArn);
    const sessionId = crypto.randomUUID();

    const url = new URL(`https://${host}/runtimes/${encodedArn}/ws`);
    url.searchParams.set("qualifier", "DEFAULT");
    url.searchParams.set("X-Amzn-Bedrock-AgentCore-Runtime-Session-Id", sessionId);

    const request = new HttpRequest({
        method: "GET",
        protocol: "https:",
        hostname: host,
        path: `/runtimes/${encodedArn}/ws`,
        query: Object.fromEntries(url.searchParams.entries()),
        headers: { host },
    });

    const signer = new SignatureV4({
        service: "bedrock-agentcore",
        region,
        credentials: {
            accessKeyId: credentials.accessKeyId,
            secretAccessKey: credentials.secretAccessKey,
            sessionToken: credentials.sessionToken,
        },
        sha256: Sha256,
    });

    const presigned = await signer.presign(request, { expiresIn: 3600 });
    const signedParams = new URLSearchParams();
    for (const [key, value] of Object.entries(presigned.query || {})) {
        signedParams.set(key, value as string);
    }

    return `wss://${host}${presigned.path}?${signedParams.toString()}`;
}

export async function connectHive(
    idToken: string,
    userId: string,
    onMessage: HiveMessageHandler,
    onError: (error: string) => void,
    onClose: () => void,
): Promise<WebSocket> {
    const wsUrl = await presignHiveWebSocketUrl(idToken);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        // Send init message
        sendHiveMessage(ws, { type: "init", user_id: userId });
    };

    ws.onmessage = (event) => {
        try {
            const msg: HiveResponse = JSON.parse(event.data);
            onMessage(msg);
        } catch {
            onMessage({ type: "error", message: "Failed to parse message" });
        }
    };

    ws.onerror = () => onError("Hive WebSocket error");
    ws.onclose = onClose;

    hiveSocket = ws;
    return ws;
}

export function sendHiveMessage(ws: WebSocket, message: HiveMessage) {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(message));
    }
}

export function getHiveSocket(): WebSocket | null {
    return hiveSocket;
}
```

- [ ] **Step 3: Commit**

```bash
git add artifacts/chat-ui/src/components/hive/types.ts artifacts/chat-ui/src/common/hive-ws.ts
git commit -m "feat(hive-ui): add TypeScript types and WebSocket helper"
```

---

### Task 2: Install React Flow & Add Route

**Files:**
- Modify: `artifacts/chat-ui/package.json`
- Modify: `artifacts/chat-ui/src/app.tsx`
- Create: `artifacts/chat-ui/src/pages/hive-page.tsx`

- [ ] **Step 1: Add reactflow to package.json dependencies**

Add to `dependencies` in `artifacts/chat-ui/package.json`:
```json
"@xyflow/react": "^12.4.0"
```

- [ ] **Step 2: Install dependency**

Run: `cd artifacts/chat-ui && npm install`

- [ ] **Step 3: Create Hive page shell**

```typescript
// artifacts/chat-ui/src/pages/hive-page.tsx
import { useState, useEffect } from "react";
import { withAuthenticator } from "@aws-amplify/ui-react";
import { ContentLayout, Header } from "@cloudscape-design/components";
import { AuthHelper } from "../common/helpers/auth-help";
import { AppPage } from "../common/types";
import { HiveLayout } from "../components/hive/hive-layout";

function HivePage(props: AppPage) {
    useEffect(() => {
        const init = async () => {
            const userdata = await AuthHelper.getUserDetails();
            props.setAppData({ userinfo: userdata });
        };
        init();
    }, []);

    return (
        <ContentLayout
            defaultPadding
            headerVariant="high-contrast"
            header={
                <Header
                    variant="h1"
                    description="Your personal AI agent swarm with channels, tools, and autonomous capabilities"
                >
                    Hive
                </Header>
            }
        >
            <HiveLayout />
        </ContentLayout>
    );
}

export default withAuthenticator(HivePage);
```

- [ ] **Step 4: Add route to app.tsx**

In `artifacts/chat-ui/src/app.tsx`, add import:
```typescript
import HivePage from './pages/hive-page';
```

Add to `SideNavigation` items (after Multi-Agent):
```typescript
{ type: "link", text: "Hive", href: "#/hive" },
```

Add to `Routes`:
```typescript
<Route path="/hive" element={<HivePage setAppData={setAppData} />} />
```

Add to tools panel `Routes`:
```typescript
<Route path="/hive" element={<Help setPageId="hive" />} />
```

Wrap the Hive nav item conditionally based on `hiveEnabled` from runtime config (read at app load time).

- [ ] **Step 5: Commit**

```bash
git add artifacts/chat-ui/package.json artifacts/chat-ui/src/pages/hive-page.tsx artifacts/chat-ui/src/app.tsx
git commit -m "feat(hive-ui): add /hive route and page shell"
```

---

### Task 3: Live Agent Graph

**Files:**
- Create: `artifacts/chat-ui/src/components/hive/agent-graph.tsx`
- Create: `artifacts/chat-ui/src/components/hive/agent-graph-nodes.tsx`

- [ ] **Step 1: Create custom node components**

```typescript
// artifacts/chat-ui/src/components/hive/agent-graph-nodes.tsx
import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { AgentStatus } from "./types";

interface AgentNodeProps {
    data: {
        label: string;
        status: AgentStatus;
        isCore?: boolean;
    };
}

export const AgentNode = memo(({ data }: AgentNodeProps) => {
    const statusColors: Record<AgentStatus, string> = {
        idle: "#8c8c8c",
        thinking: "#f0a30a",
        acting: "#1d8102",
        error: "#d13212",
    };

    const size = data.isCore ? 80 : 60;
    const color = statusColors[data.status];

    return (
        <div
            style={{
                width: size,
                height: size,
                borderRadius: "50%",
                background: `radial-gradient(circle, ${color}33, ${color}11)`,
                border: `3px solid ${color}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexDirection: "column",
                cursor: "pointer",
                animation: data.status === "thinking" ? "pulse 1.5s infinite" : undefined,
            }}
        >
            <Handle type="target" position={Position.Top} style={{ visibility: "hidden" }} />
            <span style={{ fontSize: 10, fontWeight: 600, textAlign: "center", padding: 4 }}>
                {data.label}
            </span>
            {data.status !== "idle" && (
                <span style={{ fontSize: 8, color }}>{data.status}</span>
            )}
            <Handle type="source" position={Position.Bottom} style={{ visibility: "hidden" }} />
        </div>
    );
});

interface ChannelNodeProps {
    data: {
        label: string;
        provider: string;
        connected: boolean;
    };
}

export const ChannelNode = memo(({ data }: ChannelNodeProps) => {
    const providerIcons: Record<string, string> = {
        slack: "💬",
        "whatsapp-baileys": "📱",
        mcp: "🔌",
    };

    return (
        <div
            style={{
                width: 44,
                height: 44,
                borderRadius: "50%",
                background: data.connected ? "#1d810211" : "#d1321211",
                border: `2px solid ${data.connected ? "#1d8102" : "#d13212"}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexDirection: "column",
                fontSize: 10,
            }}
        >
            <Handle type="target" position={Position.Top} style={{ visibility: "hidden" }} />
            <span style={{ fontSize: 16 }}>{providerIcons[data.provider] || "⚡"}</span>
            <span style={{ fontSize: 8 }}>{data.label}</span>
            <Handle type="source" position={Position.Bottom} style={{ visibility: "hidden" }} />
        </div>
    );
});
```

- [ ] **Step 2: Create the Agent Graph component**

```typescript
// artifacts/chat-ui/src/components/hive/agent-graph.tsx
import { useMemo, useCallback } from "react";
import {
    ReactFlow,
    Background,
    Controls,
    useNodesState,
    useEdgesState,
    Node,
    Edge,
    MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AgentNode, ChannelNode } from "./agent-graph-nodes";
import { HiveConfig, HiveEvent, AgentStatus } from "./types";

const nodeTypes = {
    agent: AgentNode,
    channel: ChannelNode,
};

interface AgentGraphProps {
    config: HiveConfig | null;
    events: HiveEvent[];
    activeAgent: string | null;
    onNodeClick: (agentId: string) => void;
}

export function AgentGraph({ config, events, activeAgent, onNodeClick }: AgentGraphProps) {
    const { nodes, edges } = useMemo(() => {
        if (!config) return { nodes: [], edges: [] };

        const agentNodes: Node[] = [];
        const channelNodes: Node[] = [];
        const edgeList: Edge[] = [];

        // Core node at center
        agentNodes.push({
            id: "core",
            type: "agent",
            position: { x: 250, y: 200 },
            data: { label: "Hive Core", status: getAgentStatus("router", events), isCore: true },
        });

        // Agent nodes in a circle around core
        const agentCount = config.agents.length;
        const radius = 150;
        config.agents.forEach((agent, i) => {
            const angle = (2 * Math.PI * i) / agentCount - Math.PI / 2;
            const x = 250 + radius * Math.cos(angle);
            const y = 200 + radius * Math.sin(angle);

            agentNodes.push({
                id: agent.id,
                type: "agent",
                position: { x, y },
                data: {
                    label: agent.name,
                    status: getAgentStatus(agent.id, events),
                },
            });

            // Edge from core to agent
            edgeList.push({
                id: `core-${agent.id}`,
                source: "core",
                target: agent.id,
                animated: activeAgent === agent.id,
                style: { stroke: activeAgent === agent.id ? "#1d8102" : "#8c8c8c" },
                markerEnd: { type: MarkerType.ArrowClosed },
            });
        });

        // Channel nodes on outer ring
        const channelCount = config.channels.length;
        const channelRadius = 280;
        config.channels.forEach((channel, i) => {
            const angle = (2 * Math.PI * i) / Math.max(channelCount, 1);
            const x = 250 + channelRadius * Math.cos(angle);
            const y = 200 + channelRadius * Math.sin(angle);

            channelNodes.push({
                id: `ch-${channel.id}`,
                type: "channel",
                position: { x, y },
                data: {
                    label: channel.id.split("-")[0],
                    provider: channel.provider,
                    connected: true,
                },
            });

            // Connect channels to their assigned agents
            channel.agents.forEach((agentId) => {
                edgeList.push({
                    id: `ch-${channel.id}-${agentId}`,
                    source: agentId,
                    target: `ch-${channel.id}`,
                    style: { stroke: "#8c8c8c", strokeDasharray: "4 4" },
                });
            });
        });

        return { nodes: [...agentNodes, ...channelNodes], edges: edgeList };
    }, [config, events, activeAgent]);

    const [flowNodes, setNodes, onNodesChange] = useNodesState(nodes);
    const [flowEdges, setEdges, onEdgesChange] = useEdgesState(edges);

    // Update nodes when props change
    useMemo(() => {
        setNodes(nodes);
        setEdges(edges);
    }, [nodes, edges]);

    const handleNodeClick = useCallback((_: any, node: Node) => {
        if (node.type === "agent" && node.id !== "core") {
            onNodeClick(node.id);
        }
    }, [onNodeClick]);

    return (
        <div style={{ width: "100%", height: 400 }}>
            <ReactFlow
                nodes={flowNodes}
                edges={flowEdges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={handleNodeClick}
                nodeTypes={nodeTypes}
                fitView
                proOptions={{ hideAttribution: true }}
            >
                <Background />
                <Controls />
            </ReactFlow>
        </div>
    );
}

function getAgentStatus(agentId: string, events: HiveEvent[]): AgentStatus {
    // Find last event for this agent
    const agentEvents = events.filter((e) => e.agent === agentId);
    if (agentEvents.length === 0) return "idle";

    const last = agentEvents[agentEvents.length - 1];
    if (last.event === "error") return "error";
    if (last.event === "received" || last.event === "thinking") return "thinking";
    if (last.event === "responded" || last.event === "acting") return "acting";
    return "idle";
}
```

- [ ] **Step 3: Commit**

```bash
git add artifacts/chat-ui/src/components/hive/agent-graph.tsx artifacts/chat-ui/src/components/hive/agent-graph-nodes.tsx
git commit -m "feat(hive-ui): add React Flow live agent graph with custom nodes"
```

---

### Task 4: Chat Panel

**Files:**
- Create: `artifacts/chat-ui/src/components/hive/chat-panel.tsx`

- [ ] **Step 1: Implement chat panel with agent attribution**

```typescript
// artifacts/chat-ui/src/components/hive/chat-panel.tsx
import { useState, useRef, useEffect } from "react";
import {
    Container,
    SpaceBetween,
    Button,
    Textarea,
    Box,
    Badge,
    ExpandableSection,
} from "@cloudscape-design/components";

interface ChatMessage {
    id: string;
    role: "user" | "agent" | "system";
    content: string;
    agent_id?: string;
    agent_name?: string;
    timestamp: number;
    thinking?: string;
}

interface ChatPanelProps {
    messages: ChatMessage[];
    onSend: (message: string) => void;
    isLoading: boolean;
    activeAgent: string | null;
}

export function ChatPanel({ messages, onSend, isLoading, activeAgent }: ChatPanelProps) {
    const [input, setInput] = useState("");
    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const handleSend = () => {
        if (!input.trim() || isLoading) return;
        onSend(input.trim());
        setInput("");
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <Container>
            <SpaceBetween size="s">
                {/* Messages */}
                <div style={{ maxHeight: 400, overflowY: "auto", padding: "8px 0" }}>
                    {messages.map((msg) => (
                        <div
                            key={msg.id}
                            style={{
                                marginBottom: 12,
                                padding: "8px 12px",
                                borderRadius: 8,
                                background: msg.role === "user" ? "#0972d311" : "#f2f3f3",
                            }}
                        >
                            <Box>
                                <SpaceBetween size="xxs" direction="horizontal">
                                    <Box fontWeight="bold" fontSize="body-s">
                                        {msg.role === "user" ? "You" : msg.agent_name || "System"}
                                    </Box>
                                    {msg.agent_id && (
                                        <Badge color="blue">{msg.agent_id}</Badge>
                                    )}
                                </SpaceBetween>
                            </Box>
                            <Box variant="p" margin={{ top: "xxs" }}>
                                {msg.content}
                            </Box>
                            {msg.thinking && (
                                <ExpandableSection headerText="Thought process" variant="footer">
                                    <Box variant="code" fontSize="body-s">
                                        {msg.thinking}
                                    </Box>
                                </ExpandableSection>
                            )}
                        </div>
                    ))}
                    {isLoading && activeAgent && (
                        <div style={{ padding: "8px 12px", color: "#5f6b7a" }}>
                            <Badge color="green">{activeAgent}</Badge> is thinking...
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                {/* Input */}
                <div style={{ display: "flex", gap: 8 }}>
                    <div style={{ flex: 1 }}>
                        <Textarea
                            value={input}
                            onChange={({ detail }) => setInput(detail.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Message your agents..."
                            rows={2}
                            disabled={isLoading}
                        />
                    </div>
                    <Button
                        variant="primary"
                        onClick={handleSend}
                        disabled={!input.trim() || isLoading}
                        iconName="send"
                    >
                        Send
                    </Button>
                </div>
            </SpaceBetween>
        </Container>
    );
}
```

- [ ] **Step 2: Commit**

```bash
git add artifacts/chat-ui/src/components/hive/chat-panel.tsx
git commit -m "feat(hive-ui): add chat panel with agent attribution and thought process"
```

---

### Task 5: Channel Configuration Wizard

**Files:**
- Create: `artifacts/chat-ui/src/components/hive/channel-config.tsx`

- [ ] **Step 1: Implement channel configuration wizard**

```typescript
// artifacts/chat-ui/src/components/hive/channel-config.tsx
import { useState } from "react";
import {
    Wizard,
    FormField,
    Input,
    Select,
    Multiselect,
    Container,
    Header,
    SpaceBetween,
    Alert,
    StatusIndicator,
    Toggle,
} from "@cloudscape-design/components";
import { ChannelConfig, AgentConfig } from "./types";

interface ChannelConfigProps {
    agents: AgentConfig[];
    onSave: (config: ChannelConfig) => void;
    onCancel: () => void;
}

const PROVIDERS = [
    { label: "Slack", value: "slack" },
    { label: "WhatsApp (Baileys)", value: "whatsapp-baileys" },
    { label: "MCP Server (SSE)", value: "mcp-sse" },
    { label: "MCP Server (stdio)", value: "mcp-stdio" },
];

export function ChannelConfigWizard({ agents, onSave, onCancel }: ChannelConfigProps) {
    const [provider, setProvider] = useState<string>("");
    const [channelId, setChannelId] = useState("");
    const [config, setConfig] = useState<Record<string, string>>({});
    const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
    const [permissions, setPermissions] = useState<string[]>(["read"]);

    const handleSubmit = () => {
        const channelType = provider.startsWith("mcp") ? "data" : "communication";
        const actualProvider = provider === "mcp-sse" || provider === "mcp-stdio" ? "mcp" : provider;

        const channelConfig: ChannelConfig = {
            id: channelId,
            type: channelType,
            provider: actualProvider,
            config: {
                ...config,
                ...(provider === "mcp-sse" ? { transport: "sse" } : {}),
                ...(provider === "mcp-stdio" ? { transport: "stdio" } : {}),
            },
            permissions,
            agents: selectedAgents,
        };
        onSave(channelConfig);
    };

    const renderProviderFields = () => {
        switch (provider) {
            case "slack":
                return (
                    <SpaceBetween size="m">
                        <FormField label="Webhook URL">
                            <Input
                                value={config.webhook_url || ""}
                                onChange={({ detail }) => setConfig({ ...config, webhook_url: detail.value })}
                                placeholder="https://hooks.slack.com/services/..."
                                type="password"
                            />
                        </FormField>
                        <FormField label="Default Channel">
                            <Input
                                value={config.default_channel || ""}
                                onChange={({ detail }) => setConfig({ ...config, default_channel: detail.value })}
                                placeholder="#general"
                            />
                        </FormField>
                    </SpaceBetween>
                );
            case "whatsapp-baileys":
                return (
                    <SpaceBetween size="m">
                        <FormField label="Phone Number">
                            <Input
                                value={config.phone_number || ""}
                                onChange={({ detail }) => setConfig({ ...config, phone_number: detail.value })}
                                placeholder="+61..."
                            />
                        </FormField>
                        <Alert type="info">
                            After saving, you'll need to scan a QR code with your WhatsApp to link the device.
                            Note: Baileys is unofficial — WhatsApp may break compatibility.
                        </Alert>
                    </SpaceBetween>
                );
            case "mcp-sse":
                return (
                    <SpaceBetween size="m">
                        <FormField label="MCP Server URL">
                            <Input
                                value={config.url || ""}
                                onChange={({ detail }) => setConfig({ ...config, url: detail.value })}
                                placeholder="https://your-mcp-server.com/mcp"
                            />
                        </FormField>
                        <FormField label="API Key (optional)">
                            <Input
                                value={config.api_key || ""}
                                onChange={({ detail }) => setConfig({ ...config, api_key: detail.value })}
                                type="password"
                            />
                        </FormField>
                    </SpaceBetween>
                );
            case "mcp-stdio":
                return (
                    <SpaceBetween size="m">
                        <FormField label="Command">
                            <Input
                                value={config.command || ""}
                                onChange={({ detail }) => setConfig({ ...config, command: detail.value })}
                                placeholder="npx"
                            />
                        </FormField>
                        <FormField label="Arguments (comma-separated)">
                            <Input
                                value={config.args || ""}
                                onChange={({ detail }) => setConfig({ ...config, args: detail.value })}
                                placeholder="-y, @modelcontextprotocol/server-github"
                            />
                        </FormField>
                        <FormField label="Environment Variables (KEY=VALUE, one per line)">
                            <Input
                                value={config.env || ""}
                                onChange={({ detail }) => setConfig({ ...config, env: detail.value })}
                                placeholder="GITHUB_TOKEN=ghp_xxx"
                                type="password"
                            />
                        </FormField>
                    </SpaceBetween>
                );
            default:
                return null;
        }
    };

    return (
        <Wizard
            onCancel={onCancel}
            onSubmit={handleSubmit}
            steps={[
                {
                    title: "Choose Provider",
                    content: (
                        <Container header={<Header variant="h3">Channel Provider</Header>}>
                            <SpaceBetween size="m">
                                <FormField label="Channel ID">
                                    <Input
                                        value={channelId}
                                        onChange={({ detail }) => setChannelId(detail.value)}
                                        placeholder="my-slack-channel"
                                    />
                                </FormField>
                                <FormField label="Provider">
                                    <Select
                                        selectedOption={PROVIDERS.find((p) => p.value === provider) || null}
                                        onChange={({ detail }) => setProvider(detail.selectedOption?.value || "")}
                                        options={PROVIDERS}
                                        placeholder="Select provider..."
                                    />
                                </FormField>
                            </SpaceBetween>
                        </Container>
                    ),
                },
                {
                    title: "Configure",
                    content: (
                        <Container header={<Header variant="h3">Connection Details</Header>}>
                            {renderProviderFields()}
                        </Container>
                    ),
                },
                {
                    title: "Assign Agents",
                    content: (
                        <Container header={<Header variant="h3">Agent Access</Header>}>
                            <SpaceBetween size="m">
                                <FormField label="Which agents can use this channel?">
                                    <Multiselect
                                        selectedOptions={agents
                                            .filter((a) => selectedAgents.includes(a.id))
                                            .map((a) => ({ label: a.name, value: a.id }))}
                                        onChange={({ detail }) =>
                                            setSelectedAgents(
                                                detail.selectedOptions.map((o) => o.value!)
                                            )
                                        }
                                        options={agents.map((a) => ({ label: a.name, value: a.id }))}
                                        placeholder="Select agents..."
                                    />
                                </FormField>
                                <FormField label="Permissions">
                                    <SpaceBetween size="s" direction="horizontal">
                                        <Toggle
                                            checked={permissions.includes("read")}
                                            onChange={({ detail }) => {
                                                if (detail.checked) setPermissions([...permissions, "read"]);
                                                else setPermissions(permissions.filter((p) => p !== "read"));
                                            }}
                                        >
                                            Read
                                        </Toggle>
                                        <Toggle
                                            checked={permissions.includes("write") || permissions.includes("send")}
                                            onChange={({ detail }) => {
                                                const perm = provider.startsWith("mcp") ? "write" : "send";
                                                if (detail.checked) setPermissions([...permissions, perm]);
                                                else setPermissions(permissions.filter((p) => p !== perm && p !== "write" && p !== "send"));
                                            }}
                                        >
                                            {provider.startsWith("mcp") ? "Write" : "Send"}
                                        </Toggle>
                                    </SpaceBetween>
                                </FormField>
                            </SpaceBetween>
                        </Container>
                    ),
                },
            ]}
        />
    );
}
```

- [ ] **Step 2: Commit**

```bash
git add artifacts/chat-ui/src/components/hive/channel-config.tsx
git commit -m "feat(hive-ui): add channel configuration wizard"
```

---

### Task 6: Agent Configuration & Job Viewer

**Files:**
- Create: `artifacts/chat-ui/src/components/hive/agent-config.tsx`
- Create: `artifacts/chat-ui/src/components/hive/job-viewer.tsx`

- [ ] **Step 1: Create agent configuration panel**

```typescript
// artifacts/chat-ui/src/components/hive/agent-config.tsx
import { useState } from "react";
import {
    Container,
    Header,
    SpaceBetween,
    Button,
    FormField,
    Input,
    Select,
    Textarea,
    Table,
    Box,
    Badge,
    Modal,
} from "@cloudscape-design/components";
import { AgentConfig } from "./types";

interface AgentConfigPanelProps {
    agents: AgentConfig[];
    onAdd: (agent: AgentConfig) => void;
    onRemove: (agentId: string) => void;
}

const MODELS = [
    { label: "Claude Sonnet 4.6 (Global)", value: "global.anthropic.claude-sonnet-4-6-v1:0" },
    { label: "Claude Opus 4.6 (Global)", value: "global.anthropic.claude-opus-4-6-v1:0" },
];

const AUTONOMY_OPTIONS = [
    { label: "Ask before acting", value: "ask" },
    { label: "Act then notify", value: "notify" },
    { label: "Fully autonomous", value: "silent" },
];

export function AgentConfigPanel({ agents, onAdd, onRemove }: AgentConfigPanelProps) {
    const [showModal, setShowModal] = useState(false);
    const [name, setName] = useState("");
    const [purpose, setPurpose] = useState("");
    const [model, setModel] = useState(MODELS[0].value);
    const [autonomy, setAutonomy] = useState("ask");

    const handleAdd = () => {
        const id = name.toLowerCase().replace(/\s+/g, "-") + "-agent";
        const agent: AgentConfig = {
            id,
            name,
            type: "custom",
            system_prompt: `You are ${name}. ${purpose}`,
            model,
            tools: [],
            channels: [],
            mcp_channels: [],
            autonomy: autonomy as "ask" | "notify" | "silent",
        };
        onAdd(agent);
        setShowModal(false);
        setName("");
        setPurpose("");
    };

    return (
        <>
            <Table
                header={
                    <Header
                        variant="h3"
                        actions={<Button onClick={() => setShowModal(true)}>Add Agent</Button>}
                    >
                        Agent Roster
                    </Header>
                }
                items={agents}
                columnDefinitions={[
                    { id: "name", header: "Name", cell: (a) => a.name },
                    { id: "type", header: "Type", cell: (a) => <Badge color={a.type === "default" ? "blue" : "green"}>{a.type}</Badge> },
                    { id: "autonomy", header: "Autonomy", cell: (a) => a.autonomy },
                    { id: "actions", header: "Actions", cell: (a) => (
                        a.type === "custom" ? (
                            <Button variant="icon" iconName="remove" onClick={() => onRemove(a.id)} />
                        ) : <Box color="text-status-inactive">Built-in</Box>
                    )},
                ]}
                empty={<Box>No agents configured</Box>}
            />

            <Modal
                visible={showModal}
                onDismiss={() => setShowModal(false)}
                header="Add Custom Agent"
                footer={
                    <SpaceBetween size="s" direction="horizontal">
                        <Button onClick={() => setShowModal(false)}>Cancel</Button>
                        <Button variant="primary" onClick={handleAdd} disabled={!name || !purpose}>
                            Create Agent
                        </Button>
                    </SpaceBetween>
                }
            >
                <SpaceBetween size="m">
                    <FormField label="Agent Name">
                        <Input value={name} onChange={({ detail }) => setName(detail.value)} placeholder="Code Reviewer" />
                    </FormField>
                    <FormField label="Purpose (becomes system prompt)">
                        <Textarea value={purpose} onChange={({ detail }) => setPurpose(detail.value)} rows={3} placeholder="Review pull requests and suggest improvements..." />
                    </FormField>
                    <FormField label="Model">
                        <Select
                            selectedOption={MODELS.find((m) => m.value === model) || MODELS[0]}
                            onChange={({ detail }) => setModel(detail.selectedOption?.value || MODELS[0].value)}
                            options={MODELS}
                        />
                    </FormField>
                    <FormField label="Autonomy Level">
                        <Select
                            selectedOption={AUTONOMY_OPTIONS.find((a) => a.value === autonomy) || AUTONOMY_OPTIONS[0]}
                            onChange={({ detail }) => setAutonomy(detail.selectedOption?.value || "ask")}
                            options={AUTONOMY_OPTIONS}
                        />
                    </FormField>
                </SpaceBetween>
            </Modal>
        </>
    );
}
```

- [ ] **Step 2: Create job viewer**

```typescript
// artifacts/chat-ui/src/components/hive/job-viewer.tsx
import {
    Table,
    Header,
    Box,
    Badge,
    Button,
    SpaceBetween,
    StatusIndicator,
} from "@cloudscape-design/components";
import { CronJob } from "./types";

interface JobViewerProps {
    jobs: CronJob[];
    onDelete: (jobId: string) => void;
}

export function JobViewer({ jobs, onDelete }: JobViewerProps) {
    return (
        <Table
            header={<Header variant="h3">Scheduled Jobs</Header>}
            items={jobs}
            columnDefinitions={[
                { id: "name", header: "Name", cell: (j) => j.name },
                { id: "schedule", header: "Schedule", cell: (j) => <code>{j.schedule}</code> },
                { id: "agent", header: "Agent", cell: (j) => <Badge>{j.agent_id}</Badge> },
                { id: "action", header: "Action", cell: (j) => j.action },
                { id: "channel", header: "Notify Via", cell: (j) => j.notify_channel || "—" },
                {
                    id: "actions",
                    header: "Actions",
                    cell: (j) => (
                        <Button variant="icon" iconName="remove" onClick={() => onDelete(j.id)} />
                    ),
                },
            ]}
            empty={
                <Box textAlign="center" padding="l">
                    No scheduled jobs. Ask an agent to schedule something!
                </Box>
            }
        />
    );
}
```

- [ ] **Step 3: Commit**

```bash
git add artifacts/chat-ui/src/components/hive/agent-config.tsx artifacts/chat-ui/src/components/hive/job-viewer.tsx
git commit -m "feat(hive-ui): add agent config panel and job viewer"
```

---

### Task 7: Main Hive Layout (Wiring It All Together)

**Files:**
- Create: `artifacts/chat-ui/src/components/hive/hive-layout.tsx`

- [ ] **Step 1: Implement the main layout that connects all components**

```typescript
// artifacts/chat-ui/src/components/hive/hive-layout.tsx
import { useState, useEffect, useCallback } from "react";
import {
    Grid,
    Tabs,
    Container,
    SpaceBetween,
    Button,
    Header,
    StatusIndicator,
} from "@cloudscape-design/components";
import { AgentGraph } from "./agent-graph";
import { ChatPanel } from "./chat-panel";
import { ChannelConfigWizard } from "./channel-config";
import { AgentConfigPanel } from "./agent-config";
import { JobViewer } from "./job-viewer";
import { HiveConfig, HiveEvent, HiveResponse, AgentConfig, ChannelConfig, CronJob } from "./types";
import { connectHive, sendHiveMessage, getHiveSocket } from "../../common/hive-ws";
import { AuthHelper } from "../../common/helpers/auth-help";

interface ChatMessage {
    id: string;
    role: "user" | "agent" | "system";
    content: string;
    agent_id?: string;
    agent_name?: string;
    timestamp: number;
    thinking?: string;
}

export function HiveLayout() {
    const [config, setConfig] = useState<HiveConfig | null>(null);
    const [events, setEvents] = useState<HiveEvent[]>([]);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [activeAgent, setActiveAgent] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [connected, setConnected] = useState(false);
    const [showChannelWizard, setShowChannelWizard] = useState(false);
    const [activeTab, setActiveTab] = useState("chat");
    const [jobs, setJobs] = useState<CronJob[]>([]);

    // Connect to Hive on mount
    useEffect(() => {
        const init = async () => {
            const userdata = await AuthHelper.getUserDetails();
            const idToken = await AuthHelper.getIdToken();
            const userId = userdata.signInDetails?.loginId || "anonymous";

            await connectHive(
                idToken,
                userId,
                handleMessage,
                (err) => console.error("Hive error:", err),
                () => setConnected(false),
            );
            setConnected(true);
        };
        init().catch(console.error);
    }, []);

    const handleMessage = useCallback((msg: HiveResponse) => {
        switch (msg.type) {
            case "init_complete":
                setConfig(msg.config);
                break;
            case "routed":
                setActiveAgent(msg.target);
                break;
            case "response":
                setIsLoading(false);
                setMessages((prev) => [
                    ...prev,
                    {
                        id: crypto.randomUUID(),
                        role: "agent",
                        content: msg.data.result || JSON.stringify(msg.data),
                        agent_id: activeAgent || undefined,
                        agent_name: config?.agents.find((a) => a.id === activeAgent)?.name,
                        timestamp: Date.now(),
                    },
                ]);
                setActiveAgent(null);
                break;
            case "events":
                setEvents(msg.events);
                break;
            case "error":
                setIsLoading(false);
                setMessages((prev) => [
                    ...prev,
                    { id: crypto.randomUUID(), role: "system", content: msg.message, timestamp: Date.now() },
                ]);
                break;
            case "channel_added":
                // Refresh config
                const ws = getHiveSocket();
                if (ws) sendHiveMessage(ws, { type: "get_config" });
                break;
            case "config":
                setConfig(msg.config);
                break;
        }
    }, [activeAgent, config]);

    const handleSend = (text: string) => {
        setMessages((prev) => [
            ...prev,
            { id: crypto.randomUUID(), role: "user", content: text, timestamp: Date.now() },
        ]);
        setIsLoading(true);
        const ws = getHiveSocket();
        if (ws) sendHiveMessage(ws, { type: "chat", query: text });
    };

    const handleAddChannel = (channelConfig: ChannelConfig) => {
        const ws = getHiveSocket();
        if (ws) sendHiveMessage(ws, { type: "add_channel", channel: channelConfig });
        setShowChannelWizard(false);
    };

    const handleAddAgent = (agent: AgentConfig) => {
        if (config) {
            setConfig({ ...config, agents: [...config.agents, agent] });
        }
    };

    const handleRemoveAgent = (agentId: string) => {
        if (config) {
            setConfig({ ...config, agents: config.agents.filter((a) => a.id !== agentId) });
        }
    };

    const handleNodeClick = (agentId: string) => {
        // Filter events for this agent
        const agentEvents = events.filter((e) => e.agent === agentId);
        // Could open a detail panel — for now just log
        console.log(`Agent ${agentId} events:`, agentEvents);
    };

    if (showChannelWizard) {
        return (
            <ChannelConfigWizard
                agents={config?.agents || []}
                onSave={handleAddChannel}
                onCancel={() => setShowChannelWizard(false)}
            />
        );
    }

    return (
        <SpaceBetween size="l">
            {/* Connection status */}
            <StatusIndicator type={connected ? "success" : "error"}>
                {connected ? "Connected to Hive" : "Disconnected"}
            </StatusIndicator>

            {/* Agent Graph */}
            <Container header={<Header variant="h2">Agent Network</Header>}>
                <AgentGraph
                    config={config}
                    events={events}
                    activeAgent={activeAgent}
                    onNodeClick={handleNodeClick}
                />
            </Container>

            {/* Tabbed panel: Chat, Agents, Channels, Jobs */}
            <Tabs
                activeTabId={activeTab}
                onChange={({ detail }) => setActiveTab(detail.activeTabId)}
                tabs={[
                    {
                        id: "chat",
                        label: "Chat",
                        content: (
                            <ChatPanel
                                messages={messages}
                                onSend={handleSend}
                                isLoading={isLoading}
                                activeAgent={activeAgent}
                            />
                        ),
                    },
                    {
                        id: "agents",
                        label: "Agents",
                        content: (
                            <AgentConfigPanel
                                agents={config?.agents || []}
                                onAdd={handleAddAgent}
                                onRemove={handleRemoveAgent}
                            />
                        ),
                    },
                    {
                        id: "channels",
                        label: "Channels",
                        content: (
                            <Container
                                header={
                                    <Header
                                        variant="h3"
                                        actions={
                                            <Button onClick={() => setShowChannelWizard(true)}>
                                                Add Channel
                                            </Button>
                                        }
                                    >
                                        Channels
                                    </Header>
                                }
                            >
                                {config?.channels.length === 0 ? (
                                    <SpaceBetween size="s" alignItems="center">
                                        No channels configured. Add a Slack, WhatsApp, or MCP channel.
                                    </SpaceBetween>
                                ) : (
                                    <SpaceBetween size="s">
                                        {config?.channels.map((ch) => (
                                            <div key={ch.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                                <StatusIndicator type="success" />
                                                <strong>{ch.id}</strong> — {ch.provider} ({ch.type})
                                            </div>
                                        ))}
                                    </SpaceBetween>
                                )}
                            </Container>
                        ),
                    },
                    {
                        id: "jobs",
                        label: "Jobs",
                        content: <JobViewer jobs={jobs} onDelete={(id) => setJobs(jobs.filter((j) => j.id !== id))} />,
                    },
                ]}
            />
        </SpaceBetween>
    );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd artifacts/chat-ui && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add artifacts/chat-ui/src/components/hive/hive-layout.tsx
git commit -m "feat(hive-ui): add main HiveLayout wiring graph, chat, agents, channels, and jobs"
```

---

### Task 8: CSS Animations & Final Polish

**Files:**
- Create: `artifacts/chat-ui/src/components/hive/hive.css`

- [ ] **Step 1: Add pulse animation for thinking state**

```css
/* artifacts/chat-ui/src/components/hive/hive.css */
@keyframes pulse {
    0% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.08); opacity: 0.8; }
    100% { transform: scale(1); opacity: 1; }
}

@keyframes edge-flow {
    0% { stroke-dashoffset: 20; }
    100% { stroke-dashoffset: 0; }
}

.react-flow__edge.animated path {
    animation: edge-flow 0.5s linear infinite;
}

.hive-graph-container {
    border-radius: 8px;
    border: 1px solid #e9ebed;
    overflow: hidden;
}
```

- [ ] **Step 2: Import CSS in hive-layout.tsx**

Add at top of `hive-layout.tsx`:
```typescript
import "./hive.css";
```

- [ ] **Step 3: Run build to verify everything compiles**

Run: `cd artifacts/chat-ui && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add artifacts/chat-ui/src/components/hive/hive.css artifacts/chat-ui/src/components/hive/hive-layout.tsx
git commit -m "feat(hive-ui): add CSS animations and final polish"
```

---
