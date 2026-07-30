import { invoke } from "@tauri-apps/api/core";
import { emit } from "@tauri-apps/api/event";
import { LogicalSize, getAllWindows, getCurrentWindow } from "@tauri-apps/api/window";
import { useEffect, useState } from "react";
import { SettingsForm } from "../components/SettingsForm";
import { DEFAULT_SETTINGS } from "../settings/defaults";
import { loadSettings, saveSettings } from "../settings/settingsStore";
import type { AppSettings } from "../settings/schema";
import { commandErrorMessage } from "../tauriError";

const PROVIDER_ID = "openai-compatible";

export function SettingsApp() {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [apiKey, setApiKey] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void loadSettings().then(setSettings);
  }, []);

  useEffect(() => {
    void getAllWindows()
      .then((windows) => windows.find((window) => window.label === "pet"))
      .then((pet) =>
        pet?.setSize(new LogicalSize(256 * settings.pet.scale, 256 * settings.pet.scale)),
      )
      .catch((error) => setStatus(`缩放预览失败：${commandErrorMessage(error)}`));
  }, [settings.pet.scale]);

  const persist = async (): Promise<AppSettings> => {
    let next = settings;
    if (apiKey.trim()) {
      await invoke("save_api_key", { providerId: PROVIDER_ID, apiKey: apiKey.trim() });
      next = {
        ...settings,
        chat: {
          ...settings.chat,
          providerConfig: { ...settings.chat.providerConfig, apiKeyRef: PROVIDER_ID },
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
    return next;
  };

  const save = async () => {
    setBusy(true);
    try {
      await persist();
      setStatus("设置与 API Key 已保存");
    } catch (error) {
      setStatus(`保存失败：${commandErrorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    setStatus("正在保存并测试…");
    try {
      const saved = await persist();
      const result = await invoke<{ valid: boolean; message: string }>("validate_llm_config", {
        config: saved.chat.providerConfig,
      });
      setStatus(result.valid ? result.message : `连接失败：${result.message}`);
    } catch (error) {
      setStatus(`连接失败：${commandErrorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const clearKey = async () => {
    setBusy(true);
    try {
      await invoke("delete_api_key", { providerId: PROVIDER_ID });
      const next = {
        ...settings,
        chat: {
          ...settings.chat,
          providerConfig: { ...settings.chat.providerConfig, apiKeyRef: undefined },
        },
      };
      setSettings(next);
      setApiKey("");
      await saveSettings(next);
      await emit("settings://changed", next);
      setStatus("API Key 已清除");
    } catch (error) {
      setStatus(`清除失败：${commandErrorMessage(error)}`);
    } finally {
      setBusy(false);
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
        <button className="text-button" disabled={busy} onClick={() => void test()}>测试连接</button>
        <button className="text-button danger" disabled={busy} onClick={() => void clearKey()}>清除 Key</button>
        <button className="primary-button" disabled={busy} onClick={() => void save()}>保存</button>
      </footer>
    </main>
  );
}
