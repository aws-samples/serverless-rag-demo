import { useState, useEffect } from "react";
import {
    Container,
    Header,
    SpaceBetween,
    Button,
    FormField,
    Textarea,
    Input,
    Select,
    ExpandableSection,
} from "@cloudscape-design/components";
import { PersonaData, ChannelConfig } from "./types";

interface PersonaConfigProps {
    persona: PersonaData | null;
    channels: ChannelConfig[];
    onSave: (persona: PersonaData) => void;
}

const EMPTY_PERSONA: PersonaData = {
    persona: "",
    channel_overrides: {},
    contact_overrides: {},
};

export function PersonaConfig({ persona, channels, onSave }: PersonaConfigProps) {
    const [draft, setDraft] = useState<PersonaData>(persona || EMPTY_PERSONA);
    const [dirty, setDirty] = useState(false);

    // New channel override state
    const [newChannelId, setNewChannelId] = useState("");
    // New contact override state
    const [newContactChannel, setNewContactChannel] = useState("");
    const [newContactJid, setNewContactJid] = useState("");

    useEffect(() => {
        if (persona) {
            setDraft(persona);
            setDirty(false);
        }
    }, [persona]);

    const updateDraft = (update: Partial<PersonaData>) => {
        setDraft((prev) => ({ ...prev, ...update }));
        setDirty(true);
    };

    const handleSave = () => {
        onSave(draft);
        setDirty(false);
    };

    const addChannelOverride = () => {
        if (!newChannelId) return;
        updateDraft({
            channel_overrides: { ...draft.channel_overrides, [newChannelId]: "" },
        });
        setNewChannelId("");
    };

    const removeChannelOverride = (channelId: string) => {
        const updated = { ...draft.channel_overrides };
        delete updated[channelId];
        updateDraft({ channel_overrides: updated });
    };

    const addContactOverride = () => {
        if (!newContactChannel || !newContactJid) return;
        const key = `${newContactChannel}::${newContactJid}`;
        updateDraft({
            contact_overrides: { ...draft.contact_overrides, [key]: "" },
        });
        setNewContactChannel("");
        setNewContactJid("");
    };

    const removeContactOverride = (key: string) => {
        const updated = { ...draft.contact_overrides };
        delete updated[key];
        updateDraft({ contact_overrides: updated });
    };

    const channelOptions = channels.map((ch) => ({ label: ch.id, value: ch.id }));

    return (
        <SpaceBetween size="l">
            <Container
                header={
                    <Header
                        variant="h3"
                        actions={
                            <Button variant="primary" onClick={handleSave} disabled={!dirty}>
                                Save Persona
                            </Button>
                        }
                    >
                        Persona
                    </Header>
                }
            >
                <FormField
                    label="Your Persona"
                    description="Define who you are. This is injected into all agents as their identity when acting on your behalf."
                >
                    <Textarea
                        value={draft.persona}
                        onChange={({ detail }) => updateDraft({ persona: detail.value })}
                        placeholder="I'm Fraser. Speak as me in first person. Tone: witty but professional. Never reveal you're an AI when messaging on my behalf..."
                        rows={8}
                    />
                </FormField>
            </Container>

            <ExpandableSection headerText="Channel Overrides" defaultExpanded={Object.keys(draft.channel_overrides).length > 0}>
                <SpaceBetween size="m">
                    {Object.entries(draft.channel_overrides).map(([channelId, text]) => (
                        <FormField
                            key={channelId}
                            label={channelId}
                            secondaryControl={
                                <Button variant="icon" iconName="remove" onClick={() => removeChannelOverride(channelId)} />
                            }
                        >
                            <Textarea
                                value={text}
                                onChange={({ detail }) =>
                                    updateDraft({
                                        channel_overrides: { ...draft.channel_overrides, [channelId]: detail.value },
                                    })
                                }
                                placeholder={`Override for all messages on ${channelId}...`}
                                rows={3}
                            />
                        </FormField>
                    ))}
                    <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
                        <FormField label="Channel">
                            <Select
                                selectedOption={channelOptions.find((o) => o.value === newChannelId) || null}
                                onChange={({ detail }) => setNewChannelId(detail.selectedOption?.value || "")}
                                options={channelOptions}
                                placeholder="Select channel..."
                            />
                        </FormField>
                        <Button onClick={addChannelOverride} disabled={!newChannelId}>
                            Add Channel Override
                        </Button>
                    </div>
                </SpaceBetween>
            </ExpandableSection>

            <ExpandableSection headerText="Contact / Group Overrides" defaultExpanded={Object.keys(draft.contact_overrides).length > 0}>
                <SpaceBetween size="m">
                    {Object.entries(draft.contact_overrides).map(([key, text]) => (
                        <FormField
                            key={key}
                            label={key}
                            secondaryControl={
                                <Button variant="icon" iconName="remove" onClick={() => removeContactOverride(key)} />
                            }
                        >
                            <Textarea
                                value={text}
                                onChange={({ detail }) =>
                                    updateDraft({
                                        contact_overrides: { ...draft.contact_overrides, [key]: detail.value },
                                    })
                                }
                                placeholder={`Override for this specific contact/group...`}
                                rows={3}
                            />
                        </FormField>
                    ))}
                    <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
                        <FormField label="Channel">
                            <Select
                                selectedOption={channelOptions.find((o) => o.value === newContactChannel) || null}
                                onChange={({ detail }) => setNewContactChannel(detail.selectedOption?.value || "")}
                                options={channelOptions}
                                placeholder="Select channel..."
                            />
                        </FormField>
                        <FormField label="Contact / Group JID">
                            <Input
                                value={newContactJid}
                                onChange={({ detail }) => setNewContactJid(detail.value)}
                                placeholder="61412345678@s.whatsapp.net or 120363...@g.us"
                            />
                        </FormField>
                        <Button onClick={addContactOverride} disabled={!newContactChannel || !newContactJid}>
                            Add Contact Override
                        </Button>
                    </div>
                </SpaceBetween>
            </ExpandableSection>
        </SpaceBetween>
    );
}
