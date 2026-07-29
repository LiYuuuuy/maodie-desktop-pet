import { appendDelta, finishStream } from "../src/chat/streamController";
import type { ChatMessage } from "../src/chat/types";

it("preserves generated text when a stream is cancelled", () => {
  const messages: ChatMessage[] = [
    { id: "a", role: "assistant", content: "", createdAt: 1, status: "streaming" },
  ];
  const partial = appendDelta(messages, "a", "别急");
  expect(finishStream(partial, "a", "stopped")[0]).toMatchObject({
    content: "别急",
    status: "stopped",
  });
});
