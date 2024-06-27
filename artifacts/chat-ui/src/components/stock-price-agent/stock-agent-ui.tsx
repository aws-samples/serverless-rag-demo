import { StatusIndicator } from "@cloudscape-design/components";
import { ChatMessage } from "./types";
import ChatUIInputPanel from "./stock-agent-ui-input-panel";
import { useEffect } from "react";
import ChatUIMessageList from "./stock-agent-ui-message-list";
import styles from "../../styles/chat-ui.module.scss";
import ButtonDropdown from "@cloudscape-design/components/button-dropdown";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import Toggle from "@cloudscape-design/components/toggle";
import * as React from "react";

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

export function StockAgentUI(props: ChatUIProps) {
  const [checked, setChecked] = React.useState(false);
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
    <div className={styles.chat_container}>
      <ColumnLayout columns={4}>
        <div><ButtonDropdown
          items={[
            { text: "Claude 3 Haiku", id: "claude-3-haiku", disabled: false },
            { text: "Claude 3 Sonnet", id: "claude-3-sonnet", disabled: false },
            { text: "Claude 3 Opus", id: "claude-3-opus", disabled: true },
          ]}
        >
          Models
        </ButtonDropdown></div>


        <div> <ButtonDropdown
          items={[
            { text: "English", id: "english", disabled: false },
            { text: "Hindi", id: "hindi", disabled: false },
            { text: "Thai", id: "thai", disabled: false },
            { text: "French", id: "french", disabled: false },
            { text: "Arabic", id: "arabic", disabled: false },
            { text: "Gujarati", id: "gujarati", disabled: false },
          ]}
        >
          Language
        </ButtonDropdown></div>

        <div>
          <Toggle
            onChange={({ detail }) =>
              setChecked(detail.checked)
            }
            checked={checked}
          >
            Query Vector Store
          </Toggle>
        </div>



      </ColumnLayout>


      <ChatUIMessageList
        messages={props.messages}
        showCopyButton={props.showCopyButton}
      />
      <div className={styles.welcome_text}>
        {props.messages?.length === 0 && !props.loading && (
          <center>{props.welcomeText ?? "ChatBot"}</center>
        )}
        {props.loading && (
          <center>
            <StatusIndicator type="loading">Loading</StatusIndicator>
          </center>
        )}
      </div>
      <div className={styles.input_container}>
        <ChatUIInputPanel {...props} />
      </div>
    </div>
  );
}
