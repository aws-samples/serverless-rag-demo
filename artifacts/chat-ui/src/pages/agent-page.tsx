import { useState, useEffect } from "react";
import { AgentUI } from "../components/dynamic-agent/agent-ui";
import { ChatMessage, ChatMessageType } from "../components/dynamic-agent/types";
import { AuthHelper } from "../common/helpers/auth-help";
import { withAuthenticator } from '@aws-amplify/ui-react';
import {
  Container,
  ContentLayout,
  Header,
} from "@cloudscape-design/components";
import { AppPage } from "../common/types";

function AgentPage(props: AppPage) {
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
      setMessages((prevMessages) => {
        const lastMessage = prevMessages[prevMessages.length - 1];
        lastMessage.content += message;
        return [...prevMessages];
      });
      setRunning(false);
    }
  };
  return (
    <ContentLayout
      defaultPadding
      headerVariant="high-contrast"
      header={
        <Header
          variant="h1"
          description="Gen AI agents that assist with content writing/App generation/Presentations and much more"
        >
          Multi Agent
        </Header>
      }
    >
      <Container fitHeight
      >
        <AgentUI
          onSendMessage={sendMessage}
          messages={messages}
          running={running}
        />
      </Container>
    </ContentLayout>
  );
}

export default withAuthenticator(AgentPage)