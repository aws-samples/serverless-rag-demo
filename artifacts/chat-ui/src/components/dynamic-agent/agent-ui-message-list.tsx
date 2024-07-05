import { SpaceBetween } from "@cloudscape-design/components";
import { ChatMessage } from "./types";
import AgentChatUIMessage from "./agent-message";
import { useEffect } from "react";

export interface AgentChatUIMessageListProps {
  messages?: ChatMessage[];
  showCopyButton?: boolean;
  onRenderComplete?: () => void;
}

export default function AgentChatUIMessageList(props: AgentChatUIMessageListProps) {
  const messages = props.messages || [];
  useEffect(() => {
    if (props.onRenderComplete) {
      props.onRenderComplete();
    }
  })
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
