import { useState, useEffect } from "react";
import { ChatUI } from "../components/chat-ui/chat-ui";
import { ChatMessage, ChatMessageType } from "../components/chat-ui/types";
import { withAuthenticator } from '@aws-amplify/ui-react';
import {
  Container,
  ContentLayout,
  Header,
} from "@cloudscape-design/components";

import { AuthHelper } from "../common/helpers/auth-help";
import { AppPage } from "../common/types";

function ChatPage(props: AppPage) {
  const [running, setRunning] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  useEffect(() => {
    const init = async () => {
      let userdata = await AuthHelper.getUserDetails();
      props.setAppData({
        userinfo: userdata
      })
    }
    init();
  },[])

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
    <ContentLayout
      defaultPadding
      headerVariant="high-contrast"
      header={
        <Header
          variant="h1"
          description="App description will come here"
        >
          Document Chat
        </Header>
      }
    >
      <Container fitHeight
      >
        <ChatUI
          onSendMessage={sendMessage}
          messages={messages}
          running={running}
        />
      </Container>
    </ContentLayout>
  );
}

export default withAuthenticator(ChatPage)