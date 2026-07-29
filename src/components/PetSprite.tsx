import { useEffect, useMemo, useState } from "react";
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

  useEffect(() => {
    setFrame(0);
    const config = ANIMATION_CONFIG[state];
    const startedAt = performance.now();
    const interval = window.setInterval(() => {
      setFrame((current) => {
        if (config.durationMs && performance.now() - startedAt >= config.durationMs) {
          window.clearInterval(interval);
          queueMicrotask(() => onComplete(state));
          return current;
        }
        const next = current + 1;
        if (next < frames.length) return next;
        if (config.loop) return 0;
        window.clearInterval(interval);
        queueMicrotask(() => onComplete(state));
        return current;
      });
    }, 1_000 / Math.max(1, config.fps * fpsMultiplier));
    return () => window.clearInterval(interval);
  }, [fpsMultiplier, frames.length, onComplete, state]);

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
