import DocViewer, { } from "react-doc-viewer";

export interface ChatFileReaderProps {
    content: string;
}

const LOCATION = /<location>(.+?)<\/location>/;

/**
 * Render a generated artefact the agent reported back.
 *
 * The URL arrives inside model output, so it is treated as untrusted. Two things
 * matter here:
 *
 *  - It must be an https S3 presigned URL. The previous `url.includes("html")`
 *    test was satisfied by `javascript:...//html`, and a `javascript:` iframe
 *    inherits the embedding document's origin — so a document carrying a prompt
 *    injection could reach this app's Cognito tokens.
 *  - Even a legitimate presigned URL points at generated HTML, which the model
 *    wrote. `sandbox` with neither allow-scripts nor allow-same-origin gives it
 *    an opaque origin and no script execution, so it can be displayed without
 *    being trusted.
 */
function presignedS3Url(raw: string): URL | null {
    let parsed: URL;
    try {
        parsed = new URL(raw);
    } catch {
        return null;
    }
    if (parsed.protocol !== "https:") return null;
    // s3.amazonaws.com, s3.<region>.amazonaws.com and the virtual-hosted forms.
    if (!/(^|\.)s3[.-][a-z0-9.-]*amazonaws\.com$/.test(parsed.hostname)) return null;
    return parsed;
}

export default function AgentChatFileReader(props: ChatFileReaderProps) {
    const match = props.content.match(LOCATION);
    if (!match) return null;

    const url = presignedS3Url(match[1]);
    if (!url) return null;

    if (url.pathname.endsWith(".html")) {
        return (
            <iframe
                style={{ width: "100%", minHeight: "300px", maxHeight: "600px", border: "0px" }}
                sandbox=""
                referrerPolicy="no-referrer"
                src={url.href}
            />
        );
    }

    const filetype = url.pathname.endsWith(".pptx") ? "pptx" : null;
    return (
        <DocViewer
            documents={[{ uri: url.href, fileType: filetype }]}
        />
    );
}
