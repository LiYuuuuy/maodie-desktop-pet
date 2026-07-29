import type { ProviderConfig } from "../settings/schema";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  status?: "streaming" | "complete" | "stopped" | "error";
};

export type ChatRequest = {
  messages: Array<Pick<ChatMessage, "role" | "content">>;
  config: ProviderConfig;
};

export type ChatStreamEvent = {
  requestId: string;
  delta?: string;
  message?: string;
};
