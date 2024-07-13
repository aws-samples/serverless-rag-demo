import { SpaceBetween } from "@cloudscape-design/components";
import { ChatMessage } from "./types";
import AgentChatUIMessage from "./agent-message";
import { useEffect, useState } from "react";

export interface AgentChatUIMessageListProps {
  messages?: ChatMessage[];
  showCopyButton?: boolean;
  onRenderComplete?: () => void;
  clear_socket?: boolean;
}

export default function AgentChatUIMessageList(props: AgentChatUIMessageListProps) {
  const messages = props.messages || [];
  useEffect(() => {
    if (props.onRenderComplete) {
      props.onRenderComplete();
    }
  })

  useEffect(() => {
    if (props.clear_socket) {
      messages.splice(0, messages.length)
    }
  }, [props.clear_socket]);

  return (
    <SpaceBetween direction="vertical" size="m">
      {messages.map((message, idx) => (
        <AgentChatUIMessage
          key={idx}
          message={message}
          showCopyButton={props.showCopyButton}
        />
      ))}
    </SpaceBetween>
  );
}
