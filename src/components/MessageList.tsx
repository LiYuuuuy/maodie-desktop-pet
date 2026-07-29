import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "../chat/types";

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="message-list" aria-live="polite">
      {messages.length === 0 && (
        <div className="chat-empty">
          <span>圆头耄耋</span>
          <p>有事快说，没事也可以摸两下。</p>
        </div>
      )}
      {messages.map((message) => (
        <article key={message.id} className={`message message-${message.role}`}>
          <header>{message.role === "user" ? "你" : "耄耋"}</header>
          <ReactMarkdown>{message.content || (message.status === "streaming" ? "…" : "")}</ReactMarkdown>
          {message.status === "stopped" && <small>已停止</small>}
          {message.status === "error" && <small>生成失败</small>}
        </article>
      ))}
    </div>
  );
}
