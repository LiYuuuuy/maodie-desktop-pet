import { useEffect, useMemo, useRef, useState } from "react";
import { ANIMATION_CONFIG, type VisualState } from "../pet/types";

const frameModules = import.meta.glob<string>("../assets/pet/*/*.png", {
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

type Props = {
  state: VisualState;
  direction: "left" | "right";
  fpsMultiplier?: number;
  onComplete: (state: VisualState) => void;
};

export function PetSprite({ state, direction, fpsMultiplier = 1, onComplete }: Props) {
  const frames = useMemo(() => framesFor(state), [state]);
  const [frame, setFrame] = useState(0);
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    setFrame(0);
    const config = ANIMATION_CONFIG[state];
    const frameDuration = 1_000 / Math.max(1, config.fps * fpsMultiplier);
    const interval = window.setInterval(() => {
      setFrame((current) => {
        const next = current + 1;
        if (next < frames.length) return next;
        if (config.loop) return 0;
        window.clearInterval(interval);
        return current;
      });
    }, frameDuration);
    const completionDelay =
      config.durationMs ?? (config.loop ? undefined : frameDuration * Math.max(1, frames.length));
    const completion =
      completionDelay === undefined
        ? undefined
        : window.setTimeout(() => onCompleteRef.current(state), completionDelay);
    return () => {
      window.clearInterval(interval);
      if (completion !== undefined) window.clearTimeout(completion);
    };
  }, [fpsMultiplier, frames.length, state]);

  return (
    <img
      className="pet-sprite"
      src={frames[frame] ?? frames[0]}
      alt=""
      draggable={false}
      style={{ transform: direction === "left" ? "scaleX(-1)" : undefined }}
    />
  );
}
