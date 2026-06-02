import { useState } from "react";
import {
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
