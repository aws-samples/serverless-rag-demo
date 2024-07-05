import DocViewer, { } from "react-doc-viewer";
export interface ChatFileReaderProps {
    content: string;
}
const regex = /<location>(.+?)<\/location>/; 
export default function AgentChatFileReader(props: ChatFileReaderProps) {
    
    const match = props.content.match(regex);
    const url = match[1];
    if(url.includes("html")){
        return(<iframe
            style={{ width: "100%" , minHeight: "300px" , maxHeight: "600px" , border:"0px"}}
            src={url}
        />)
    }else{
        let filetype = null;
        if(url.includes(".pptx")) filetype = "pptx";
        return(<DocViewer
            documents={[{uri: url , fileType: filetype}]}
        />)
    }
}