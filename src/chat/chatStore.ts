import type { ChatMessage } from "./types";

const KEY = "maodie.chat.history";

export function loadChatHistory(maxMessages = 50): ChatMessage[] {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? "[]") as ChatMessage[];
    return Array.isArray(value) ? value.slice(-maxMessages) : [];
  } catch {
    return [];
  }
}

export function saveChatHistory(messages: ChatMessage[], maxMessages = 50): void {
  localStorage.setItem(
    KEY,
    JSON.stringify(
      messages
        .filter((message) => message.status !== "streaming")
        .slice(-Math.max(1, maxMessages)),
    ),
  );
}

export function clearChatHistory(): void {
  localStorage.removeItem(KEY);
}
