export enum ChatMessageType {
  AI = "ai",
  Human = "human",
}

export interface SourceInfo {
  index: number;
  uri: string;
  excerpt?: string;
  presignedUrl?: string;
  fileName?: string;
}

export interface ChatMessage {
  type: ChatMessageType;
  content: string;
  sources?: SourceInfo[];
  rating?: "up" | "down" | null;
  question?: string;
}
