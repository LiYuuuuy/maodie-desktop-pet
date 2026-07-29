import { load, type Store } from "@tauri-apps/plugin-store";
import { DEFAULT_SETTINGS, migrateSettings } from "./defaults";
import type { AppSettings, SavedPetPosition } from "./schema";

const SETTINGS_KEY = "settings";
const POSITION_KEY = "petPosition";
let storePromise: Promise<Store> | undefined;

function appStore(): Promise<Store> {
  storePromise ??= load("maodie.settings.json", { autoSave: 300 });
  return storePromise;
}

export async function loadSettings(): Promise<AppSettings> {
  try {
    const store = await appStore();
    return migrateSettings(await store.get(SETTINGS_KEY));
  } catch {
    const local = localStorage.getItem(SETTINGS_KEY);
    return migrateSettings(local ? JSON.parse(local) : DEFAULT_SETTINGS);
  }
}

export async function saveSettings(settings: AppSettings): Promise<void> {
  const value = migrateSettings(settings);
  try {
    const store = await appStore();
    await store.set(SETTINGS_KEY, value);
    await store.save();
  } catch {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(value));
  }
  window.dispatchEvent(new CustomEvent("maodie:settings", { detail: value }));
}

export async function loadPetPosition(): Promise<SavedPetPosition | undefined> {
  try {
    return (await (await appStore()).get(POSITION_KEY)) as SavedPetPosition | undefined;
  } catch {
    const value = localStorage.getItem(POSITION_KEY);
    return value ? (JSON.parse(value) as SavedPetPosition) : undefined;
  }
}

export async function savePetPosition(position: SavedPetPosition): Promise<void> {
  try {
    const store = await appStore();
    await store.set(POSITION_KEY, position);
    await store.save();
  } catch {
    localStorage.setItem(POSITION_KEY, JSON.stringify(position));
  }
}
