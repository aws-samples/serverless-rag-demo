import { useState, useEffect } from "react";
import { ChatUI } from "../components/chat-ui/chat-ui";
import { UploadUI } from "../components/upload-ui/upload-ui";
import { ChatMessage, ChatMessageType } from "../components/chat-ui/types";
import { withAuthenticator } from '@aws-amplify/ui-react';
import Link from "@cloudscape-design/components/link";
import {
  Container,
  ContentLayout,
  Header, Button, Modal, SpaceBetween, FormField, Toggle, Alert, Select
} from "@cloudscape-design/components";
import { ModelSelector } from "../components/ModelSelector";

import { AuthHelper } from "../common/helpers/auth-help";
import { AppPage } from "../common/types";
import defaultConfig from "../default-properties.json";
import style from "../styles/chat-ui.module.scss";
import { transformModels } from "../utils/modelRegionTransformer";

interface Model {
  label: string;
  value: string;
}

interface Language {
  label: string;
  value: string;
}

const documentConfig = defaultConfig["document-chat"]["config"]
function ChatPage(props: AppPage) {
  const [running, setRunning] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedLanguage, setSelectedLanguage] = useState<Language>(documentConfig["languages"][0])
  const [isHybridSearch, setHybridSearch] = useState(false)
  const [checkVectorDb, setCheckVectorDb] = useState(true);
  const [selectedModelOption, setSelectedModelOption] = useState<Model>(transformModels(documentConfig["models"])[0]);
  const [showAlert, setShowAlert] = useState(false)
  const [alertMsg, setAlertMsg] = useState("")
  const [alertType, setAlertType] = useState("error")

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

  const handle_notifications = (message, notify_type) => {
    setAlertMsg(message)
    setAlertType(notify_type)
    setShowAlert(true)
  }

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
      <Container fitHeight>
      {(showAlert && alertType=='error') ? <Alert dismissible statusIconAriaLabel="Error" type='error' onDismiss={() => setShowAlert(false)}>{alertMsg}</Alert> : ""}
      {(showAlert && alertType=='success') ? <Alert dismissible statusIconAriaLabel="Success" type='success' onDismiss={() => setShowAlert(false)}>{alertMsg}</Alert> : ""}
      {(showAlert && alertType=='warning') ? <Alert dismissible statusIconAriaLabel="Warning" type='warning' onDismiss={() => setShowAlert(false)}>{alertMsg}</Alert> : ""}
      {(showAlert && alertType=='info') ? <Alert dismissible statusIconAriaLabel="Info" type='info' onDismiss={() => setShowAlert(false)}>{alertMsg}</Alert> : ""}
        {
          (props.manageDocument?<UploadUI notify_parent={handle_notifications}/>:<ChatUI
          onSendMessage={sendMessage}
          notify_parent={handle_notifications} 
          messages={messages}
          running={running}
          selected_model_option={selectedModelOption.value}
          selected_language={selectedLanguage.value}
          check_vector_db={checkVectorDb}
          is_hybrid_search={isHybridSearch}
        />)
        }
        
        <Modal
          size="medium"
          onDismiss={() => setModalVisible(false)}
          visible={modalVisible}
          header="Preference"
        >
          <Container fitHeight>
            <SpaceBetween size="m">
              <FormField label="Model">
                <ModelSelector
                  selectedModel={selectedModelOption}
                  onModelSelect={setSelectedModelOption}
                />
              </FormField>

              <FormField label="Language">
                <Select
                  selectedOption={selectedLanguage}
                  onChange={({ detail }) =>
                    setSelectedLanguage(detail.selectedOption as Language)
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
              
              <Toggle
                onChange={({ detail }) =>
                  setHybridSearch(detail.checked)
                }
                checked={isHybridSearch}
              >
                Enable Hybrid Search(Beta)
              </Toggle>

            </SpaceBetween>
          </Container>
        </Modal>
      </Container>
    </ContentLayout>
  );
}

export default withAuthenticator(ChatPage)