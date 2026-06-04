import { Container, Header, SpaceBetween, Button, StatusIndicator, Box, Table, ButtonDropdown } from "@cloudscape-design/components";
import { AgentStatusInfo } from "./types";

interface SessionPanelProps {
    agents: AgentStatusInfo[];
    onStopAgent: (agentId: string) => void;
    onStartAgent: (agentId: string) => void;
    onRestartAgent: (agentId: string) => void;
    onRestartAll: () => void;
    onRestart: () => void;
    onWipe: () => void;
}

function formatUptime(startedAt: number): string {
    if (!startedAt) return "-";
    const secs = Math.floor(Date.now() / 1000 - startedAt);
    if (secs < 60) return `${secs}s`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m`;
    return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
}

function formatLastActivity(ts: number): string {
    if (!ts) return "never";
    const secs = Math.floor(Date.now() / 1000 - ts);
    if (secs < 10) return "just now";
    if (secs < 60) return `${secs}s ago`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    return `${Math.floor(secs / 3600)}h ago`;
}

export function SessionPanel({ agents, onStopAgent, onStartAgent, onRestartAgent, onRestartAll, onRestart, onWipe }: SessionPanelProps) {
    return (
        <SpaceBetween size="l">
            <Container
                header={
                    <Header
                        variant="h3"
                        actions={
                            <SpaceBetween direction="horizontal" size="xs">
                                <Button onClick={onRestartAll}>Restart All Agents</Button>
                            </SpaceBetween>
                        }
                    >
                        Agent Lifecycle
                    </Header>
                }
            >
                {agents.length === 0 ? (
                    <Box textAlign="center" color="text-status-inactive" padding="l">
                        No agents registered. Initialize a session first.
                    </Box>
                ) : (
                    <Table
                        items={agents}
                        columnDefinitions={[
                            {
                                id: "status",
                                header: "Status",
                                width: 100,
                                cell: (item) => (
                                    <StatusIndicator type={item.status === "running" ? "success" : "stopped"}>
                                        {item.status}
                                    </StatusIndicator>
                                ),
                            },
                            {
                                id: "name",
                                header: "Agent",
                                cell: (item) => <strong>{item.name}</strong>,
                            },
                            {
                                id: "id",
                                header: "ID",
                                cell: (item) => <span style={{ fontSize: 12, color: "#666" }}>{item.id}</span>,
                            },
                            {
                                id: "messages",
                                header: "Messages",
                                width: 90,
                                cell: (item) => item.message_count,
                            },
                            {
                                id: "last_activity",
                                header: "Last Active",
                                width: 110,
                                cell: (item) => formatLastActivity(item.last_activity),
                            },
                            {
                                id: "uptime",
                                header: "Uptime",
                                width: 90,
                                cell: (item) => item.status === "running" ? formatUptime(item.started_at) : "-",
                            },
                            {
                                id: "actions",
                                header: "Actions",
                                width: 140,
                                cell: (item) => (
                                    <ButtonDropdown
                                        items={[
                                            ...(item.status === "running"
                                                ? [{ id: "stop", text: "Stop" }, { id: "restart", text: "Restart" }]
                                                : [{ id: "start", text: "Start" }]),
                                        ]}
                                        onItemClick={({ detail }) => {
                                            if (detail.id === "stop") onStopAgent(item.id);
                                            if (detail.id === "start") onStartAgent(item.id);
                                            if (detail.id === "restart") onRestartAgent(item.id);
                                        }}
                                    >
                                        Actions
                                    </ButtonDropdown>
                                ),
                            },
                        ]}
                        variant="embedded"
                        empty={<Box>No agents</Box>}
                    />
                )}
            </Container>

            <Container header={<Header variant="h3">Container</Header>}>
                <SpaceBetween size="l">
                    <SpaceBetween size="s">
                        <Box>
                            <strong>Restart Container</strong> — Picks up the latest deployed code. Channels reconnect automatically. All state is preserved.
                        </Box>
                        <Button variant="normal" onClick={onRestart}>Restart Container</Button>
                    </SpaceBetween>
                    <hr style={{ border: "none", borderTop: "1px solid #eee" }} />
                    <SpaceBetween size="s">
                        <Box>
                            <strong>Wipe Session</strong> — Deletes all state (config, channels, persona, guardrails, auth, event logs) and resets to defaults. Irreversible.
                        </Box>
                        <Button variant="normal" onClick={onWipe}>Wipe Session</Button>
                    </SpaceBetween>
                </SpaceBetween>
            </Container>
        </SpaceBetween>
    );
}
