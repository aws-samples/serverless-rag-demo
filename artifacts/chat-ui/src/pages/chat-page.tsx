import { useState, useEffect } from "react";
import { ChatUI } from "../components/chat-ui/chat-ui";
import { ChatMessage, ChatMessageType } from "../components/chat-ui/types";
import { withAuthenticator } from '@aws-amplify/ui-react';
import {
  Container,
  ContentLayout,
  Header, Button, Modal, Grid, SpaceBetween, Select, FormField, Toggle
} from "@cloudscape-design/components";

import { AuthHelper } from "../common/helpers/auth-help";
import { AppPage } from "../common/types";
import style from "../styles/chat-ui.module.scss";

function ChatPage(props: AppPage) {
  const [running, setRunning] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedLanguage, setSelectedLanguage] = useState({ label: "English", value: "english" })
  const [checkVectorDb, setCheckVectorDb] = useState(false);
  const [selectedModelOption, setSelectedModelOption] = useState({
    label: "Claude 3 Haiku v1",
    value: "claude_3_haiku_v1",
    iconName: "keyboard",
    description: "Text & vision model | Context size = up to 200k",
    tags: ["Anthropic"],
    labelTag: "Text & Vision"
  });

  useEffect(() => {
    const init = async () => {
      let userdata = await AuthHelper.getUserDetails();
      props.setAppData({
        userinfo: userdata
      })
    }
    init();
  }, [])

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
  };

  return (
    <ContentLayout
      defaultPadding
      headerVariant="high-contrast"
      header={
        <Header
          variant="h1"
          description="Retrieval Augmented Generation"
          actions={<Button iconName="settings" variant="icon" onClick={() => setModalVisible(true)} />}
        >Document Chat</Header>
      }
    >
      <Container fitHeight
      >
        <ChatUI
          onSendMessage={sendMessage}
          messages={messages}
          running={running}
        />
        <Modal
          size="large"
          onDismiss={() => setModalVisible(false)}
          visible={modalVisible}
          header="Document Chat Configuration"
        >
          <hr />
          <Grid gridDefinition={[
            { colspan: { default: 12, xs: 6, s: 6 } },
            { colspan: { default: 12, xs: 6, s: 6 } }]} >
            <Container className={style.doc_ui_page_config_col}
              fitHeight
              header={<Header variant="h3">Preference</Header>}>
              <SpaceBetween size="m">
                <FormField label="Model">
                  <Select
                    selectedOption={selectedModelOption}
                    onChange={({ detail }) =>
                      setSelectedModelOption(detail.selectedOption)
                    }
                    options={[
                      {
                        label: "Claude 3 Haiku v1",
                        value: "claude_3_haiku_v1",
                        iconName: "keyboard",
                        description: "Text & vision model | Context size = up to 200k",
                        tags: ["Anthropic"],
                        labelTag: "Text & Vision"
                      },
                      {
                        label: "Claude 3 Sonnet v1",
                        value: "claude_3_sonnet_v1",
                        iconName: "keyboard",
                        description: "Text & vision model | Context size = up to 200k",
                        tags: ["Anthropic"],
                        labelTag: "Text & Vision"
                      },
                      {
                        label: "Claude 3 Opus v1",
                        value: "claude_3_opus_v1",
                        disabled: true,
                        iconName: "keyboard",
                        description: "Text & vision model | Context size = up to 200k",
                        tags: ["Anthropic"],
                        labelTag: "Text & Vision"
                      }
                    ]}
                    expandToViewport
                    triggerVariant="option"
                  />
                </FormField>

                <FormField label="Language">
                  <Select
                    selectedOption={selectedLanguage}
                    onChange={({ detail }) =>
                      setSelectedLanguage(detail.selectedOption)
                    }
                    options={[
                      { label: "English", value: "english" },
                      { label: "Hindi", value: "hindi" },
                      { label: "Thai", value: "thai" },
                      { label: "French", value: "french" },
                      { label: "Arabic", value: "arabic" },
                      { label: "Gujarati", value: "gujarati" }
                    ]}
                    expandToViewport
                  />
                </FormField>

                <Toggle
                  onChange={({ detail }) =>
                    setCheckVectorDb(detail.checked)
                  }
                  checked={checkVectorDb}
                >
                  Query Vector Store
                </Toggle>

              </SpaceBetween>
            </Container>
            <Container className={style.doc_ui_page_config_col} fitHeight header={<Header variant="h3">Documents</Header>}>
            </Container>
          </Grid>
        </Modal>
      </Container>
    </ContentLayout>
  );
}

export default withAuthenticator(ChatPage)