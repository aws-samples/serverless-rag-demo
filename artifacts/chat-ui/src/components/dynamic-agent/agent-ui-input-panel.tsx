import {
  Button,
  Container,
  SpaceBetween,
  Spinner, Textarea
} from "@cloudscape-design/components";
import { useContext, useEffect, useLayoutEffect, useState } from "react";
import { ChatScrollState } from "./agent-ui";
import { ChatMessage, ChatMessageType } from "./types";
import { AppContext } from "../../common/context";
import { getRuntimeConfig } from "../../runtime-config";
import { createAgentCoreWebSocket, AgentCoreMessage } from "../../common/agentcore-ws";

let ws: WebSocket | null = null;
let chatHistory: { role: string; content: string }[] = [];
let streamedText = "";

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
  const [isDisabled, setDisabled] = useState(false);
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
      ChatScrollState.userHasScrolled = !isScrollToTheEnd;
    };
    window.addEventListener("scroll", onWindowScroll);
    return () => window.removeEventListener("scroll", onWindowScroll);
  }, []);

  useEffect(() => {
    if (props.clear_socket) {
      if (ws) {
        ws.close();
        ws = null;
      }
      chatHistory = [];
      streamedText = "";
      setDisabled(false);
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

  const onSendMessage = async () => {
    if (inputText.trim() === "") return;

    ChatScrollState.userHasScrolled = false;
    props.onSendMessage?.(inputText, ChatMessageType.Human);
    const query = inputText;
    setInputText("");

    if (!("WebSocket" in window)) {
      console.log("WebSocket is not supported by your browser.");
      return;
    }

    setDisabled(true);
    streamedText = "";
    chatHistory.push({ role: "user", content: query });

    const sendQuery = () => {
      ws!.send(JSON.stringify({
        query,
        chat_history: chatHistory.slice(-10),
      }));
    };

    const handleMessage = (msg: AgentCoreMessage) => {
      switch (msg.type) {
        case "start":
          break;
        case "intent":
          props.onSendMessage?.(`[${msg.intent}]`, ChatMessageType.AI);
          break;
        case "sources":
          if (msg.sources && msg.sources.length > 0) {
            const sourceText = msg.sources.map((s: any) =>
              `[${s.title || s.uri || "Source"}](${s.uri || "#"})`
            ).join(" | ");
            props.onSendMessage?.(`Sources: ${sourceText}`, ChatMessageType.AI);
          }
          break;
        case "token":
          streamedText += msg.text || "";
          props.onSendMessage?.(streamedText, ChatMessageType.AI);
          break;
        case "result":
          props.onSendMessage?.(msg.text || JSON.stringify(msg), ChatMessageType.AI);
          setDisabled(false);
          break;
        case "end":
          chatHistory.push({ role: "assistant", content: streamedText });
          setDisabled(false);
          break;
        case "error":
          props.onSendMessage?.(msg.message || "Unknown error", ChatMessageType.AI);
          setDisabled(false);
          break;
        default:
          break;
      }
    };

    const handleError = (error: string) => {
      props.onSendMessage?.(error, ChatMessageType.AI);
      setDisabled(false);
    };

    const handleClose = () => {
      ws = null;
      setDisabled(false);
    };

    if (ws == null || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
      try {
        const config = getRuntimeConfig();
        const idToken = appData.userinfo.tokens.idToken.toString();
        ws = await createAgentCoreWebSocket(
          config.multiAgentRuntimeArn,
          idToken,
          handleMessage,
          handleError,
          handleClose,
        );
        ws.onopen = () => sendQuery();
      } catch (err: any) {
        props.onSendMessage?.(`Connection failed: ${err.message}`, ChatMessageType.AI);
        setDisabled(false);
      }
    } else {
      sendQuery();
    }
  };

  const OnTextareaKeyDown = (event: any) => {
    if (!props.running && event.detail.key === "Enter" && !event.detail.shiftKey) {
      event.preventDefault();
      onSendMessage();
    }
  };

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
          variant="primary">
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
