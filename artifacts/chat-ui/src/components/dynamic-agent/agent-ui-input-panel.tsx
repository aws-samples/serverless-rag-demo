import {
  Button,
  Container,
  SpaceBetween,
  Spinner, Textarea, Grid
} from "@cloudscape-design/components";
import { useEffect, useLayoutEffect, useState } from "react";
import { ChatScrollState } from "./agent-ui";
import { ChatMessage, ChatMessageType } from "./types";
import config from "../../config.json";

var ws = null;
var agent_prompt_flow = []

export interface AgentChatUIInputPanelProps {
  inputPlaceholderText?: string;
  sendButtonText?: string;
  running?: boolean;
  messages?: ChatMessage[];
  onSendMessage?: (message: string, type: string) => void;
}

export default function AgentChatUIInputPanel(props: AgentChatUIInputPanelProps) {
  const [inputText, setInputText] = useState("");
  const socketUrl = config.websocketUrl;
  const [message, setMessage] = useState('');

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
        agent_prompt_flow.push({ 'role': 'user', 'content': [{ "type": "text", "text": inputText }] })
        if (ws == null || ws.readyState == 3 || ws.readyState == 2) {

          ws = new WebSocket(socketUrl);
          ws.onerror = function (event) {
            console.log(event);
          }
        } else {
          // query_vectordb allowed values -> yes/no
          ws.send(JSON.stringify({ query: (JSON.stringify(agent_prompt_flow)), behaviour: 'advanced-agent', 'query_vectordb': 'yes', 'model_id': 'anthropic.claude-3-haiku-20240307-v1:0' }));
        }

        ws.onopen = () => {
          // query_vectordb allowed values -> yes/no
          ws.send(JSON.stringify({ query: (JSON.stringify(agent_prompt_flow)), behaviour: 'advanced-agent', 'query_vectordb': 'yes', 'model_id': 'anthropic.claude-3-haiku-20240307-v1:0' }));

        };
        var messages = ''
        var thought = ''
        ws.onmessage = (event) => {
          if (event.data.includes('message')) {
            var evt_json = JSON.parse(event.data)
            props.onSendMessage?.(evt_json['message'], ChatMessageType.AI);
          }
          else {
            var response_details = JSON.parse(atob(event.data))
            console.log(response_details);
            if ('intermediate_execution' in response_details) {
              props.onSendMessage?.(response_details['intermediate_execution'], ChatMessageType.AI);
              //props.onSendMessage?.("", ChatMessageType.AI);
            }
            else if ('prompt_flow' in response_details) {
              var is_done = Boolean(response_details['done'])
              if (!is_done) {
                agent_prompt_flow = []
                for (var k = 0; k < response_details['prompt_flow'].length; k++) {
                  var prompt_content_list = response_details['prompt_flow'][k]['content']
                  var content = []
                  for (var j = 0; j < prompt_content_list.length; j++) {
                    if ('text' in prompt_content_list[j]) {
                      content.push({ "type": "text", "text": prompt_content_list[j]['text'] })
                    } else {
                      content.push(prompt_content_list[j])
                    }
                  }
                  agent_prompt_flow.push({ "role": response_details['prompt_flow'][k]['role'], "content": content })
                }

                for (var i = 0; i < response_details['prompt_flow'].length; i++) {
                  if ('content' in response_details['prompt_flow'][i]) {
                    var content_list = response_details['prompt_flow'][i]['content']
                    for (var j = 0; j < content_list.length; j++) {
                      if ('text' in content_list[j]) {
                        thought = thought + capitalizeFirstLetter(response_details['prompt_flow'][i]['role']) + ': ' + content_list[j]['text']
                      } else {
                        thought = thought + capitalizeFirstLetter(response_details['prompt_flow'][i]['role']) + ': ' + content_list[j]
                      }
                    }
                  }
                }
                messages = thought.replace('ack-end-of-string', '')
                props.onSendMessage?.(messages, ChatMessageType.AI);
              } else {
                if (response_details['prompt_flow'].length > 0) {

                  var last_element = response_details['prompt_flow'][response_details['prompt_flow'].length - 1]
                  if ('content' in last_element) {
                    var content_list = last_element['content']
                    var content = []
                    for (var j = 0; j < content_list.length; j++) {
                      if ('text' in content_list[j]) {
                        content.push({ "type": "text", "text": content_list[j]['text'] })
                        thought = thought + capitalizeFirstLetter(last_element['role']) + ': ' + content_list[j]['text']
                      } else {
                        content.push(content_list[j])
                        thought = thought + capitalizeFirstLetter(last_element['role']) + ': ' + content_list[j]
                      }
                    }
                    agent_prompt_flow.push({ "role": last_element['role'], "content": content })

                    messages = thought.replace('ack-end-of-msg', '')

                    props.onSendMessage?.(messages, ChatMessageType.AI);
                  }
                }
              }

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
      <Grid gridDefinition={[{ colspan: 11 }, { colspan: 1 }]} >
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
