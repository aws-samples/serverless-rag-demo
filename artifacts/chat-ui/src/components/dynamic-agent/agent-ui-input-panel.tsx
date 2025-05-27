import {
  Button,
  Container,
  SpaceBetween,
  Spinner, Textarea, Grid
} from "@cloudscape-design/components";
import { useContext, useEffect, useLayoutEffect, useState } from "react";
import { ChatScrollState } from "./agent-ui";
import { ChatMessage, ChatMessageType } from "./types";
import config from "../../config.json";
import { AppContext } from "../../common/context";

var ws = null;
var agent_prompt_flow = []

export interface AgentChatUIInputPanelProps {
  inputPlaceholderText?: string;
  sendButtonText?: string;
  running?: boolean;
  messages?: ChatMessage[];
  clear_socket?: boolean;
  onSendMessage?: (message: string, type: string) => void;
}

export default function AgentChatUIInputPanel(props: AgentChatUIInputPanelProps) {
  const [inputText, setInputText] = useState("");
  const socketUrl = config.websocketUrl;
  const [message, setMessage] = useState('');
  const [isDisabled, setDisabled] = useState(false)
  const appData = useContext(AppContext);

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

  useEffect(() => {
    if (props.clear_socket) {
      ws=null;
      agent_prompt_flow=[]
      setDisabled(false)
    }
  }, [props.clear_socket]);

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
    if (inputText.trim() !== '') {
      if ("WebSocket" in window) {
        setDisabled(true)
        agent_prompt_flow.push({ 'role': 'user', 'content': [{ "type": "text", "text": inputText }] })
        if (ws == null || ws.readyState == 3 || ws.readyState == 2) {
          var idToken = appData.userinfo.tokens.idToken.toString()
          ws = new WebSocket(socketUrl + "?access_token=" + idToken);
          ws.onerror = function (event) {
            console.log(event);
            setDisabled(false);
          }
        } else {
          ws.send(JSON.stringify({ query: (JSON.stringify(agent_prompt_flow)), behaviour: 'advanced-agent', 'query_vectordb': 'yes', 'model_id': 'anthropic.claude-3-haiku-20240307-v1:0' }));
        }

        ws.onopen = () => {
          ws.send(JSON.stringify({ query: (JSON.stringify(agent_prompt_flow)), behaviour: 'advanced-agent', 'query_vectordb': 'yes', 'model_id': 'anthropic.claude-3-haiku-20240307-v1:0' }));
        };
        
        ws.onmessage = (event) => {
          if (event.data) {
            var decodedMessage = ""
            try{
               decodedMessage = atob(event.data);
            }
            catch(e){
              // If decoding fails, use the original message
              decodedMessage = event.data;
            }
            try {
              const parsedMessage = JSON.parse(decodedMessage);
              const messageText = parsedMessage.text || parsedMessage;
              const cleanMessage = messageText.replace(/""/g, '"');
              props.onSendMessage?.(cleanMessage, ChatMessageType.AI);
            } catch (e) {
              // If parsing fails, just use the decoded message
              const cleanMessage = decodedMessage.replace(/""/g, '"');
              props.onSendMessage?.(cleanMessage, ChatMessageType.AI);
            }
            setDisabled(false);
          }
        };

        ws.onclose = () => {
          console.log('WebSocket connection closed');
          agent_prompt_flow = []
        };
      } else {
        console.log('WebSocket is not supported by your browser.');
        agent_prompt_flow = []
      }
    }
  };

  function capitalizeFirstLetter(val) {
    return val.charAt(0).toUpperCase() + val.slice(1);
  }

  const OnTextareaKeyDown = (event) => {
    if (!props.running && event.detail.key === "Enter" && !event.detail.shiftKey) {
      event.preventDefault()
      onSendMessage();
    }
  }
  return (
    <Container disableContentPaddings disableHeaderPaddings variant="stacked">
      <SpaceBetween size="s">
        <Textarea
          spellcheck={true}
          rows={3}
          autoFocus
          onKeyDown={(event) => OnTextareaKeyDown(event)}
          onChange={({ detail }) => setInputText(detail.value)}
          value={inputText}
          placeholder={props.inputPlaceholderText ?? "Send a message"}
        />
        <Button
          disabled={props.running || isDisabled || inputText.trim().length === 0}
          onClick={onSendMessage}
          iconAlign="right"
          iconName={!props.running ? "angle-right-double" : undefined}
          variant="primary" >
          {props.running ? (
            <>
              Loading&nbsp;&nbsp;
              <Spinner />
            </>
          ) : (
            <>{props.sendButtonText ?? "Send"}</>
          )}
        </Button>
      </SpaceBetween>
    </Container>
  );
}
