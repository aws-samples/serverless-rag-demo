import { useEffect , useState} from "react";
import { ChatMessage } from "./types";
import AgentChatUIInputPanel from "./agent-ui-input-panel";
import AgentChatUIMessageList from "./agent-ui-message-list";
import style from "../../styles/agent-ui.module.scss";

import {
  Container,
} from "@cloudscape-design/components";

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
  const onRenderComplete = () => {
    const element = document.getElementById(style.agent_ui_chat_panel);
    element.scroll(0, element.scrollHeight);
  }
  return (<Container
    fitHeight
    variant="embed"
    footer={<AgentChatUIInputPanel {...props} />}
  >
    <div id={style.agent_ui_chat_panel} className={style.agent_ui_chat_panel}>
      <AgentChatUIMessageList messages={props.messages} showCopyButton={props.showCopyButton} onRenderComplete={onRenderComplete}/>
    </div>
  </Container>)

}
