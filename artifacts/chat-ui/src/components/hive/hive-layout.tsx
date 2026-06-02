import { useState, useEffect, useCallback } from "react";
import { fetchAuthSession } from "aws-amplify/auth";
import {
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
        const agentEvents = events.filter((e) => e.agent === agentId);
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
