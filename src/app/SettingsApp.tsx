import { invoke } from "@tauri-apps/api/core";
import { emit } from "@tauri-apps/api/event";
import { LogicalSize, getAllWindows, getCurrentWindow } from "@tauri-apps/api/window";
import { useEffect, useState } from "react";
import { SettingsForm } from "../components/SettingsForm";
import { DEFAULT_SETTINGS } from "../settings/defaults";
import { loadSettings, saveSettings } from "../settings/settingsStore";
import type { AppSettings } from "../settings/schema";

export function SettingsApp() {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [apiKey, setApiKey] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    void loadSettings().then(setSettings);
  }, []);

  useEffect(() => {
    void getAllWindows()
      .then((windows) => windows.find((window) => window.label === "pet"))
      .then((pet) =>
        pet?.setSize(new LogicalSize(256 * settings.pet.scale, 256 * settings.pet.scale)),
      )
      .catch((error) => setStatus(`缩放预览失败：${String(error)}`));
  }, [settings.pet.scale]);

  const save = async () => {
    let next = settings;
    if (apiKey.trim()) {
      await invoke("save_api_key", { providerId: "openai-compatible", apiKey: apiKey.trim() });
      next = {
        ...settings,
        chat: {
          ...settings.chat,
          providerConfig: { ...settings.chat.providerConfig, apiKeyRef: "openai-compatible" },
        },
      };
      setSettings(next);
      setApiKey("");
    }
    await saveSettings(next);
    await emit("settings://changed", next);
    const pet = (await getAllWindows()).find((window) => window.label === "pet");
    if (pet) {
      await pet.setAlwaysOnTop(next.pet.alwaysOnTop);
      await pet.setSize(new LogicalSize(256 * next.pet.scale, 256 * next.pet.scale));
    }
    setStatus("设置已保存");
  };

  const test = async () => {
    setStatus("正在测试…");
    try {
      const result = await invoke<{ valid: boolean; message: string }>("validate_llm_config", {
        config: settings.chat.providerConfig,
      });
      setStatus(result.message);
    } catch (error) {
      setStatus(String(error));
    }
  };

  return (
    <main className="dialog-window settings-window">
      <header className="dialog-titlebar">
        <div className="dialog-drag-region" data-tauri-drag-region><strong>耄耋设置</strong><span>别乱调，调坏了我可不管。</span></div>
        <button onClick={() => void getCurrentWindow().hide()}>×</button>
      </header>
      <SettingsForm value={settings} apiKey={apiKey} onApiKey={setApiKey} onChange={setSettings} />
      <footer className="settings-actions">
        <span>{status}</span>
        <button className="text-button" onClick={() => void test()}>测试连接</button>
        <button className="text-button danger" onClick={async () => {
          await invoke("delete_api_key", { providerId: "openai-compatible" });
          setSettings({ ...settings, chat: { ...settings.chat, providerConfig: { ...settings.chat.providerConfig, apiKeyRef: undefined } } });
          setStatus("API Key 已清除");
        }}>清除 Key</button>
        <button className="primary-button" onClick={() => void save()}>保存</button>
      </footer>
    </main>
  );
}
