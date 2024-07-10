import { Button, Container, Grid } from "@cloudscape-design/components";
import { ChatMessage } from "./types";
import ChatUIInputPanel from "./chat-ui-input-panel";
import ChatUIMessageList from "./chat-ui-message-list";
import style from "../../styles/chat-ui.module.scss";
import { useState } from "react";

export interface ChatUIProps {
  loading?: boolean;
  running?: boolean;
  messages?: ChatMessage[];
  selected_model_option?: string;
  selected_language?: string;
  check_vector_db?: boolean;
  welcomeText?: string;
  inputPlaceholderText?: string;
  sendButtonText?: string;
  showCopyButton?: boolean;
  onSendMessage?: (message: string, type: string) => void;
  userinfo?: any;
}

export abstract class ChatScrollState {
  static userHasScrolled = false;
  static skipNextScrollEvent = false;
  static skipNextHistoryUpdate = false;
}

export function ChatUI(props: ChatUIProps) {
  const [clearSocket, setClearSocket] = useState(false);
  const onRenderComplete = () => {
    const element = document.getElementById(style.doc_ui_chat_panel);
    element.scroll(0, element.scrollHeight);
  }
  const onClearSocket = () => {
    setClearSocket(true);
    setTimeout(() => {
      setClearSocket(false);
    }, 1000);
  }
  return (
    <Container fitHeight variant="embed" footer={<ChatUIInputPanel clear_socket={clearSocket} {...props} />} >
          <Grid gridDefinition={[
              { colspan: { default: 10, s: 10 } },
              { colspan: { default: 2, s: 2 } }
            ]}>
              <div></div>
              <div><Button variant="normal" onClick={onClearSocket} ><span>Clear <img width={"25vw"} height={"20vh"} src="https://c.d.cdn.console.awsstatic.com/a/v1/W7RWD4JDJWBK7AFDVNHE6KASCNLZ7RL4OVOJ2PISD567F2XGNHFQ/images/playground/clearButton.svg"></img></span></Button></div>

            </Grid>
            
      <div id={style.doc_ui_chat_panel} className={style.doc_ui_chat_panel}>
        <ChatUIMessageList clear_socket={clearSocket} messages={props.messages} showCopyButton={props.showCopyButton} onRenderComplete={onRenderComplete} />
      </div>
    </Container>
  );
}
