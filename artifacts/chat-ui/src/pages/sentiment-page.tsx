import { useState, useEffect } from "react";
import {
  Container,
  ContentLayout,
  Header,
  Button, Modal, Toggle, FormField, Select,Link,
  SpaceBetween,
} from "@cloudscape-design/components";
import { withAuthenticator } from '@aws-amplify/ui-react';
import { AppPage } from "../common/types";
import { AuthHelper } from "../common/helpers/auth-help";
import Textarea from "@cloudscape-design/components/textarea";
import * as React from "react"
import { AppContext } from "../common/context";
import config from "../config.json";
import defaultConfig from "../default-properties.json";

const default_customer_review = defaultConfig["sentiment"]["defaultReview"]
const default_sentiment_placeholder = defaultConfig["sentiment"]["defaultSentiment"]
const documentConfig = defaultConfig["document-chat"]["config"]
var ws = null
var msgs = null
function SentimentPage(props: AppPage) {
  const [value, setValue] = React.useState(default_customer_review);
  const [modalVisible, setModalVisible] = useState(false)
  const [selectedLanguage, setSelectedLanguage] = useState(documentConfig["languages"][0])
  const [checkVectorDb, setCheckVectorDb] = useState(true);
  const [selectedModelOption, setSelectedModelOption] = useState(documentConfig["models"][0]);
  const [out, setOut] = React.useState("");
  const appData = React.useContext(AppContext);
  const socketUrl = config.websocketUrl;
  useEffect(() => {
    const init = async () => {
      let userdata = await AuthHelper.getUserDetails();
      props.setAppData({
        userinfo: userdata
      })
    }
    init();
  }, [])

  const onSubmitReview = () => {
    if ("WebSocket" in window) {
      if (value.length > 0) {
        setOut("")
        msgs = null
        send_over_socket()
      }
    }
  }

  const send_over_socket = () => {
    if (ws == null || ws.readyState == 3 || ws.readyState == 2) {
      let idToken = appData.userinfo.tokens.idToken.toString();
      ws = new WebSocket(socketUrl + "?access_token=" + idToken);
      ws.onerror = function (event) {
        console.log(event);
      };
    } else {

      ws.send(JSON.stringify({
        query: JSON.stringify([{ "role": "user", "content": [{ "type": "text", "text": value }] }]),
        behaviour: 'sentiment',
        'query_vectordb': checkVectorDb,
        'model_id': selectedModelOption.value
      }));
    }

    ws.onopen = () => {
      ws.send(JSON.stringify({
        query: JSON.stringify([{ "role": "user", "content": [{ "type": "text", "text": value }] }]),
        behaviour: 'sentiment',
        'query_vectordb': checkVectorDb,
        'model_id': selectedModelOption.value
      }));

    };

    ws.onmessage = (event) => {
      if (event.data.includes('message')) {
        var evt_json = JSON.parse(event.data);
        setOut(out + evt_json['message'])
      }
      else {
        var chat_output = JSON.parse(atob(event.data));
        if ('text' in chat_output) {
          if (msgs) {
            msgs += chat_output['text'];
          } else {
            msgs = chat_output['text'];
          }

          if (msgs.endsWith('ack-end-of-msg')) {
            msgs = msgs.replace('ack-end-of-msg', '');
            setOut(msgs)
            msgs = null
          }

        } else {
          // Display errors
          setOut(chat_output)
        }
      }

    }
  }

  return (
    <ContentLayout
      defaultPadding
      headerVariant="high-contrast"
      header={
        <Header
          variant="h1"
          description="App description will come here"
          actions={<Button iconName="settings" variant="icon" onClick={() => setModalVisible(true)} />}
        >
          Sentiment Analysis<Link variant="primary" onClick={() => setModalVisible(true)}> ({selectedModelOption.label}) </Link>
        </Header>
      }
    >
      <Container fitHeight >
        <Container variant="embed"
          header={
            <Header variant="h3"
              actions={<Button iconAlign="right" onClick={onSubmitReview} variant="primary" >Submit </Button>}>
              Customer Review
            </Header>
          }>
          <SpaceBetween size="l"><Textarea
            onChange={({ detail }) => setValue(detail.value)}
            value={value}
            placeholder={default_customer_review}
            rows={15}
          />
            <Textarea
              readOnly={true}
              value={out}
              placeholder={default_sentiment_placeholder}
              rows={8}
            /></SpaceBetween>
        </Container>
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

export default withAuthenticator(SentimentPage)