import { useState, useEffect, useCallback } from "react";
import { fetchAuthSession } from "aws-amplify/auth";
import {
    Tabs,
    Container,
    SpaceBetween,
    Button,
    Header,
    StatusIndicator,
    ExpandableSection,
    Flashbar,
    Grid,
    Box,
    Modal,
    Alert,
} from "@cloudscape-design/components";
import { WaQrModal } from "./wa-qr-modal";
import { AgentGraph } from "./agent-graph";
import { ChatPanel } from "./chat-panel";
import { ChannelConfigWizard } from "./channel-config";
import { AgentConfigPanel } from "./agent-config";
import { JobViewer } from "./job-viewer";
import { HiveConfig, HiveEvent, HiveResponse, AgentConfig, ChannelConfig, CronJob, PersonaData, GuardrailsPolicy } from "./types";
import { PersonaConfig } from "./persona-config";
import { GuardrailsConfig } from "./guardrails-config";
import { connectHive, sendHiveMessage, getHiveSocket } from "../../common/hive-ws";
import { AuthHelper } from "../../common/helpers/auth-help";
import "./hive.css";

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
    const [graphExpanded, setGraphExpanded] = useState(true);
    const [waQrVisible, setWaQrVisible] = useState(false);
    const [waQrData, setWaQrData] = useState<string | null>(null);
    const [waConnected, setWaConnected] = useState(false);
    const [waPhone, setWaPhone] = useState("");
    const [flashItems, setFlashItems] = useState<any[]>([]);
    const [persona, setPersona] = useState<PersonaData | null>(null);
    const [guardrails, setGuardrails] = useState<GuardrailsPolicy | null>(null);

    // Connect to Hive on mount
    useEffect(() => {
        const init = async () => {
            const userdata = await AuthHelper.getUserDetails();
            const session = await fetchAuthSession();
            const idToken = session.tokens?.idToken?.toString() ?? "";
            const userId = (userdata as any).signInDetails?.loginId || "anonymous";

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
            case "channel_removed":
            case "channel_updated":
                if (msg.config) setConfig(msg.config);
                else {
                    const ws2 = getHiveSocket();
                    if (ws2) sendHiveMessage(ws2, { type: "get_config" });
                }
                break;
            case "channel_test": {
                const flashId = crypto.randomUUID();
                setFlashItems((prev) => [
                    ...prev,
                    {
                        id: flashId,
                        type: msg.connected ? "success" : "warning",
                        content: `${msg.channel_id}: ${msg.connected ? "Connected" : "Not connected"}${msg.phone ? ` (${msg.phone})` : ""}${msg.message ? ` — ${msg.message}` : ""}`,
                        dismissible: true,
                        onDismiss: () => setFlashItems((f) => f.filter((i) => i.id !== flashId)),
                    },
                ]);
                // Auto-dismiss after 5s
                setTimeout(() => setFlashItems((f) => f.filter((i) => i.id !== flashId)), 5000);
                break;
            }
            case "config":
                setConfig(msg.config);
                break;
            case "wa_qr":
                setWaQrData(msg.qr);
                setWaQrVisible(true);
                break;
            case "wa_connected":
                setWaConnected(true);
                setWaPhone(msg.phone);
                setTimeout(() => setWaQrVisible(false), 2000);
                break;
            case "wa_incoming":
                setMessages((prev) => [
                    ...prev,
                    {
                        id: crypto.randomUUID(),
                        role: "system" as const,
                        content: `📱 WhatsApp from ${msg.from_name || msg.from}: ${msg.message}${msg.response ? `\n\n🤖 Reply: ${msg.response}` : ""}${msg.proposed_response ? `\n\n🤖 Proposed: ${msg.proposed_response}` : ""}`,
                        timestamp: Date.now(),
                    },
                ]);
                break;
            case "wa_status":
                setWaConnected(msg.connected);
                break;
            case "persona":
            case "persona_saved":
                setPersona(msg.persona);
                break;
            case "guardrails":
            case "guardrails_saved":
                setGuardrails(msg.guardrails);
                break;
            case "jobs":
            case "job_deleted":
                setJobs(msg.jobs);
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

    const [editingChannel, setEditingChannel] = useState<ChannelConfig | null>(null);
    const [showWipeModal, setShowWipeModal] = useState(false);

    const handleAddChannel = (channelConfig: ChannelConfig) => {
        const ws = getHiveSocket();
        if (editingChannel) {
            if (ws) sendHiveMessage(ws, { type: "update_channel", channel: channelConfig });
            setEditingChannel(null);
        } else {
            if (ws) sendHiveMessage(ws, { type: "add_channel", channel: channelConfig });
        }
        setShowChannelWizard(false);
    };

    const handleRemoveChannel = (channelId: string) => {
        const ws = getHiveSocket();
        if (ws) sendHiveMessage(ws, { type: "remove_channel", channel_id: channelId });
    };

    const handleTestChannel = (channelId: string) => {
        const ws = getHiveSocket();
        if (ws) sendHiveMessage(ws, { type: "test_channel", channel_id: channelId });
    };

    const handleEditChannel = (ch: ChannelConfig) => {
        setEditingChannel(ch);
        setShowChannelWizard(true);
    };

    const handleAddAgent = (agent: AgentConfig) => {
        if (config && ws) {
            sendHiveMessage(ws, { type: "add_agent", agent });
            setConfig({ ...config, agents: [...config.agents, agent] });
        }
    };

    const handleRemoveAgent = (agentId: string) => {
        if (config && ws) {
            sendHiveMessage(ws, { type: "remove_agent", agent_id: agentId });
            setConfig({ ...config, agents: config.agents.filter((a) => a.id !== agentId) });
        }
    };

    const handleNodeClick = (agentId: string) => {
        const agentEvents = events.filter((e) => e.agent === agentId);
        console.log(`Agent ${agentId} events:`, agentEvents);
    };

    if (showChannelWizard) {
        return (
            <ChannelConfigWizard
                agents={config?.agents || []}
                onSave={handleAddChannel}
                onCancel={() => { setShowChannelWizard(false); setEditingChannel(null); }}
                initialChannel={editingChannel}
            />
        );
    }

    return (
        <SpaceBetween size="s">
            {flashItems.length > 0 && <Flashbar items={flashItems} />}
            {/* Connection status */}
            <StatusIndicator type={connected ? "success" : "error"}>
                {connected ? "Connected to Hive" : "Disconnected"}
            </StatusIndicator>

            {/* Vertical split: Graph (collapsible) | Chat + Tabs */}
            <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
                {/* Left: Agent Graph (collapsible) */}
                <div style={{
                    width: graphExpanded ? 360 : 0,
                    minWidth: graphExpanded ? 360 : 0,
                    transition: "width 0.3s ease, min-width 0.3s ease",
                    overflow: "hidden",
                    flexShrink: 0,
                }}>
                    {graphExpanded && (
                        <Container
                            header={
                                <Header
                                    variant="h3"
                                    actions={
                                        <Button
                                            variant="icon"
                                            iconName="angle-left"
                                            onClick={() => setGraphExpanded(false)}
                                        />
                                    }
                                >
                                    Agent Network
                                </Header>
                            }
                        >
                            <div style={{ height: 320 }}>
                                <AgentGraph
                                    config={config}
                                    events={events}
                                    activeAgent={activeAgent}
                                    onNodeClick={handleNodeClick}
                                />
                            </div>
                        </Container>
                    )}
                </div>

                {/* Expand button when collapsed */}
                {!graphExpanded && (
                    <div style={{ flexShrink: 0, paddingTop: 4 }}>
                        <Button
                            variant="icon"
                            iconName="angle-right"
                            onClick={() => setGraphExpanded(true)}
                        />
                    </div>
                )}

                {/* Right: Chat + Tabs */}
                <div style={{ flex: 1, minWidth: 0 }}>
                    <Tabs
                        activeTabId={activeTab}
                        onChange={({ detail }) => {
                            setActiveTab(detail.activeTabId);
                            if (detail.activeTabId === "jobs") {
                                const ws = getHiveSocket();
                                if (ws) sendHiveMessage(ws, { type: "get_jobs" });
                            }
                            if (detail.activeTabId === "persona" && !persona) {
                                const ws = getHiveSocket();
                                if (ws) sendHiveMessage(ws, { type: "get_persona" });
                            }
                            if (detail.activeTabId === "guardrails") {
                                const ws = getHiveSocket();
                                if (ws) sendHiveMessage(ws, { type: "get_guardrails" });
                            }
                        }}
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
                                id: "persona",
                                label: "Persona",
                                content: (
                                    <PersonaConfig
                                        persona={persona}
                                        channels={config?.channels || []}
                                        onSave={(p) => {
                                            const ws = getHiveSocket();
                                            if (ws) sendHiveMessage(ws, { type: "save_persona", persona: p });
                                        }}
                                    />
                                ),
                            },
                            {
                                id: "guardrails",
                                label: "Guardrails",
                                content: (
                                    <GuardrailsConfig
                                        guardrails={guardrails}
                                        onSave={(g) => {
                                            const ws = getHiveSocket();
                                            if (ws) sendHiveMessage(ws, { type: "save_guardrails", guardrails: g });
                                        }}
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
                                                        <StatusIndicator type={ch.provider === "whatsapp-baileys" && waConnected ? "success" : "info"} />
                                                        <strong>{ch.id}</strong> — {ch.provider} ({ch.type})
                                                        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                                                            <Button variant="inline-link" onClick={() => handleTestChannel(ch.id)}>Test</Button>
                                                            <Button variant="inline-link" onClick={() => handleEditChannel(ch)}>Edit</Button>
                                                            <Button variant="inline-link" onClick={() => handleRemoveChannel(ch.id)}>Delete</Button>
                                                        </div>
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
                                content: <JobViewer jobs={jobs} onDelete={(id) => {
                                    const ws = getHiveSocket();
                                    if (ws) sendHiveMessage(ws, { type: "delete_job", job_id: id });
                                }} />,
                            },
                            {
                                id: "danger",
                                label: "Session",
                                content: (
                                    <Container header={<Header variant="h3">Session Management</Header>}>
                                        <SpaceBetween size="l">
                                            <SpaceBetween size="s">
                                                <Box>
                                                    <strong>Restart Container</strong> — Picks up the latest deployed code. Your session reconnects automatically in a few seconds. All state (channels, config, persona) is preserved.
                                                </Box>
                                                <Button variant="normal" onClick={() => {
                                                    const ws = getHiveSocket();
                                                    if (ws) sendHiveMessage(ws, { type: "restart" });
                                                }}>
                                                    Restart
                                                </Button>
                                            </SpaceBetween>
                                            <hr style={{ border: "none", borderTop: "1px solid #eee" }} />
                                            <SpaceBetween size="s">
                                                <Box>
                                                    <strong>Wipe Session</strong> — Deletes all state (config, channels, persona, guardrails, auth, event logs) and resets to defaults. This is irreversible.
                                                </Box>
                                                <Button variant="normal" onClick={() => setShowWipeModal(true)}>
                                                    Wipe Session
                                                </Button>
                                            </SpaceBetween>
                                        </SpaceBetween>
                                    </Container>
                                ),
                            },
                        ]}
                    />
                </div>
            </div>
            <WaQrModal
                visible={waQrVisible}
                qrDataUrl={waQrData}
                connected={waConnected}
                phone={waPhone}
                onDismiss={() => setWaQrVisible(false)}
            />
            <Modal
                visible={showWipeModal}
                onDismiss={() => setShowWipeModal(false)}
                header="Wipe Session"
                footer={
                    <SpaceBetween size="s" direction="horizontal">
                        <Button onClick={() => setShowWipeModal(false)}>Cancel</Button>
                        <Button variant="primary" onClick={() => {
                            const ws = getHiveSocket();
                            if (ws) sendHiveMessage(ws, { type: "wipe" });
                            setShowWipeModal(false);
                            setConfig(null);
                            setMessages([]);
                            setJobs([]);
                            setPersona(null);
                            setGuardrails(null);
                            setWaConnected(false);
                            window.location.reload();
                        }}>
                            Wipe Everything
                        </Button>
                    </SpaceBetween>
                }
            >
                <Alert type="warning">
                    This will permanently delete all your Hive data: channels, agents, persona, guardrails, scheduled jobs, WhatsApp auth, and event logs. You will need to reconfigure everything from scratch.
                </Alert>
            </Modal>
        </SpaceBetween>
    );
}
