export type PointerSample = { x: number; y: number; time: number };

export function classifyGesture(
  start: PointerSample,
  end: PointerSample,
  distanceThreshold = 6,
  durationThreshold = 500,
): "click" | "drag" | "long-press" {
  const distance = Math.hypot(end.x - start.x, end.y - start.y);
  if (distance >= distanceThreshold) return "drag";
  return end.time - start.time < durationThreshold ? "click" : "long-press";
}
