export interface ChatFileReaderProps {
    content: string;
}
const regex = /<location>(.+?)<\/location>/; 
export default function AgentChatFileReader(props: ChatFileReaderProps) {
    
    const match = props.content.match(regex);
    const url = match[1];
    return(<iframe
        style={{ width: "100%" , minHeight: "300px" , maxHeight: "600px" , border:"0px"}}
        src={url}
    />)
}