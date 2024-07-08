import { useState, useEffect } from "react";
import { ChatUI } from "../components/chat-ui/chat-ui";
import { UploadUI } from "../components/upload-ui/upload-ui";
import { ChatMessage, ChatMessageType } from "../components/chat-ui/types";
import { withAuthenticator } from '@aws-amplify/ui-react';
import Link from "@cloudscape-design/components/link";
import {
  Container,
  ContentLayout,
  Header, Button, Modal, SpaceBetween, Select, FormField, Toggle
} from "@cloudscape-design/components";

import { AuthHelper } from "../common/helpers/auth-help";
import { AppPage } from "../common/types";
import defaultConfig from "../default-properties.json";
import style from "../styles/chat-ui.module.scss";

const documentConfig = defaultConfig["document-chat"]["config"]
function ChatPage(props: AppPage) {
  const [running, setRunning] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedLanguage, setSelectedLanguage] = useState(documentConfig["languages"][0])
  const [checkVectorDb, setCheckVectorDb] = useState(true);
  const [selectedModelOption, setSelectedModelOption] = useState(documentConfig["models"][0]);

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
          description="Query your knowledge sources through natural language"
          actions={<Button iconName="settings" variant="icon" onClick={() => setModalVisible(true)} />}
        >Document Chat<Link variant="primary" onClick={() => setModalVisible(true)}> ({selectedModelOption.label}) </Link>
        </Header>
      }
    >
      <Container fitHeight
      >
        {
          (props.manageDocument?<UploadUI/>:<ChatUI
          onSendMessage={sendMessage}
          messages={messages}
          running={running}
          selected_model_option={selectedModelOption.value}
          selected_language={selectedLanguage.value}
          check_vector_db={checkVectorDb}
        />)
        }
        
        <Modal
          size="medium"
          onDismiss={() => setModalVisible(false)}
          visible={modalVisible}
          header="Preference"
        >

          <Container
            fitHeight>
            <SpaceBetween size="m">
              <FormField label="Model">
                <Select
                  selectedOption={selectedModelOption}
                  onChange={({ detail }) =>
                    setSelectedModelOption(detail.selectedOption)
                  }
                  options={documentConfig["models"]}
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
                  options={documentConfig["languages"]}
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
        </Modal>
      </Container>
    </ContentLayout>
  );
}

export default withAuthenticator(ChatPage)