import { HelpPanel } from "@cloudscape-design/components";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { HelpPage } from "../common/types";
import config from "../help-properties.json";

// The help text is bundled markdown rather than HTML so that rendering it never
// needs dangerouslySetInnerHTML: react-markdown ignores raw HTML by default, so
// there is no path from this panel to script execution.
export default function Help(props: HelpPage) {
    const entry = config[props.setPageId];
    return (
        <HelpPanel header={<h2>{entry ? entry.title : ""}</h2>}>
            <ReactMarkdown
                children={entry ? entry.description : ""}
                remarkPlugins={[remarkGfm]}
                components={{
                    a(linkProps) {
                        const { children, href, ...rest } = linkProps;
                        return (
                            <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
                                {children}
                            </a>
                        );
                    },
                }}
            />
        </HelpPanel>
    );
}
