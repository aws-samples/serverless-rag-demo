import { SpaceBetween } from "@cloudscape-design/components";
import { ChatMessage } from "./types";
import ChatUIMessage from "./chat-ui-message";
import { useEffect } from "react";

export interface ChatUIMessageListProps {
  messages?: ChatMessage[];
  showCopyButton?: boolean;
  onRenderComplete?: () => void;
  clear_socket?: boolean;
}

export default function ChatUIMessageList(props: ChatUIMessageListProps) {
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
        <ChatUIMessage
          key={idx}
          message={message}
          showCopyButton={props.showCopyButton}
        />
      ))}
    </SpaceBetween>
  );
}
