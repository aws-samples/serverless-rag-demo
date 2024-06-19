import {
  Button,
  Container,
  SpaceBetween,
  Spinner,
} from "@cloudscape-design/components";
import { useEffect, useLayoutEffect, useState } from "react";
import TextareaAutosize from "react-textarea-autosize";
import { ChatScrollState } from "./chat-ui";
import { ChatMessage, ChatMessageType } from "./types";
import styles from "../../styles/chat-ui.module.scss";
import config from "../../config.json";


export interface ChatUIInputPanelProps {
  inputPlaceholderText?: string;
  sendButtonText?: string;
  running?: boolean;
  messages?: ChatMessage[];
  onSendMessage?: (message: string, type: string) => void;
}

export default function ChatUIInputPanel(props: ChatUIInputPanelProps) {
  const [inputText, setInputText] = useState("");
  const socketUrl = config.websocketUrl;
  const [message, setMessage] = useState('');
  var ws = null; 
  var chat_messages = []

  useEffect(() => {
    const onWindowScroll = () => {
      if (ChatScrollState.skipNextScrollEvent) {
        ChatScrollState.skipNextScrollEvent = false;
        return;
      }

      const isScrollToTheEnd =
        Math.abs(
          window.innerHeight +
            window.scrollY -
            document.documentElement.scrollHeight
        ) <= 10;

      if (!isScrollToTheEnd) {
        ChatScrollState.userHasScrolled = true;
      } else {
        ChatScrollState.userHasScrolled = false;
      }
    };

    window.addEventListener("scroll", onWindowScroll);

    return () => {
      window.removeEventListener("scroll", onWindowScroll);
    };
  }, []);

  useLayoutEffect(() => {
    if (ChatScrollState.skipNextHistoryUpdate) {
      ChatScrollState.skipNextHistoryUpdate = false;
      return;
    }

    if (!ChatScrollState.userHasScrolled && (props.messages ?? []).length > 0) {
      ChatScrollState.skipNextScrollEvent = true;
      window.scrollTo({
        top: document.documentElement.scrollHeight + 1000,
        behavior: "instant",
      });
    }
  }, [props.messages]);

  const onSendMessage = () => {
    ChatScrollState.userHasScrolled = false;
    props.onSendMessage?.(inputText, ChatMessageType.Human);
    setInputText("");

    const access_token = sessionStorage.getItem('accessToken');
    
    if (inputText.trim() !== '') {
      if ("WebSocket" in window) {
        chat_messages.push({"type": "text", "data": inputText})
        if(ws==null || ws.readyState==3 || ws.readyState==2) {
          
          ws = new WebSocket(socketUrl);
          ws.onerror = function (event) {
            console.log(event);
          }
        } else {
          // query_vectordb allowed values -> yes/no
          ws.send(JSON.stringify({ query: btoa(unescape(JSON.stringify(chat_messages))) , behaviour: 'chat', 'query_vectordb': 'yes', 'model_id': 'anthropic.claude-3-haiku-20240307-v1:0' }));
          chat_messages = []
       }
        
        ws.onopen = () => {
          // query_vectordb allowed values -> yes/no
          ws.send(JSON.stringify({ query: btoa(unescape(JSON.stringify(chat_messages))), behaviour: 'chat', 'query_vectordb': 'yes', 'model_id': 'anthropic.claude-3-haiku-20240307-v1:0'}));
          chat_messages = []
        };
        var messages = ''
        ws.onmessage = (event) => {
          var chat_output = JSON.parse(atob(event.data))
          if ('text' in chat_output) {
            messages += chat_output['text']
            if (messages.endsWith('ack-end-of-string')) {
              messages = messages.replace('ack-end-of-string', '')
              props.onSendMessage?.(messages, ChatMessageType.AI);
            }
          } else {
            // Display errors
            props.onSendMessage?.(chat_output, ChatMessageType.AI);
          }
          setMessage("");
        };

        ws.onclose = () => {
          console.log('WebSocket connection closed');
          chat_messages = []
        };

      } else {
        console.log('WebSocket is not supported by your browser.');
        chat_messages = []
      }
    }
  };

  const onTextareaKeyDown = (
    event: React.KeyboardEvent<HTMLTextAreaElement>
  ) => {
    if (!props.running && event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSendMessage();
    }
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      <Container>
        <div className={styles.input_textarea_container}>
          <TextareaAutosize
            className={styles.input_textarea}
            maxRows={6}
            minRows={1}
            spellCheck={true}
            autoFocus
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={onTextareaKeyDown}
            value={inputText}
            placeholder={props.inputPlaceholderText ?? "Send a message"}
          />
          <div style={{ marginLeft: "8px" }}>
            <Button
              disabled={props.running || inputText.trim().length === 0}
              onClick={onSendMessage}
              iconAlign="right"
              iconName={!props.running ? "angle-right-double" : undefined}
              variant="primary"
            >
              {props.running ? (
                <>
                  Loading&nbsp;&nbsp;
                  <Spinner />
                </>
              ) : (
                <>{props.sendButtonText ?? "Send"}</>
              )}
            </Button>
          </div>
        </div>
      </Container>
    </SpaceBetween>
  );
}
