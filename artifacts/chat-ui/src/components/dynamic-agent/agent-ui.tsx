import { ChatMessage } from "./types";
import AgentChatUIInputPanel from "./agent-ui-input-panel";
import AgentChatUIMessageList from "./agent-ui-message-list";
import style from "../../styles/agent-ui.module.scss";

import {
  Button,
  Container,
  Grid,
} from "@cloudscape-design/components";
import { useState } from "react";

export interface ChatUIProps {
  loading?: boolean;
  running?: boolean;
  messages?: ChatMessage[];
  welcomeText?: string;
  inputPlaceholderText?: string;
  sendButtonText?: string;
  showCopyButton?: boolean;
  onSendMessage?: (message: string, type: string) => void;
}

export abstract class ChatScrollState {
  static userHasScrolled = false;
  static skipNextScrollEvent = false;
  static skipNextHistoryUpdate = false;
}

export function AgentUI(props: ChatUIProps) {
  const [clearSocket, setClearSocket] = useState(false);
  const onRenderComplete = () => {
    const element = document.getElementById(style.agent_ui_chat_panel);
    element.scroll(0, element.scrollHeight);
  }
  const onClearSocket = () => {
    setClearSocket(true);
    setTimeout(() => {
      setClearSocket(false);
    }, 1000);
  }

  return (<Container
    fitHeight
    variant="embed"
    footer={<AgentChatUIInputPanel clear_socket={clearSocket} {...props} />}
  > 
    <Grid gridDefinition={[
              { colspan: { default: 10, s: 10 } },
              { colspan: { default: 2, s: 2 } }
            ]}>
              <div></div>
              <div><Button variant="normal" onClick={onClearSocket} ><span>Clear <img width={"25vw"} height={"20vh"} src="https://c.d.cdn.console.awsstatic.com/a/v1/W7RWD4JDJWBK7AFDVNHE6KASCNLZ7RL4OVOJ2PISD567F2XGNHFQ/images/playground/clearButton.svg"></img></span></Button></div>

            </Grid>
    <div id={style.agent_ui_chat_panel} className={style.agent_ui_chat_panel}>
      <AgentChatUIMessageList clear_socket={clearSocket} messages={props.messages} showCopyButton={props.showCopyButton} onRenderComplete={onRenderComplete}/>
    </div>
  </Container>)

}
