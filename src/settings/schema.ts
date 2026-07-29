export type ProviderConfig = {
  provider: "openai-compatible";
  baseUrl: string;
  model: string;
  temperature: number;
  maxOutputTokens: number;
  timeoutMs: number;
  apiKeyRef?: string;
};

export type AppSettings = {
  version: 1;
  pet: {
    scale: number;
    alwaysOnTop: boolean;
    showOnStartup: boolean;
    savePosition: boolean;
  };
  appearance: {
    animationFpsMultiplier: number;
    showFeedHint: boolean;
    theme: "system" | "light" | "dark";
  };
  idleScheduler: {
    enabled: boolean;
    minDelayMs: number;
    maxDelayMs: number;
    weights: { sitting: number; walking: number; sleeping: number };
    avoidImmediateRepeat: boolean;
  };
  movement: {
    minSpeed: number;
    maxSpeed: number;
    allowCrossMonitor: boolean;
  };
  interaction: {
    hissProbability: number;
    clickDebounceMs: number;
  };
  chat: {
    saveHistory: boolean;
    maxMessages: number;
    providerConfig: ProviderConfig;
  };
};

export type SavedPetPosition = {
  monitorId?: string;
  x: number;
  y: number;
  scaleFactorAtSave: number;
};
