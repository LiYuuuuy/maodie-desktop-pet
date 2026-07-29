import { LogicalPosition, availableMonitors, getCurrentWindow } from "@tauri-apps/api/window";
import type { AppSettings } from "../settings/schema";

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
  const appWindow = getCurrentWindow();

  const tick = async (now: number) => {
    if (!active) return;
    const elapsed = Math.min(0.1, (now - last) / 1_000);
    last = now;
    try {
      const [position, scaleFactor, monitors] = await Promise.all([
        appWindow.outerPosition(),
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
        const minX = monitor.workArea.position.x / scaleFactor;
        const maxX =
          (monitor.workArea.position.x + monitor.workArea.size.width) / scaleFactor -
          256 * settings.pet.scale;
        let x = position.x / scaleFactor + (currentDirection === "right" ? 1 : -1) * speed * elapsed;
        if (x <= minX || x >= maxX) {
          currentDirection = currentDirection === "right" ? "left" : "right";
          onDirection(currentDirection);
          x = Math.min(maxX, Math.max(minX, x));
        }
        await appWindow.setPosition(new LogicalPosition(x, position.y / scaleFactor));
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
