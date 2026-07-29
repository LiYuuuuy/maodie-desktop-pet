import type { AppSettings } from "./schema";

export const DEFAULT_SETTINGS: AppSettings = {
  version: 1,
  pet: {
    scale: 1,
    alwaysOnTop: true,
    showOnStartup: true,
    savePosition: true,
  },
  appearance: {
    animationFpsMultiplier: 1,
    showFeedHint: true,
    theme: "system",
  },
  idleScheduler: {
    enabled: true,
    minDelayMs: 8_000,
    maxDelayMs: 25_000,
    weights: { sitting: 0.45, walking: 0.35, sleeping: 0.2 },
    avoidImmediateRepeat: true,
  },
  movement: {
    minSpeed: 35,
    maxSpeed: 75,
    allowCrossMonitor: false,
  },
  interaction: {
    hissProbability: 0.15,
    clickDebounceMs: 250,
  },
  chat: {
    saveHistory: true,
    maxMessages: 50,
    providerConfig: {
      provider: "openai-compatible",
      baseUrl: "https://api.openai.com/v1",
      model: "gpt-4.1-mini",
      temperature: 0.8,
      maxOutputTokens: 800,
      timeoutMs: 60_000,
    },
  },
};

export function migrateSettings(value: unknown): AppSettings {
  if (!value || typeof value !== "object") return structuredClone(DEFAULT_SETTINGS);
  const candidate = value as Partial<AppSettings>;
  const merged = {
    ...DEFAULT_SETTINGS,
    ...candidate,
    pet: { ...DEFAULT_SETTINGS.pet, ...candidate.pet },
    appearance: { ...DEFAULT_SETTINGS.appearance, ...candidate.appearance },
    idleScheduler: {
      ...DEFAULT_SETTINGS.idleScheduler,
      ...candidate.idleScheduler,
      weights: {
        ...DEFAULT_SETTINGS.idleScheduler.weights,
        ...candidate.idleScheduler?.weights,
      },
    },
    movement: { ...DEFAULT_SETTINGS.movement, ...candidate.movement },
    interaction: { ...DEFAULT_SETTINGS.interaction, ...candidate.interaction },
    chat: {
      ...DEFAULT_SETTINGS.chat,
      ...candidate.chat,
      providerConfig: {
        ...DEFAULT_SETTINGS.chat.providerConfig,
        ...candidate.chat?.providerConfig,
      },
    },
    version: 1 as const,
  };
  merged.pet.scale = Math.min(2, Math.max(0.5, Number(merged.pet.scale) || 1));
  merged.interaction.hissProbability = Math.min(
    1,
    Math.max(0, Number(merged.interaction.hissProbability) || 0),
  );
  if (merged.idleScheduler.minDelayMs > merged.idleScheduler.maxDelayMs) {
    [merged.idleScheduler.minDelayMs, merged.idleScheduler.maxDelayMs] = [
      merged.idleScheduler.maxDelayMs,
      merged.idleScheduler.minDelayMs,
    ];
  }
  return merged;
}
