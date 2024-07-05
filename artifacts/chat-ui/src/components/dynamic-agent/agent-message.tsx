import { Box, Button, Container, Popover, Spinner, StatusIndicator, TextContent} from "@cloudscape-design/components";
import remarkGfm from "remark-gfm";
import ReactMarkdown from "react-markdown";
import { ChatMessage, ChatMessageType } from "./types";
import AgentChatFileReader from "./agent-file-reader";
export interface AgentChatUIMessageProps {
  message: ChatMessage;
  showCopyButton?: boolean;
}

const regex = /<location>(.+?)<\/location>/;           
export default function AgentChatUIMessage(props: AgentChatUIMessageProps) {
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
                    if(props.message.content.includes('<location>')){
                      const match = props.message.content.match(regex);
                      const url = match[1];
                      navigator.clipboard.writeText(url);
                    }
                    else
                      navigator.clipboard.writeText(props.message.content);
                  }}
                />
              </Popover>
            </div>
          ) : null}
          {props.message.content.includes('<location>') ? (<AgentChatFileReader content={props.message.content}/>) : (<ReactMarkdown
            children={props.message.content}
            remarkPlugins={[remarkGfm]}
            components={{
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
                  <td {...rest} >
                    {children}
                  </td>
                );
              },
            }}
          />)}
          
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
