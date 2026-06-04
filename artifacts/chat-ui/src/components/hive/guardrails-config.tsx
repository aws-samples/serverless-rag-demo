import { useState, useEffect } from "react";
import {
    Container,
    Header,
    SpaceBetween,
    Button,
    FormField,
    Textarea,
    Input,
    Toggle,
    Alert,
    Modal,
    ExpandableSection,
    StatusIndicator,
    Box,
    Checkbox,
} from "@cloudscape-design/components";
import { GuardrailsPolicy } from "./types";

interface GuardrailsConfigProps {
    guardrails: GuardrailsPolicy | null;
    onSave: (g: GuardrailsPolicy) => void;
}

const ACTION_LABELS: Record<string, string> = {
    send_to_any: "Send to third parties",
    send_to_sender: "Reply to sender",
    read_history: "Read message history",
    disclose_contacts: "Reveal contacts",
    disclose_conversations: "Share conversations",
    schedule_jobs: "Schedule jobs",
    execute_code: "Execute code",
    modify_config: "Modify configuration",
    impersonate_owner: "Speak as owner",
    unknown_tool: "Use unmapped tools",
};

const HARM_DESCRIPTIONS: Record<string, string> = {
    send_to_any: "Anyone in this tier can instruct your AI to send messages to other people as you. This could be used to impersonate you.",
    read_history: "Anyone in this tier can read your conversations with other contacts.",
    disclose_contacts: "Anyone in this tier can discover who you communicate with.",
    disclose_conversations: "Anyone in this tier can access the content of your private conversations.",
    execute_code: "Anyone in this tier can run arbitrary code on your Hive container.",
    modify_config: "Anyone in this tier can change your Hive configuration, including adding/removing channels.",
    impersonate_owner: "Anyone in this tier can make your AI speak as you in first person.",
    unknown_tool: "Anyone in this tier can use any new/unmapped tool — this is a catch-all that could expose future capabilities.",
    schedule_jobs: "Anyone in this tier can create recurring tasks that run on your behalf.",
};

const DEFAULT_POLICIES: Record<string, Record<string, boolean>> = {
    owner: {
        send_to_any: true,
        send_to_sender: true,
        read_history: true,
        disclose_contacts: true,
        disclose_conversations: true,
        schedule_jobs: true,
        execute_code: true,
        modify_config: true,
        impersonate_owner: true,
        unknown_tool: true,
    },
    trusted: {
        send_to_any: false,
        send_to_sender: true,
        read_history: false,
        disclose_contacts: false,
        disclose_conversations: false,
        schedule_jobs: false,
        execute_code: false,
        modify_config: false,
        impersonate_owner: false,
        unknown_tool: false,
    },
    known: {
        send_to_any: false,
        send_to_sender: true,
        read_history: false,
        disclose_contacts: false,
        disclose_conversations: false,
        schedule_jobs: false,
        execute_code: false,
        modify_config: false,
        impersonate_owner: false,
        unknown_tool: false,
    },
    stranger: {
        send_to_any: false,
        send_to_sender: false,
        read_history: false,
        disclose_contacts: false,
        disclose_conversations: false,
        schedule_jobs: false,
        execute_code: false,
        modify_config: false,
        impersonate_owner: false,
        unknown_tool: false,
    },
};

const EMPTY_GUARDRAILS: GuardrailsPolicy = {
    version: 1,
    enabled: true,
    tiers: {
        trusted: { description: "Close contacts you fully trust", contacts: [] },
        known: { description: "Known contacts with limited access", contacts: [] },
    },
    policies: DEFAULT_POLICIES,
    refusal_message: "I'm not able to do that for you. This action requires owner-level permission.",
};

export function GuardrailsConfig({ guardrails, onSave }: GuardrailsConfigProps) {
    const [draft, setDraft] = useState<GuardrailsPolicy>(guardrails || EMPTY_GUARDRAILS);
    const [dirty, setDirty] = useState(false);
    const [pendingEnable, setPendingEnable] = useState<{ action: string; tier: string } | null>(null);
    const [riskAcknowledged, setRiskAcknowledged] = useState(false);
    const [showResetModal, setShowResetModal] = useState(false);
    const [newContactInputs, setNewContactInputs] = useState<Record<string, string>>({});

    useEffect(() => {
        if (guardrails) {
            setDraft(guardrails);
            setDirty(false);
        }
    }, [guardrails]);

    const updateDraft = (update: Partial<GuardrailsPolicy>) => {
        setDraft((prev) => ({ ...prev, ...update }));
        setDirty(true);
    };

    const handleSave = () => {
        onSave(draft);
        setDirty(false);
    };

    const handleTogglePermission = (action: string, tier: string, checked: boolean) => {
        if (checked && !draft.policies[tier]?.[action]) {
            // Enabling a permission - show warning
            setPendingEnable({ action, tier });
            setRiskAcknowledged(false);
        } else {
            // Disabling - no confirmation needed
            applyPermissionChange(action, tier, checked);
        }
    };

    const applyPermissionChange = (action: string, tier: string, checked: boolean) => {
        const updatedPolicies = { ...draft.policies };
        updatedPolicies[tier] = { ...updatedPolicies[tier], [action]: checked };
        updateDraft({ policies: updatedPolicies });
    };

    const confirmEnable = () => {
        if (pendingEnable) {
            applyPermissionChange(pendingEnable.action, pendingEnable.tier, true);
            setPendingEnable(null);
            setRiskAcknowledged(false);
        }
    };

    const handleReset = () => {
        // Reset policies to defaults but preserve contact assignments
        updateDraft({ policies: DEFAULT_POLICIES });
        setShowResetModal(false);
    };

    const addContact = (tier: string) => {
        const jid = newContactInputs[tier]?.trim();
        if (!jid) return;
        const updatedTiers = { ...draft.tiers };
        updatedTiers[tier] = {
            ...updatedTiers[tier],
            contacts: [...(updatedTiers[tier]?.contacts || []), jid],
        };
        updateDraft({ tiers: updatedTiers });
        setNewContactInputs((prev) => ({ ...prev, [tier]: "" }));
    };

    const removeContact = (tier: string, jid: string) => {
        const updatedTiers = { ...draft.tiers };
        updatedTiers[tier] = {
            ...updatedTiers[tier],
            contacts: updatedTiers[tier].contacts.filter((c) => c !== jid),
        };
        updateDraft({ tiers: updatedTiers });
    };

    const actions = Object.keys(ACTION_LABELS);
    const tiers = ["owner", "trusted", "known", "stranger"];

    return (
        <SpaceBetween size="l">
            {/* Status Banner */}
            <Container
                header={
                    <Header
                        variant="h3"
                        actions={
                            <SpaceBetween direction="horizontal" size="s">
                                <Button onClick={() => setShowResetModal(true)}>Reset to Defaults</Button>
                                <Button variant="primary" onClick={handleSave} disabled={!dirty || !!pendingEnable}>
                                    Save Guardrails
                                </Button>
                            </SpaceBetween>
                        }
                    >
                        Guardrails
                    </Header>
                }
            >
                <SpaceBetween size="s">
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <StatusIndicator type={draft.enabled ? "success" : "stopped"}>
                            {draft.enabled ? "Guardrails Active" : "Guardrails Disabled"}
                        </StatusIndicator>
                        <Toggle
                            checked={draft.enabled}
                            onChange={({ detail }) => updateDraft({ enabled: detail.checked })}
                        >
                            {draft.enabled ? "Enabled" : "Disabled"}
                        </Toggle>
                    </div>
                </SpaceBetween>
            </Container>

            {/* Pending Enable Warning */}
            {pendingEnable && (
                <Alert
                    type="warning"
                    header={`Enable "${ACTION_LABELS[pendingEnable.action]}" for ${pendingEnable.tier}?`}
                    action={
                        <SpaceBetween direction="horizontal" size="s">
                            <Button onClick={() => { setPendingEnable(null); setRiskAcknowledged(false); }}>
                                Cancel
                            </Button>
                            <Button variant="primary" onClick={confirmEnable} disabled={!riskAcknowledged}>
                                Confirm
                            </Button>
                        </SpaceBetween>
                    }
                >
                    <SpaceBetween size="s">
                        <Box>{HARM_DESCRIPTIONS[pendingEnable.action] || "This action may have security implications."}</Box>
                        <Toggle
                            checked={riskAcknowledged}
                            onChange={({ detail }) => setRiskAcknowledged(detail.checked)}
                        >
                            I understand the risks
                        </Toggle>
                    </SpaceBetween>
                </Alert>
            )}

            {/* Action Permission Matrix */}
            <Container header={<Header variant="h3">Action Permission Matrix</Header>}>
                <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                        <thead>
                            <tr>
                                <th style={{ textAlign: "left", padding: "8px 12px", borderBottom: "1px solid #e9ebed" }}>
                                    Action
                                </th>
                                {tiers.map((tier) => (
                                    <th key={tier} style={{ textAlign: "center", padding: "8px 12px", borderBottom: "1px solid #e9ebed", textTransform: "capitalize" }}>
                                        {tier}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {actions.map((action) => (
                                <tr key={action}>
                                    <td style={{ padding: "6px 12px", borderBottom: "1px solid #f2f3f3" }}>
                                        {ACTION_LABELS[action]}
                                    </td>
                                    {tiers.map((tier) => (
                                        <td key={tier} style={{ textAlign: "center", padding: "6px 12px", borderBottom: "1px solid #f2f3f3" }}>
                                            <Checkbox
                                                checked={draft.policies[tier]?.[action] ?? false}
                                                disabled={tier === "owner"}
                                                onChange={({ detail }) => handleTogglePermission(action, tier, detail.checked)}
                                            />
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </Container>

            {/* Tier Contact Lists */}
            {["trusted", "known"].map((tier) => (
                <ExpandableSection
                    key={tier}
                    headerText={`${tier.charAt(0).toUpperCase() + tier.slice(1)} Contacts (${draft.tiers[tier]?.contacts?.length || 0})`}
                    defaultExpanded={(draft.tiers[tier]?.contacts?.length || 0) > 0}
                >
                    <SpaceBetween size="s">
                        <Box color="text-body-secondary">{draft.tiers[tier]?.description || ""}</Box>
                        {(draft.tiers[tier]?.contacts || []).map((jid) => (
                            <div key={jid} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <Box variant="code">{jid}</Box>
                                <Button variant="icon" iconName="remove" onClick={() => removeContact(tier, jid)} />
                            </div>
                        ))}
                        <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
                            <FormField label="JID">
                                <Input
                                    value={newContactInputs[tier] || ""}
                                    onChange={({ detail }) => setNewContactInputs((prev) => ({ ...prev, [tier]: detail.value }))}
                                    placeholder="61412345678@s.whatsapp.net"
                                />
                            </FormField>
                            <Button onClick={() => addContact(tier)} disabled={!newContactInputs[tier]?.trim()}>
                                Add
                            </Button>
                        </div>
                    </SpaceBetween>
                </ExpandableSection>
            ))}

            {/* Refusal Message */}
            <Container header={<Header variant="h3">Refusal Message</Header>}>
                <FormField
                    label="Message shown when an action is denied"
                    description="This is sent to contacts when they request an action they don't have permission for."
                >
                    <Textarea
                        value={draft.refusal_message}
                        onChange={({ detail }) => updateDraft({ refusal_message: detail.value })}
                        rows={3}
                    />
                </FormField>
            </Container>

            {/* Reset Confirmation Modal */}
            <Modal
                visible={showResetModal}
                onDismiss={() => setShowResetModal(false)}
                header="Reset Guardrails to Defaults"
                footer={
                    <Box float="right">
                        <SpaceBetween direction="horizontal" size="xs">
                            <Button variant="link" onClick={() => setShowResetModal(false)}>Cancel</Button>
                            <Button variant="primary" onClick={handleReset}>Reset</Button>
                        </SpaceBetween>
                    </Box>
                }
            >
                <Box>
                    This will reset all action permissions to their default values. Your contact assignments (trusted/known lists) will be preserved.
                </Box>
            </Modal>
        </SpaceBetween>
    );
}
