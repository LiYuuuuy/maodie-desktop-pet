import { commandErrorMessage } from "../src/tauriError";

describe("Tauri command errors", () => {
  it("shows the message from a structured AppError instead of object Object", () => {
    expect(commandErrorMessage({ code: "api_key_missing", message: "尚未配置 API Key" })).toBe(
      "尚未配置 API Key",
    );
  });

  it("handles native and fallback errors", () => {
    expect(commandErrorMessage(new Error("网络不可用"))).toBe("网络不可用");
    expect(commandErrorMessage({ code: "unknown" }, "连接失败")).toBe("连接失败（unknown）");
    expect(commandErrorMessage(null, "连接失败")).toBe("连接失败");
  });
});
