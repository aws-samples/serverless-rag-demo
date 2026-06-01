import { useContext, useState } from "react";
import {
  Box,
  Button,
  Container,
  ExpandableSection,
  Link,
  Popover,
  SpaceBetween,
  Spinner,
  StatusIndicator,
  TextContent,
} from "@cloudscape-design/components";
import remarkGfm from "remark-gfm";
import ReactMarkdown from "react-markdown";
import { ChatMessage, ChatMessageType, SourceInfo } from "./types";
import { AppContext } from "../../common/context";
import { submitFeedback } from "../../common/feedback-service";


export interface ChatUIMessageProps {
  message: ChatMessage;
  showCopyButton?: boolean;
}

function FeedbackButtons({ message }: { message: ChatMessage }) {
  const [rating, setRating] = useState<"up" | "down" | null>(message.rating || null);
  const appData = useContext(AppContext);

  const handleRating = async (value: "up" | "down") => {
    const newRating = rating === value ? null : value;
    setRating(newRating);
    if (!newRating) return;

    const idToken = appData.userinfo?.tokens?.idToken?.toString() || "";
    const userEmail = appData.userinfo?.signInDetails?.loginId || appData.userinfo?.username || "";

    try {
      await submitFeedback({
        timestamp: new Date().toISOString(),
        userEmail,
        question: message.question || "",
        answer: message.content,
        sources: message.sources?.map(s => s.uri) || [],
        rating: newRating,
      }, idToken);
    } catch {
      // Silent fail — don't interrupt chat UX
    }
  };

  return (
    <Box margin={{ top: "xs" }} float="right">
      <SpaceBetween direction="horizontal" size="xs">
        <Button
          variant="inline-icon"
          iconName={rating === "up" ? "thumbs-up-filled" : "thumbs-up"}
          onClick={() => handleRating("up")}
        />
        <Button
          variant="inline-icon"
          iconName={rating === "down" ? "thumbs-down-filled" : "thumbs-down"}
          onClick={() => handleRating("down")}
        />
      </SpaceBetween>
    </Box>
  );
}

function SourcesSection({ sources }: { sources: SourceInfo[] }) {
  return (
    <Box margin={{ top: "m" }}>
      <SpaceBetween size="xs">
        <Box fontWeight="bold" fontSize="body-s">Sources</Box>
        <Box>
          {sources.map((s) => (
            <span key={s.index} style={{ marginRight: "12px" }}>
              {s.presignedUrl ? (
                <Link href={s.presignedUrl} external fontSize="body-s">
                  [{s.index}] {s.fileName}
                </Link>
              ) : (
                <span>[{s.index}] {s.fileName}</span>
              )}
            </span>
          ))}
        </Box>
        {sources.some((s) => s.excerpt) && (
          <ExpandableSection headerText="Citations" variant="footer">
            <SpaceBetween size="xs">
              {sources.filter((s) => s.excerpt).map((s) => (
                <Box key={s.index} padding="xs" variant="code" fontSize="body-s">
                  <Box fontWeight="bold">[{s.index}] {s.fileName}</Box>
                  <Box color="text-body-secondary">
                    {s.excerpt!.length > 300 ? `${s.excerpt!.slice(0, 300)}...` : s.excerpt}
                  </Box>
                </Box>
              ))}
            </SpaceBetween>
          </ExpandableSection>
        )}
      </SpaceBetween>
    </Box>
  );
}

export default function ChatUIMessage(props: ChatUIMessageProps) {
  return (
    <div>
      {props.message?.type === ChatMessageType.AI && (
        <Container>
          {props.message.content.length === 0 ? (
            <Box>
              <Spinner />
            </Box>
          ) : null}
          {props.message.content.length > 0 &&
          props.showCopyButton !== false ? (
            <div>
              <Popover
                size="medium"
                position="top"
                triggerType="custom"
                dismissButton={false}
                content={
                  <StatusIndicator type="success">
                    Copied to clipboard
                  </StatusIndicator>
                }
              >
                <Button
                  variant="inline-icon"
                  iconName="copy"
                  onClick={() => {
                    navigator.clipboard.writeText(props.message.content);
                  }}
                />
              </Popover>
            </div>
          ) : null}
          <ReactMarkdown
            children={props.message.content}
            remarkPlugins={[remarkGfm]}
            components={{
              a(props) {
                const { children, href, ...rest } = props;
                return (
                  <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
                    {children}
                  </a>
                );
              },
              pre(props) {
                const { children, ...rest } = props;
                return (
                  <pre {...rest}>
                    {children}
                  </pre>
                );
              },
              table(props) {
                const { children, ...rest } = props;
                return (
                  <table {...rest}>
                    {children}
                  </table>
                );
              },
              th(props) {
                const { children, ...rest } = props;
                return (
                  <th {...rest}>
                    {children}
                  </th>
                );
              },
              td(props) {
                const { children, ...rest } = props;
                return (
                  <td {...rest}>
                    {children}
                  </td>
                );
              },
            }}
          />
          {props.message.sources && props.message.sources.length > 0 && (
            <SourcesSection sources={props.message.sources} />
          )}
          {props.message.content.length > 0 && (
            <FeedbackButtons message={props.message} />
          )}
        </Container>
      )}
      {props.message?.type === ChatMessageType.Human && (
        <TextContent>
          <strong>{props.message.content}</strong>
        </TextContent>
      )}
    </div>
  );
}
