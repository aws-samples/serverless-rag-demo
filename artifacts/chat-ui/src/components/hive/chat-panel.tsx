import { useState, useRef, useEffect } from "react";
import {
    Container,
    SpaceBetween,
    Button,
    Textarea,
    Box,
    Badge,
    ExpandableSection,
} from "@cloudscape-design/components";

interface ChatMessage {
    id: string;
    role: "user" | "agent" | "system";
    content: string;
    agent_id?: string;
    agent_name?: string;
    timestamp: number;
    thinking?: string;
}

interface ChatPanelProps {
    messages: ChatMessage[];
    onSend: (message: string) => void;
    isLoading: boolean;
    activeAgent: string | null;
}

export function ChatPanel({ messages, onSend, isLoading, activeAgent }: ChatPanelProps) {
    const [input, setInput] = useState("");
    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const handleSend = () => {
        if (!input.trim() || isLoading) return;
        onSend(input.trim());
        setInput("");
    };

    return (
        <Container>
            <SpaceBetween size="s">
                {/* Messages */}
                <div style={{ maxHeight: 400, overflowY: "auto", padding: "8px 0" }}>
                    {messages.map((msg) => (
                        <div
                            key={msg.id}
                            style={{
                                marginBottom: 12,
                                padding: "8px 12px",
                                borderRadius: 8,
                                background: msg.role === "user" ? "#0972d311" : "#f2f3f3",
                            }}
                        >
                            <Box>
                                <SpaceBetween size="xxs" direction="horizontal">
                                    <Box fontWeight="bold" fontSize="body-s">
                                        {msg.role === "user" ? "You" : msg.agent_name || "System"}
                                    </Box>
                                    {msg.agent_id && (
                                        <Badge color="blue">{msg.agent_id}</Badge>
                                    )}
                                </SpaceBetween>
                            </Box>
                            <Box variant="p" margin={{ top: "xxs" }}>
                                {msg.content}
                            </Box>
                            {msg.thinking && (
                                <ExpandableSection headerText="Thought process" variant="footer">
                                    <Box variant="code" fontSize="body-s">
                                        {msg.thinking}
                                    </Box>
                                </ExpandableSection>
                            )}
                        </div>
                    ))}
                    {isLoading && activeAgent && (
                        <div style={{ padding: "8px 12px", color: "#5f6b7a" }}>
                            <Badge color="green">{activeAgent}</Badge> is thinking...
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                {/* Input */}
                <div style={{ display: "flex", gap: 8 }}>
                    <div style={{ flex: 1 }}>
                        <Textarea
                            value={input}
                            onChange={({ detail }) => setInput(detail.value)}
                            placeholder="Message your agents..."
                            rows={2}
                            disabled={isLoading}
                        />
                    </div>
                    <Button
                        variant="primary"
                        onClick={handleSend}
                        disabled={!input.trim() || isLoading}
                        iconName="send"
                    >
                        Send
                    </Button>
                </div>
            </SpaceBetween>
        </Container>
    );
}
