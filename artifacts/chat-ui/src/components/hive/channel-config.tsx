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
