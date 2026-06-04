import { useEffect, useRef } from "react";
import { Container, Header, Box, SpaceBetween, Badge } from "@cloudscape-design/components";
import { ChannelMessage } from "./types";

interface ChannelMessageFeedProps {
    messages: ChannelMessage[];
}

function formatTime(ts: number): string {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

const PROVIDER_COLORS: Record<string, string> = {
    whatsapp: "#25D366",
    slack: "#4A154B",
    mcp: "#FF9900",
};

const PROVIDER_LABELS: Record<string, string> = {
    whatsapp: "WA",
    slack: "Slack",
    mcp: "MCP",
};

function ProviderBadge({ provider }: { provider: string }) {
    const color = PROVIDER_COLORS[provider] || "#666";
    const label = PROVIDER_LABELS[provider] || provider;
    return (
        <span style={{
            fontSize: 10,
            fontWeight: 600,
            padding: "1px 5px",
            borderRadius: 3,
            background: color,
            color: "#fff",
            textTransform: "uppercase",
        }}>
            {label}
        </span>
    );
}

export function ChannelMessageFeed({ messages }: ChannelMessageFeedProps) {
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages.length]);

    if (messages.length === 0) {
        return (
            <Container header={<Header variant="h3">Messages</Header>}>
                <Box textAlign="center" color="text-status-inactive" padding="l">
                    No messages yet. Channel messages (WhatsApp, Slack, MCP) will appear here in real-time.
                </Box>
            </Container>
        );
    }

    return (
        <Container header={<Header variant="h3" counter={`(${messages.length})`}>Messages</Header>}>
            <div style={{ maxHeight: 500, overflowY: "auto", padding: "4px 0" }}>
                <SpaceBetween size="xs">
                    {messages.map((msg) => (
                        <div
                            key={msg.id}
                            style={{
                                padding: "8px 12px",
                                borderRadius: 8,
                                background: msg.direction === "in" ? "#f4f4f4" : "#e8f4fd",
                                borderLeft: msg.direction === "in" ? "3px solid #0972d3" : "3px solid #037f0c",
                            }}
                        >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                    <Badge color={msg.direction === "in" ? "blue" : "green"}>
                                        {msg.direction === "in" ? "IN" : "OUT"}
                                    </Badge>
                                    <ProviderBadge provider={msg.provider} />
                                    <strong>{msg.contact_name}</strong>
                                    <span style={{ fontSize: 11, color: "#666" }}>{msg.channel_id}</span>
                                </div>
                                <span style={{ fontSize: 11, color: "#888" }}>{formatTime(msg.timestamp)}</span>
                            </div>
                            <div style={{ marginLeft: 4 }}>{msg.message}</div>
                            {msg.reply && (
                                <div style={{ marginTop: 4, marginLeft: 12, padding: "4px 8px", background: "#e6f7e6", borderRadius: 4, fontSize: 13 }}>
                                    → {msg.reply}
                                </div>
                            )}
                        </div>
                    ))}
                    <div ref={bottomRef} />
                </SpaceBetween>
            </div>
        </Container>
    );
}
