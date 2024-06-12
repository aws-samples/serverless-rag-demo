import { useState } from "react";
import BaseAppLayout from "../components/base-app-layout";
import { UploadUI } from "../components/upload-ui/upload-ui";
import { ChatMessage, ChatMessageType } from "../components/chat-ui/types";
import axios from "axios";

export default function UploadPage() {
  const [running, setRunning] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const sendMessage = (message: string) => {
    setRunning(true);
    setMessages((prevMessages) => [
      ...prevMessages,
      { type: ChatMessageType.Human, content: message },
      {
        type: ChatMessageType.AI,
        content: "",
      },
    ]);

    setTimeout(() => {
      setMessages((prevMessages) => [
        ...prevMessages.splice(0, prevMessages.length - 1),
        {
          type: ChatMessageType.AI,
          content:
            "I am a chatbot. Please try to connect me to Amazon Bedrock.",
        },
      ]);

      setRunning(false);
    }, 1000);
  };

  return (
    <BaseAppLayout
      content={
        <UploadUI/>
      }
    />
  );
}
