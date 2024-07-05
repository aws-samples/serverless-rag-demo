import { useEffect, useState } from "react";
import { Container } from "@cloudscape-design/components";
import { ChatMessage } from "./types";
import ChatUIInputPanel from "./chat-ui-input-panel";
import ChatUIMessageList from "./chat-ui-message-list";
import style from "../../styles/chat-ui.module.scss";

export interface ChatUIProps {
  loading?: boolean;
  running?: boolean;
  messages?: ChatMessage[];
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
  const onRenderComplete = () => {
    const element = document.getElementById(style.doc_ui_chat_panel);
    element.scroll(0, element.scrollHeight);
  }
  return (
    <Container fitHeight variant="embed" footer={<ChatUIInputPanel {...props} />} >
      <div id={style.doc_ui_chat_panel} className={style.doc_ui_chat_panel}>
        <ChatUIMessageList messages={props.messages} showCopyButton={props.showCopyButton} onRenderComplete={onRenderComplete} />
      </div>
    </Container>
  );
}
