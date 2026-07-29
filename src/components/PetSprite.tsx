import { useEffect, useRef, useState } from "react";
import {
  ANIMATION_CONFIG,
  IDLE_TRANSITION_CONFIG,
  animationFrameDuration,
  resolveIdleTransition,
  type AnimationConfig,
  type IdleTransitionName,
  type VisualState,
} from "../pet/types";

const frameModules = import.meta.glob<string>("../assets/pet/*/*.png", {
  eager: true,
  query: "?url",
  import: "default",
});

const idleTransitionModules = import.meta.glob<string>("../assets/pet-transitions/*/*.png", {
  eager: true,
  query: "?url",
  import: "default",
});

function framesFor(state: VisualState): string[] {
  return Object.entries(frameModules)
    .filter(([path]) => path.includes(`/pet/${state}/`))
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([, url]) => url);
}

function transitionFramesFor(name: IdleTransitionName): string[] {
  return Object.entries(idleTransitionModules)
    .filter(([path]) => path.includes(`/pet-transitions/${name}/`))
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([, url]) => url);
}

type Props = {
  state: VisualState;
  direction: "left" | "right";
  fpsMultiplier?: number;
  onComplete: (state: VisualState) => void;
};

type Playback = {
  frames: string[];
  config: AnimationConfig;
  completionState?: VisualState;
  nextState?: VisualState;
};

function statePlayback(state: VisualState): Playback {
  return {
    frames: framesFor(state),
    config: ANIMATION_CONFIG[state],
    completionState: state,
  };
}

export function PetSprite({ state, direction, fpsMultiplier = 1, onComplete }: Props) {
  const [playback, setPlayback] = useState<Playback>(() => statePlayback(state));
  const [frame, setFrame] = useState(0);
  const visualRef = useRef(state);
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    const previous = visualRef.current;
    visualRef.current = state;
    if (previous === state) return;

    const transition = resolveIdleTransition(previous, state);
    if (!transition) {
      setPlayback(statePlayback(state));
      return;
    }

    const frames = transitionFramesFor(transition.name);
    setPlayback({
      frames: transition.reverse ? [...frames].reverse() : frames,
      config: IDLE_TRANSITION_CONFIG,
      nextState: state,
    });
  }, [state]);

  useEffect(() => {
    setFrame(0);
    if (playback.frames.length === 0) return;

    let current = 0;
    let frameTimer: number | undefined;
    const scheduleNext = () => {
      frameTimer = window.setTimeout(() => {
        const next = current + 1;
        if (next < playback.frames.length) {
          current = next;
          setFrame(current);
          scheduleNext();
          return;
        }
        if (playback.nextState) {
          setPlayback(statePlayback(playback.nextState));
          return;
        }
        if (playback.config.loop) {
          current = 0;
          setFrame(current);
          scheduleNext();
          return;
        }
        if (playback.completionState) {
          onCompleteRef.current(playback.completionState);
        }
      }, animationFrameDuration(playback.config, current, fpsMultiplier));
    };
    scheduleNext();

    const completion =
      playback.config.durationMs === undefined || playback.completionState === undefined
        ? undefined
        : window.setTimeout(
            () => onCompleteRef.current(playback.completionState!),
            playback.config.durationMs,
          );

    return () => {
      if (frameTimer !== undefined) window.clearTimeout(frameTimer);
      if (completion !== undefined) window.clearTimeout(completion);
    };
  }, [fpsMultiplier, playback]);

  return (
    <img
      className="pet-sprite"
      src={playback.frames[frame] ?? playback.frames[0]}
      alt=""
      draggable={false}
      style={{ transform: direction === "left" ? "scaleX(-1)" : undefined }}
    />
  );
}
