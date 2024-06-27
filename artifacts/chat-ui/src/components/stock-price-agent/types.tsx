export enum ChatMessageType {
  AI = "ai",
  Human = "human",
}

export interface ChatMessage {
  type: ChatMessageType;
  content: string;
}
