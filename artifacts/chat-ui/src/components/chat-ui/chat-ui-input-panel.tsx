import {
  Button,
  Container,
  SpaceBetween,
  Spinner, Textarea
} from "@cloudscape-design/components";
import { useEffect, useLayoutEffect, useState, useContext } from "react";
import { ChatScrollState } from "./chat-ui";
import { ChatMessage, ChatMessageType } from "./types";
import { AppContext } from "../../common/context";
import { getRuntimeConfig } from "../../runtime-config";
import { createAgentCoreWebSocket, AgentCoreMessage } from "../../common/agentcore-ws";
import { getDownloadPresignedUrl } from "../../common/document-service";

let ws: WebSocket | null = null;
let chatHistory: { role: string; content: string }[] = [];
let streamedText = "";
let collectedSources: any[] = [];

export interface ChatUIInputPanelProps {
  inputPlaceholderText?: string;
  sendButtonText?: string;
  running?: boolean;
  messages?: ChatMessage[];
  selected_model_option?: string;
  check_vector_db?: boolean;
  is_hybrid_search?: boolean;
  clear_socket?: boolean;
  onSendMessage?: (message: string, type: string, sources?: any[]) => void;
  userinfo?: any;
  notify_parent?: (message: string, notify_type: string) => void;
}

export default function ChatUIInputPanel(props: ChatUIInputPanelProps) {
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

  const notify = (message: string, notify_type: string) => {
    props.notify_parent?.(message, notify_type);
  };

  const onSendMessage = async () => {
    if (inputText.trim() === "") return;

    ChatScrollState.userHasScrolled = false;
    props.onSendMessage?.(inputText, ChatMessageType.Human);
    const query = inputText;
    setInputText("");

    if (!("WebSocket" in window)) {
      notify("WebSocket is not supported by your browser.", "error");
      return;
    }

    setDisabled(true);
    streamedText = "";
    collectedSources = [];
    chatHistory.push({ role: "user", content: query });

    const sendQuery = () => {
      const searchScope = props.check_vector_db ? "user" : "all";
      const searchType = props.is_hybrid_search ? "HYBRID" : "SEMANTIC";
      ws!.send(JSON.stringify({
        query,
        model_id: props.selected_model_option,
        search_scope: searchScope,
        search_type: searchType,
        chat_history: chatHistory.slice(-10),
      }));
    };

    const handleMessage = (msg: AgentCoreMessage) => {
      switch (msg.type) {
        case "start":
          break;
        case "sources":
          if (msg.sources && msg.sources.length > 0) {
            // Accumulate sources (may arrive multiple times with citations)
            for (const s of msg.sources) {
              const isDupe = collectedSources.some((existing) => existing.uri === s.uri);
              if (!isDupe) collectedSources.push(s);
            }
          }
          break;
        case "token":
          streamedText += msg.text || "";
          props.onSendMessage?.(streamedText, ChatMessageType.AI);
          break;
        case "end":
          chatHistory.push({ role: "assistant", content: streamedText });
          if (collectedSources.length > 0) {
            const idToken = appData.userinfo?.tokens?.idToken?.toString() || "";
            const sources = [...collectedSources];
            collectedSources = [];
            (async () => {
              const resolvedSources = await Promise.all(sources.map(async (s: any, idx: number) => {
                const uri: string = s.uri || "";
                const match = uri.match(/^s3:\/\/[^/]+\/(.+)$/);
                const key = match ? match[1] : "";
                const fileName = key ? decodeURIComponent(key.split("/").pop() || `Source ${idx + 1}`) : `Source ${idx + 1}`;
                let presignedUrl = "";
                if (key) {
                  try {
                    presignedUrl = await getDownloadPresignedUrl(key, idToken);
                  } catch { /* ignore */ }
                }
                return {
                  index: idx + 1,
                  uri,
                  excerpt: s.excerpt || "",
                  presignedUrl,
                  fileName,
                };
              }));
              props.onSendMessage?.(streamedText, ChatMessageType.AI, resolvedSources);
              setDisabled(false);
            })();
          } else {
            setDisabled(false);
          }
          break;
        case "error":
          notify(msg.message || "Unknown error", "error");
          setDisabled(false);
          break;
        default:
          break;
      }
    };

    const handleError = (error: string) => {
      notify(error, "error");
      setDisabled(false);
    };

    const handleClose = () => {
      ws = null;
      setDisabled(false);
    };

    // Connect or reuse existing connection
    if (ws == null || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
      try {
        const config = getRuntimeConfig();
        const idToken = appData.userinfo.tokens.idToken.toString();
        ws = await createAgentCoreWebSocket(
          config.ragRuntimeArn,
          idToken,
          handleMessage,
          handleError,
          handleClose,
        );
        ws.onopen = () => sendQuery();
      } catch (err: any) {
        notify(`Connection failed: ${err.message}`, "error");
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
    <Container disableContentPaddings disableHeaderPaddings variant="embed">
      <SpaceBetween size="s">
        <Textarea
          spellcheck={true}
          rows={2}
          autoFocus
          onKeyDown={(event) => OnTextareaKeyDown(event)}
          onChange={({ detail }) => setInputText(detail.value)}
          value={inputText}
          placeholder={props.inputPlaceholderText ?? "Send a message"}
        />
        <SpaceBetween size="s" direction="horizontal">
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
      </SpaceBetween>
    </Container>
  );
}
