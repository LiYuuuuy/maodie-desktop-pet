export const IDLE_STATES = ["sitting", "walking", "sleeping"] as const;
export const INTERACTION_STATES = ["happy", "petting", "hissing"] as const;
export const VISUAL_STATES = [...IDLE_STATES, ...INTERACTION_STATES] as const;

export type IdleState = (typeof IDLE_STATES)[number];
export type InteractionState = (typeof INTERACTION_STATES)[number];
export type VisualState = (typeof VISUAL_STATES)[number];
export type SystemMode = "dragging_pet" | "file_drag_hover" | "chat_open" | "hidden" | null;

export type PetEvent =
  | { type: "IDLE_TIMEOUT"; random?: number }
  | { type: "LEFT_CLICK"; random: number }
  | { type: "PET_DRAG_START" }
  | { type: "PET_DRAG_END" }
  | { type: "FILE_DRAG_ENTER"; paths: string[] }
  | { type: "FILE_DRAG_LEAVE" }
  | { type: "FILE_DROP"; paths: string[] }
  | { type: "FILE_TRASH_SUCCESS"; count: number }
  | { type: "FILE_TRASH_FAILURE"; message: string }
  | { type: "RIGHT_CLICK" }
  | { type: "CHAT_CLOSE" }
  | { type: "ANIMATION_COMPLETE"; state: VisualState };

export type PetMachineState = {
  visual: VisualState;
  mode: SystemMode;
  direction: "left" | "right";
  pendingChat: boolean;
};

export const ANIMATION_CONFIG: Record<
  VisualState,
  { fps: number; loop: boolean; durationMs?: number }
> = {
  sitting: { fps: 8, loop: true },
  walking: { fps: 10, loop: true },
  sleeping: { fps: 6, loop: true },
  happy: { fps: 12, loop: true, durationMs: 2_000 },
  petting: { fps: 10, loop: false },
  hissing: { fps: 10, loop: false },
};
