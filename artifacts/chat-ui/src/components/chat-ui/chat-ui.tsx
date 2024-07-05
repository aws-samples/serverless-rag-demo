import { useEffect, useState } from "react";
import { Container } from "@cloudscape-design/components";
import { ChatMessage } from "./types";
import ChatUIInputPanel from "./chat-ui-input-panel";
import ChatUIMessageList from "./chat-ui-message-list";

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
  const [checked, setChecked] = useState(false);
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

  return (
    <Container
      fitHeight
      variant="embed"
      footer={<ChatUIInputPanel {...props} />}
    >
      <div className="documentChatPanel">
      <ChatUIMessageList
        messages={props.messages}
        showCopyButton={props.showCopyButton}
      />
      </div>
    </Container>
  );
}
