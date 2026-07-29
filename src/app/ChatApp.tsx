import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useCallback, useEffect, useRef, useState } from "react";
import { appendDelta, finishStream } from "../chat/streamController";
import type { ChatMessage, ChatStreamEvent } from "../chat/types";
import { clearChatHistory, loadChatHistory, saveChatHistory } from "../chat/chatStore";
import { MessageList } from "../components/MessageList";
import { DEFAULT_SETTINGS } from "../settings/defaults";
import { loadSettings } from "../settings/settingsStore";
import type { AppSettings } from "../settings/schema";

const id = () => crypto.randomUUID();

export function ChatApp() {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [requestId, setRequestId] = useState<string>();
  const [error, setError] = useState("");
  const assistantId = useRef<string | undefined>(undefined);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    void loadSettings().then((loaded) => {
      setSettings(loaded);
      setMessages(loaded.chat.saveHistory ? loadChatHistory(loaded.chat.maxMessages) : []);
      requestAnimationFrame(() => inputRef.current?.focus());
    });
  }, []);

  useEffect(() => {
    const unlisteners: UnlistenFn[] = [];
    const register = async () => {
      unlisteners.push(
        await listen<ChatStreamEvent>("chat://delta", ({ payload }) => {
          if (!assistantId.current || payload.requestId !== requestId) return;
          setMessages((current) => appendDelta(current, assistantId.current!, payload.delta ?? ""));
        }),
        await listen<ChatStreamEvent>("chat://complete", ({ payload }) => {
          if (!assistantId.current || payload.requestId !== requestId) return;
          setMessages((current) => finishStream(current, assistantId.current!, "complete"));
          setRequestId(undefined);
        }),
        await listen<ChatStreamEvent>("chat://cancelled", ({ payload }) => {
          if (!assistantId.current || payload.requestId !== requestId) return;
          setMessages((current) => finishStream(current, assistantId.current!, "stopped"));
          setRequestId(undefined);
        }),
        await listen<ChatStreamEvent>("chat://error", ({ payload }) => {
          if (!assistantId.current || payload.requestId !== requestId) return;
          setError(payload.message ?? "请求失败");
          setMessages((current) => finishStream(current, assistantId.current!, "error"));
          setRequestId(undefined);
        }),
      );
    };
    void register();
    return () => unlisteners.forEach((unlisten) => unlisten());
  }, [requestId]);

  useEffect(() => {
    if (settings.chat.saveHistory) saveChatHistory(messages, settings.chat.maxMessages);
  }, [messages, settings.chat.maxMessages, settings.chat.saveHistory]);

  const send = useCallback(async () => {
    const content = input.trim();
    if (!content || requestId) return;
    if (!settings.chat.providerConfig.apiKeyRef) {
      setError("请先在设置中保存 API Key");
      return;
    }
    setError("");
    setInput("");
    const user: ChatMessage = { id: id(), role: "user", content, createdAt: Date.now(), status: "complete" };
    const assistant: ChatMessage = {
      id: id(),
      role: "assistant",
      content: "",
      createdAt: Date.now(),
      status: "streaming",
    };
    assistantId.current = assistant.id;
    const next = [...messages, user, assistant].slice(-settings.chat.maxMessages);
    setMessages(next);
    try {
      const started = await invoke<string>("start_chat_stream", {
        request: {
          messages: next
            .filter((message) => message.id !== assistant.id)
            .map(({ role, content: messageContent }) => ({ role, content: messageContent })),
          config: settings.chat.providerConfig,
        },
      });
      setRequestId(started);
    } catch (reason) {
      setError(String(reason));
      setMessages((current) => finishStream(current, assistant.id, "error"));
    }
  }, [input, messages, requestId, settings.chat.maxMessages, settings.chat.providerConfig]);

  const stop = async () => {
    if (requestId) await invoke("cancel_chat_stream", { requestId });
  };

  const close = async () => {
    if (requestId) await invoke("cancel_chat_stream", { requestId });
    await getCurrentWindow().hide();
    await invoke("notify_chat_closed");
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") void close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <main className="dialog-window chat-window">
      <header className="dialog-titlebar" data-tauri-drag-region>
        <div>
          <strong>圆头耄耋</strong>
          <span>{requestId ? "正在琢磨…" : "嘴硬但能聊"}</span>
        </div>
        <nav>
          <button onClick={() => void invoke("show_settings_window")} title="设置">⚙</button>
          <button onClick={() => void close()} title="关闭">×</button>
        </nav>
      </header>
      <MessageList messages={messages} />
      {error && <div className="error-banner">{error}</div>}
      <footer className="composer">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          placeholder="跟耄耋说点什么…"
          rows={3}
        />
        <div>
          <button
            className="text-button"
            onClick={() => {
              clearChatHistory();
              setMessages([]);
            }}
          >
            清空
          </button>
          {requestId ? (
            <button className="primary-button stop-button" onClick={() => void stop()}>
              停止
            </button>
          ) : (
            <button className="primary-button" disabled={!input.trim()} onClick={() => void send()}>
              发送
            </button>
          )}
        </div>
      </footer>
    </main>
  );
}
