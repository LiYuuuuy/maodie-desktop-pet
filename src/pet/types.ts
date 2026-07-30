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
  optionalTail?: {
    startFrame: number;
    playProbability: number;
  };
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
  sitting: {
    fps: 16,
    loop: true,
    optionalTail: { startFrame: 16, playProbability: 0.25 },
  },
  walking: { fps: 24.0246, loop: true },
  sleeping: { fps: 12, loop: true },
  happy: { fps: 24, loop: true, durationMs: 2_000 },
  petting: { fps: 24, loop: false },
  hissing: { fps: 24, loop: false },
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
  fpsMultiplier = 1,
): number {
  return 1_000 / Math.max(1, config.fps) / Math.max(0.1, fpsMultiplier);
}

export function nextAnimationFrame(
  current: number,
  frameCount: number,
  config: AnimationConfig,
  random = Math.random(),
): number | undefined {
  const next = current + 1;
  if (
    config.optionalTail &&
    next === config.optionalTail.startFrame &&
    random >= config.optionalTail.playProbability
  ) {
    return 0;
  }
  if (next < frameCount) return next;
  return config.loop ? 0 : undefined;
}
