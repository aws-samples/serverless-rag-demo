import { useState } from "react";
import BaseAppLayout from "../components/base-app-layout";
import { ChatUI } from "../components/chat-ui/chat-ui";
import { ChatMessage, ChatMessageType } from "../components/chat-ui/types";

export default function ChatPage() {
  const [running, setRunning] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  
  const sendMessage = (message: string, type: string) => {
    if (type === ChatMessageType.Human) {
      setMessages((prevMessages) => [
        ...prevMessages,
        { type: ChatMessageType.Human, content: message },
        {
          type: ChatMessageType.AI,
          content: "",
        },
      ]);
    } else if (type === ChatMessageType.AI) {
        setMessages((prevMessages) => [
          ...prevMessages.splice(0, prevMessages.length - 1),
          {
            type: ChatMessageType.AI,
            content: message,
          },
        ]);
        setRunning(false);
    }


    // setTimeout(() => {
    //   setMessages((prevMessages) => [
    //     ...prevMessages.splice(0, prevMessages.length - 1),
    //     {
    //       type: ChatMessageType.AI,
    //       content:
    //         "I am a chatbot. Please try to connect me to Amazon Bedrock.",
    //     },
    //   ]);

    //   setRunning(false);
    // }, 1000);

  };

  return (
    <BaseAppLayout
      content={
        <ChatUI
          onSendMessage={sendMessage}
          messages={messages}
          running={running}
        />
      }
    />
  );
}
