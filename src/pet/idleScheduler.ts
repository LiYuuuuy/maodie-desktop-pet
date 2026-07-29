import type { AppSettings } from "../settings/schema";

export type Clock = {
  setTimeout(callback: () => void, delay: number): ReturnType<typeof setTimeout>;
  clearTimeout(id: ReturnType<typeof setTimeout>): void;
};

export class IdleScheduler {
  private timer?: ReturnType<typeof setTimeout>;

  constructor(
    private readonly clock: Clock = window,
    private readonly random: () => number = Math.random,
  ) {}

  schedule(config: AppSettings["idleScheduler"], callback: (random: number) => void): void {
    this.cancel();
    if (!config.enabled) return;
    const span = Math.max(0, config.maxDelayMs - config.minDelayMs);
    const delay = config.minDelayMs + this.random() * span;
    this.timer = this.clock.setTimeout(() => {
      this.timer = undefined;
      callback(this.random());
    }, delay);
  }

  cancel(): void {
    if (this.timer !== undefined) this.clock.clearTimeout(this.timer);
    this.timer = undefined;
  }

  get active(): boolean {
    return this.timer !== undefined;
  }
}
