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

export interface PersonaData {
    persona: string;
    channel_overrides: Record<string, string>;
    contact_overrides: Record<string, string>; // key format: "channelId::contactJid"
}

export interface TierConfig {
    description: string;
    contacts: string[];
}

export interface GuardrailsPolicy {
    version: number;
    enabled: boolean;
    tiers: Record<string, TierConfig>;
    policies: Record<string, Record<string, boolean>>;
    refusal_message: string;
}

export interface ChannelMessage {
    id: string;
    direction: "in" | "out";
    provider: string;
    contact_name: string;
    contact_jid: string;
    channel_id: string;
    message: string;
    reply?: string;
    timestamp: number;
    metadata?: Record<string, any>;
}

export type AgentStatus = "idle" | "thinking" | "acting" | "error";

export interface AgentStatusInfo {
    id: string;
    name: string;
    status: "running" | "stopped";
    model: string;
    started_at: number;
    last_activity: number;
    message_count: number;
    has_strands: boolean;
    system_prompt: string;
}

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
    | { type: "get_jobs" }
    | { type: "delete_job"; job_id: string }
    | { type: "get_persona" }
    | { type: "save_persona"; persona: PersonaData }
    | { type: "get_guardrails" }
    | { type: "save_guardrails"; guardrails: GuardrailsPolicy }
    | { type: "get_agents" }
    | { type: "stop_agent"; agent_id: string }
    | { type: "start_agent"; agent_id: string }
    | { type: "restart_agent"; agent_id: string }
    | { type: "restart_all_agents" }
    | { type: "update_agent_prompt"; agent_id: string; system_prompt: string }
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
    | { type: "channel_incoming"; channel_id: string; provider: string; contact: string; contact_name: string; message: string; timestamp: number; reply?: string; metadata?: Record<string, any> }
    | { type: "channel_outgoing"; channel_id: string; provider: string; contact: string; contact_name: string; message: string; timestamp: number; metadata?: Record<string, any> }
    | { type: "wa_incoming"; channel_id: string; from: string; from_name: string; message: string; mode: string; proposed_response?: string; response?: string; approval_id?: string }
    | { type: "wa_outgoing"; channel_id: string; to: string; to_name: string; message: string; timestamp: number }
    | { type: "wa_status"; channel_id: string; connected: boolean }
    | { type: "jobs"; jobs: CronJob[] }
    | { type: "job_deleted"; job_id: string; jobs: CronJob[] }
    | { type: "persona"; persona: PersonaData }
    | { type: "persona_saved"; persona: PersonaData }
    | { type: "guardrails"; guardrails: GuardrailsPolicy }
    | { type: "guardrails_saved"; guardrails: GuardrailsPolicy }
    | { type: "agents_status"; agents: AgentStatusInfo[] }
    | { type: "wiped" }
    | { type: "error"; message: string };
