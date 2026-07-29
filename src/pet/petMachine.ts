import type { AppSettings } from "../settings/schema";
import { IDLE_STATES, type IdleState, type PetEvent, type PetMachineState } from "./types";

export const INITIAL_PET_STATE: PetMachineState = {
  visual: "sitting",
  mode: null,
  direction: "right",
  pendingChat: false,
};

const isBusy = (state: PetMachineState) =>
  state.visual === "happy" || state.visual === "petting" || state.visual === "hissing";

export function chooseIdleState(
  current: IdleState,
  random: number,
  settings: AppSettings["idleScheduler"],
): IdleState {
  let choices = IDLE_STATES.map((state) => ({
    state,
    weight: Math.max(0, settings.weights[state]),
  }));
  if (settings.avoidImmediateRepeat) choices = choices.filter(({ state }) => state !== current);
  const total = choices.reduce((sum, item) => sum + item.weight, 0);
  if (total <= 0) return "sitting";
  let cursor = Math.min(0.999999, Math.max(0, random)) * total;
  for (const choice of choices) {
    cursor -= choice.weight;
    if (cursor < 0) return choice.state;
  }
  return choices.at(-1)!.state;
}

export function reducePet(
  state: PetMachineState,
  event: PetEvent,
  settings: AppSettings,
): PetMachineState {
  switch (event.type) {
    case "IDLE_TIMEOUT": {
      if (state.mode || isBusy(state) || !settings.idleScheduler.enabled) return state;
      const current = IDLE_STATES.includes(state.visual as IdleState)
        ? (state.visual as IdleState)
        : "sitting";
      const visual = chooseIdleState(current, event.random ?? Math.random(), settings.idleScheduler);
      return { ...state, visual, direction: visual === "walking" && Math.random() < 0.5 ? "left" : "right" };
    }
    case "LEFT_CLICK":
      if (state.mode || isBusy(state)) return state;
      return {
        ...state,
        visual: event.random < settings.interaction.hissProbability ? "hissing" : "petting",
      };
    case "PET_DRAG_START":
      return isBusy(state) ? state : { ...state, visual: "sitting", mode: "dragging_pet" };
    case "PET_DRAG_END":
      return state.mode === "dragging_pet" ? { ...state, mode: null } : state;
    case "FILE_DRAG_ENTER":
      return { ...state, mode: "file_drag_hover", visual: "sitting" };
    case "FILE_DRAG_LEAVE":
      return state.mode === "file_drag_hover" ? { ...state, mode: null } : state;
    case "FILE_TRASH_SUCCESS":
      return event.count > 0 ? { ...state, visual: "happy", mode: null } : state;
    case "FILE_TRASH_FAILURE":
      return { ...state, visual: "sitting", mode: null };
    case "RIGHT_CLICK":
      return isBusy(state)
        ? { ...state, pendingChat: true }
        : { ...state, visual: "sitting", mode: state.mode === "chat_open" ? null : "chat_open" };
    case "CHAT_CLOSE":
      return { ...state, visual: "sitting", mode: null, pendingChat: false };
    case "ANIMATION_COMPLETE":
      if (state.visual !== event.state || !isBusy(state)) return state;
      return {
        ...state,
        visual: "sitting",
        mode: state.pendingChat ? "chat_open" : null,
        pendingChat: false,
      };
    default:
      return state;
  }
}
