import { PhysicalPosition, availableMonitors, getCurrentWindow } from "@tauri-apps/api/window";
import type { AppSettings } from "../settings/schema";

export function advanceWalkingPosition(
  currentX: number,
  direction: "left" | "right",
  distance: number,
  minX: number,
  maxX: number,
): { x: number; direction: "left" | "right" } {
  const safeMaxX = Math.max(minX, maxX);
  let nextDirection = direction;
  let x = currentX + (direction === "right" ? distance : -distance);
  if (x <= minX || x >= safeMaxX) {
    nextDirection = direction === "right" ? "left" : "right";
    x = Math.min(safeMaxX, Math.max(minX, x));
  }
  return { x, direction: nextDirection };
}

export function startWalking(
  direction: "left" | "right",
  settings: AppSettings,
  onDirection: (direction: "left" | "right") => void,
): () => void {
  let active = true;
  let currentDirection = direction;
  const speed =
    settings.movement.minSpeed +
    Math.random() * Math.max(0, settings.movement.maxSpeed - settings.movement.minSpeed);
  let last = performance.now();
  let targetX: number | undefined;
  const appWindow = getCurrentWindow();

  const tick = async (now: number) => {
    if (!active) return;
    const elapsed = Math.min(0.1, (now - last) / 1_000);
    last = now;
    try {
      const [position, windowSize, scaleFactor, monitors] = await Promise.all([
        appWindow.outerPosition(),
        appWindow.outerSize(),
        appWindow.scaleFactor(),
        availableMonitors(),
      ]);
      const monitor =
        monitors.find((item) => {
          const left = item.position.x;
          const top = item.position.y;
          return (
            position.x >= left &&
            position.x < left + item.size.width &&
            position.y >= top &&
            position.y < top + item.size.height
          );
        }) ?? monitors[0];
      if (monitor) {
        const minX = monitor.workArea.position.x;
        const maxX =
          monitor.workArea.position.x + monitor.workArea.size.width - windowSize.width;
        if (targetX === undefined || Math.abs(targetX - position.x) > 3 * scaleFactor) {
          targetX = position.x;
        }
        const next = advanceWalkingPosition(
          targetX,
          currentDirection,
          speed * scaleFactor * elapsed,
          minX,
          maxX,
        );
        targetX = next.x;
        if (next.direction !== currentDirection) {
          currentDirection = next.direction;
          onDirection(currentDirection);
        }
        await appWindow.setPosition(
          new PhysicalPosition(Math.round(targetX), position.y),
        );
      }
    } catch {
      // Browser preview and transient monitor changes simply pause one frame.
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  return () => {
    active = false;
  };
}
