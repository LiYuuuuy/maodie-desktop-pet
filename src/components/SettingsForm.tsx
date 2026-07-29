import type { AppSettings } from "../settings/schema";

type Props = {
  value: AppSettings;
  apiKey: string;
  onApiKey: (value: string) => void;
  onChange: (value: AppSettings) => void;
};

export function SettingsForm({ value, apiKey, onApiKey, onChange }: Props) {
  const patch = <K extends keyof AppSettings>(section: K, change: Partial<AppSettings[K]>) =>
    onChange({ ...value, [section]: { ...(value[section] as object), ...change } });
  return (
    <div className="settings-sections">
      <section>
        <h2>外观</h2>
        <label>
          桌宠缩放 <output>{Math.round(value.pet.scale * 100)}%</output>
          <input
            type="range"
            min="0.5"
            max="2"
            step="0.05"
            value={value.pet.scale}
            onChange={(event) => patch("pet", { scale: Number(event.target.value) })}
          />
        </label>
        <label className="check"><input type="checkbox" checked={value.pet.alwaysOnTop} onChange={(event) => patch("pet", { alwaysOnTop: event.target.checked })} /> 始终置顶</label>
        <label className="check"><input type="checkbox" checked={value.pet.showOnStartup} onChange={(event) => patch("pet", { showOnStartup: event.target.checked })} /> 启动时显示</label>
        <label className="check"><input type="checkbox" checked={value.appearance.showFeedHint} onChange={(event) => patch("appearance", { showFeedHint: event.target.checked })} /> 显示投喂提示</label>
        <label>对话主题
          <select value={value.appearance.theme} onChange={(event) => patch("appearance", { theme: event.target.value as AppSettings["appearance"]["theme"] })}>
            <option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option>
          </select>
        </label>
      </section>
      <section>
        <h2>行为</h2>
        <label className="check"><input type="checkbox" checked={value.idleScheduler.enabled} onChange={(event) => patch("idleScheduler", { enabled: event.target.checked })} /> 启用随机行为</label>
        <div className="two-columns">
          <label>最短等待（秒）<input type="number" min="1" value={value.idleScheduler.minDelayMs / 1000} onChange={(event) => patch("idleScheduler", { minDelayMs: Number(event.target.value) * 1000 })} /></label>
          <label>最长等待（秒）<input type="number" min="1" value={value.idleScheduler.maxDelayMs / 1000} onChange={(event) => patch("idleScheduler", { maxDelayMs: Number(event.target.value) * 1000 })} /></label>
        </div>
        <label>哈气概率 <output>{Math.round(value.interaction.hissProbability * 100)}%</output>
          <input type="range" min="0" max="1" step="0.01" value={value.interaction.hissProbability} onChange={(event) => patch("interaction", { hissProbability: Number(event.target.value) })} />
        </label>
        <label className="check"><input type="checkbox" checked={value.pet.savePosition} onChange={(event) => patch("pet", { savePosition: event.target.checked })} /> 记住桌宠位置</label>
      </section>
      <section>
        <h2>模型</h2>
        <label>Base URL<input value={value.chat.providerConfig.baseUrl} onChange={(event) => patch("chat", { providerConfig: { ...value.chat.providerConfig, baseUrl: event.target.value } })} /></label>
        <label>Model<input value={value.chat.providerConfig.model} onChange={(event) => patch("chat", { providerConfig: { ...value.chat.providerConfig, model: event.target.value } })} /></label>
        <label>API Key<input type="password" autoComplete="off" value={apiKey} placeholder={value.chat.providerConfig.apiKeyRef ? "已安全保存（输入可更新）" : "sk-…"} onChange={(event) => onApiKey(event.target.value)} /></label>
        <div className="two-columns">
          <label>Temperature<input type="number" min="0" max="2" step="0.1" value={value.chat.providerConfig.temperature} onChange={(event) => patch("chat", { providerConfig: { ...value.chat.providerConfig, temperature: Number(event.target.value) } })} /></label>
          <label>最大输出 tokens<input type="number" min="1" max="32768" value={value.chat.providerConfig.maxOutputTokens} onChange={(event) => patch("chat", { providerConfig: { ...value.chat.providerConfig, maxOutputTokens: Number(event.target.value) } })} /></label>
        </div>
        <label className="check"><input type="checkbox" checked={value.chat.saveHistory} onChange={(event) => patch("chat", { saveHistory: event.target.checked })} /> 保存最近一次会话</label>
      </section>
      <section>
        <h2>关于</h2>
        <p>圆头耄耋桌宠 0.1.3</p>
        <p className="muted">程序代码采用 MIT 许可证。角色参考素材版权归原始权利人，仅供获得授权的个人使用。</p>
      </section>
    </div>
  );
}
