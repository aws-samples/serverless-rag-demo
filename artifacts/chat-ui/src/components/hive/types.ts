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
    config: Record<string, any>;
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

export type HiveMessage =
    | { type: "init"; user_id: string }
    | { type: "chat"; query: string }
    | { type: "get_events"; count?: number }
    | { type: "get_config" }
    | { type: "add_channel"; channel: ChannelConfig }
    | { type: "remove_channel"; channel_id: string }
    | { type: "update_channel"; channel: ChannelConfig }
    | { type: "test_channel"; channel_id: string }
    | { type: "list_channels" }
    | { type: "wa_approve"; channel_id: string; approval_id: string; action: "send" | "edit" | "reject"; response?: string }
    | { type: "wipe" };

export type HiveResponse =
    | { type: "init_complete"; config: HiveConfig }
    | { type: "routed"; target: string }
    | { type: "response"; data: Record<string, any> }
    | { type: "events"; events: HiveEvent[] }
    | { type: "config"; config: HiveConfig }
    | { type: "channel_added"; channel_id: string; channel?: any; config?: HiveConfig }
    | { type: "channel_removed"; channel_id: string; config?: HiveConfig }
    | { type: "channel_updated"; channel?: any; config?: HiveConfig }
    | { type: "channel_test"; channel_id: string; connected?: boolean; phone?: string; message?: string }
    | { type: "channels"; channels: any[] }
    | { type: "wa_qr"; channel_id: string; qr: string }
    | { type: "wa_connected"; channel_id: string; phone: string }
    | { type: "wa_incoming"; channel_id: string; from: string; from_name: string; message: string; mode: string; proposed_response?: string; response?: string; approval_id?: string }
    | { type: "wa_status"; channel_id: string; connected: boolean }
    | { type: "wiped" }
    | { type: "error"; message: string };
