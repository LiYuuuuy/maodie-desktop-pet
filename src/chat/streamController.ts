import type { ChatMessage } from "./types";

export function appendDelta(
  messages: ChatMessage[],
  assistantId: string,
  delta: string,
): ChatMessage[] {
  return messages.map((message) =>
    message.id === assistantId ? { ...message, content: message.content + delta } : message,
  );
}

export function finishStream(
  messages: ChatMessage[],
  assistantId: string,
  status: "complete" | "stopped" | "error",
): ChatMessage[] {
  return messages.map((message) => (message.id === assistantId ? { ...message, status } : message));
}
