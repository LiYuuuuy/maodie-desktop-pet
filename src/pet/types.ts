export const IDLE_STATES = ["sitting", "walking", "sleeping"] as const;
export const INTERACTION_STATES = ["happy", "petting", "hissing"] as const;
export const VISUAL_STATES = [...IDLE_STATES, ...INTERACTION_STATES] as const;

export type IdleState = (typeof IDLE_STATES)[number];
export type InteractionState = (typeof INTERACTION_STATES)[number];
export type VisualState = (typeof VISUAL_STATES)[number];
export type SystemMode = "dragging_pet" | "file_drag_hover" | "chat_open" | "hidden" | null;
export type AnimationConfig = {
  fps: number;
  loop: boolean;
  durationMs?: number;
  frameDurationsMs?: readonly number[];
};

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

export const ANIMATION_CONFIG: Record<VisualState, AnimationConfig> = {
  sitting: { fps: 8, loop: true },
  walking: { fps: 10, loop: true },
  sleeping: { fps: 6, loop: true },
  happy: { fps: 12, loop: true, durationMs: 2_000 },
  petting: {
    fps: 10,
    loop: false,
    frameDurationsMs: [
      100, 45, 45, 40, 40, 40, 60, 120, 180, 160, 130, 100, 100, 90, 120, 120,
    ],
  },
  hissing: {
    fps: 10,
    loop: false,
    frameDurationsMs: [100, 40, 40, 35, 35, 35, 30, 75, 130, 130, 95, 55, 55, 50, 75, 85],
  },
};

export const IDLE_TRANSITION_CONFIG = { fps: 10, loop: false } satisfies AnimationConfig;

export const IDLE_TRANSITION_PAIRS = [
  ["sitting", "walking"],
  ["sitting", "sleeping"],
  ["walking", "sleeping"],
] as const satisfies readonly (readonly [IdleState, IdleState])[];

export type IdleTransitionName =
  `${(typeof IDLE_TRANSITION_PAIRS)[number][0]}-${(typeof IDLE_TRANSITION_PAIRS)[number][1]}`;

export function resolveIdleTransition(
  from: VisualState,
  to: VisualState,
): { name: IdleTransitionName; reverse: boolean } | undefined {
  for (const [start, end] of IDLE_TRANSITION_PAIRS) {
    if (from === start && to === end) {
      return { name: `${start}-${end}` as IdleTransitionName, reverse: false };
    }
    if (from === end && to === start) {
      return { name: `${start}-${end}` as IdleTransitionName, reverse: true };
    }
  }
  return undefined;
}

export function animationFrameDuration(
  config: AnimationConfig,
  frameIndex: number,
  fpsMultiplier = 1,
): number {
  const fallback = 1_000 / Math.max(1, config.fps);
  const duration = config.frameDurationsMs?.[frameIndex] ?? fallback;
  return duration / Math.max(0.1, fpsMultiplier);
}
