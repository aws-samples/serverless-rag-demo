import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { AgentStatus } from "./types";

interface AgentNodeProps {
    data: { label: string; status: AgentStatus; isCore?: boolean };
}

export const AgentNode = memo(({ data }: AgentNodeProps) => {
    const colors: Record<AgentStatus, string> = {
        idle: "#8c8c8c", thinking: "#f0a30a", acting: "#1d8102", error: "#d13212",
    };
    const size = data.isCore ? 80 : 60;
    const color = colors[data.status];

    return (
        <div style={{
            width: size, height: size, borderRadius: "50%",
            background: `radial-gradient(circle, ${color}33, ${color}11)`,
            border: `3px solid ${color}`,
            display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column",
            animation: data.status === "thinking" ? "pulse 1.5s infinite" : undefined,
        }}>
            <Handle type="target" position={Position.Top} style={{ visibility: "hidden" }} />
            <span style={{ fontSize: 10, fontWeight: 600, textAlign: "center", padding: 4 }}>{data.label}</span>
            {data.status !== "idle" && <span style={{ fontSize: 8, color }}>{data.status}</span>}
            <Handle type="source" position={Position.Bottom} style={{ visibility: "hidden" }} />
        </div>
    );
});

interface ChannelNodeProps {
    data: { label: string; provider: string; connected: boolean };
}

export const ChannelNode = memo(({ data }: ChannelNodeProps) => {
    const icons: Record<string, string> = { slack: "💬", "whatsapp-baileys": "📱", mcp: "🔌" };
    return (
        <div style={{
            width: 44, height: 44, borderRadius: "50%",
            background: data.connected ? "#1d810211" : "#d1321211",
            border: `2px solid ${data.connected ? "#1d8102" : "#d13212"}`,
            display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column",
        }}>
            <Handle type="target" position={Position.Top} style={{ visibility: "hidden" }} />
            <span style={{ fontSize: 16 }}>{icons[data.provider] || "⚡"}</span>
            <span style={{ fontSize: 8 }}>{data.label}</span>
            <Handle type="source" position={Position.Bottom} style={{ visibility: "hidden" }} />
        </div>
    );
});
