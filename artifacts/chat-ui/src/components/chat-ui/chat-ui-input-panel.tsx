import {
  Button,
  Container,
  FileUpload,
  Grid,
  SpaceBetween,
  Spinner,Textarea
} from "@cloudscape-design/components";
import { useEffect, useLayoutEffect, useState } from "react";
import { ChatScrollState } from "./chat-ui";
import { ChatMessage, ChatMessageType } from "./types";
import config from "../../config.json";

var ws = null; 
var agent_prompt_flow = []
var msgs = null

export interface ChatUIInputPanelProps {
  inputPlaceholderText?: string;
  sendButtonText?: string;
  running?: boolean;
  messages?: ChatMessage[];
  onSendMessage?: (message: string, type: string) => void;
  userinfo?: any;
}

export default function ChatUIInputPanel(props: ChatUIInputPanelProps) {
  const [inputText, setInputText] = useState("");
  const [value, setValue] = useState<File[]>([]);
  const socketUrl = config.websocketUrl;
  
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

    //const access_token = props.userinfo.tokens.accessToken.toString();
    
    if (inputText.trim() !== '') {
      if ("WebSocket" in window) {
        if (msgs){
          agent_prompt_flow.push({ 'role': 'assistant', 'content': [{"type": "text", "text": msgs}] }) 
          msgs=null 
        }
        agent_prompt_flow.push({ 'role': 'user', 'content': [{"type": "text", "text": inputText}] })
        if(ws==null || ws.readyState==3 || ws.readyState==2) {
          
          ws = new WebSocket(socketUrl);
          ws.onerror = function (event) {
            console.log(event);
          }
        } else {
          // query_vectordb allowed values -> yes/no
          ws.send(JSON.stringify({ query: JSON.stringify(agent_prompt_flow) , behaviour: 'advanced-rag-agent', 'query_vectordb': 'yes', 'model_id': 'anthropic.claude-3-haiku-20240307-v1:0' }));
          
       }
        
        ws.onopen = () => {
          // query_vectordb allowed values -> yes/no
          ws.send(JSON.stringify({ query: JSON.stringify(agent_prompt_flow), behaviour: 'advanced-rag-agent', 'query_vectordb': 'yes', 'model_id': 'anthropic.claude-3-haiku-20240307-v1:0'}));
          
        };
        
        ws.onmessage = (event) => { 
          if (event.data.includes('message')) {
            var evt_json = JSON.parse(event.data)
            props.onSendMessage?.(evt_json['message'], ChatMessageType.AI);
          } 
          else {
            var chat_output = JSON.parse(atob(event.data))
          if ('text' in chat_output) {
            if (msgs) {
              msgs += chat_output['text']
            } else {
              msgs = chat_output['text']
            }
            
            if (msgs.endsWith('ack-end-of-msg')) {
              msgs = msgs.replace('ack-end-of-msg', '')
            }
            props.onSendMessage?.(msgs, ChatMessageType.AI);
          } else {
            // Display errors
            props.onSendMessage?.(chat_output, ChatMessageType.AI);
          }
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

  return (<Container disableContentPaddings disableHeaderPaddings variant="embed">
      <Grid gridDefinition={[
        { colspan: { xxs:6, xs:8, s:8, m:10, l:10, xl:10} } ,
        { colspan: { xxs:6, xs:4, s:4, m:2, l:2, xl:2} }]} >
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
          disabled={props.running || inputText.trim().length === 0}
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
      </Grid>
  </Container>);
}