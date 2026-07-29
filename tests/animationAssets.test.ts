import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import {
  ANIMATION_CONFIG,
  IDLE_TRANSITION_PAIRS,
  VISUAL_STATES,
  resolveIdleTransition,
} from "../src/pet/types";

describe("animation asset contract", () => {
  it.each(VISUAL_STATES)("%s contains sixteen 512px RGBA frames", (state) => {
    const directory = resolve("src/assets/pet", state);
    const names = readdirSync(directory).filter((name) => name.endsWith(".png")).sort();
    expect(names).toEqual(Array.from({ length: 16 }, (_, index) => `${index.toString().padStart(2, "0")}.png`));

    for (const name of names) {
      const png = readFileSync(resolve(directory, name));
      expect(png.readUInt32BE(16)).toBe(512);
      expect(png.readUInt32BE(20)).toBe(512);
      expect(png[25]).toBe(6);
    }
  });

  it("uses restrained playback rates for the sixteen-frame sequences", () => {
    expect(Object.fromEntries(VISUAL_STATES.map((state) => [state, ANIMATION_CONFIG[state].fps]))).toEqual({
      sitting: 8,
      walking: 10,
      sleeping: 6,
      happy: 12,
      petting: 10,
      hissing: 10,
    });
  });

  it("contains one reversible eight-frame clip for every idle-state pair", () => {
    for (const [start, end] of IDLE_TRANSITION_PAIRS) {
      const name = `${start}-${end}`;
      const directory = resolve("src/assets/pet-transitions", name);
      const names = readdirSync(directory).filter((file) => file.endsWith(".png")).sort();
      expect(names).toEqual(
        Array.from({ length: 8 }, (_, index) => `${index.toString().padStart(2, "0")}.png`),
      );
      expect(resolveIdleTransition(start, end)).toEqual({ name, reverse: false });
      expect(resolveIdleTransition(end, start)).toEqual({ name, reverse: true });
    }
  });

  it("uses a fast attack, visible peak hold, and slower recovery for reactions", () => {
    for (const state of ["petting", "hissing"] as const) {
      const timings = ANIMATION_CONFIG[state].frameDurationsMs;
      expect(timings).toHaveLength(16);
      expect(new Set(timings).size).toBeGreaterThan(5);
      expect(timings!.slice(0, 6).reduce((sum, duration) => sum + duration, 0)).toBeLessThan(320);
      expect(timings!.slice(6, 10).reduce((sum, duration) => sum + duration, 0)).toBeGreaterThan(300);
    }
  });

  it("keeps the generated subject anchored and color-matched", () => {
    const report = JSON.parse(
      readFileSync(resolve("artifacts/asset-work/v3/quality-report.json"), "utf8"),
    ) as {
      states: Record<
        string,
        {
          frameCount: number;
          maxCenterDriftPx: number;
          maxBaselineDriftPx: number;
          maxFurColorDistance: number;
          maxHeadWidthGrowthRatio: number;
        }
      >;
      idleTransitions: Record<
        string,
        {
          frameCount: number;
          maxCenterDriftPx: number;
          maxBaselineDriftPx: number;
          maxFurColorDistance: number;
        }
      >;
    };

    for (const state of VISUAL_STATES) {
      expect(report.states[state].frameCount).toBe(16);
      expect(report.states[state].maxCenterDriftPx).toBeLessThanOrEqual(3);
      expect(report.states[state].maxBaselineDriftPx).toBeLessThanOrEqual(1);
      expect(report.states[state].maxFurColorDistance).toBeLessThanOrEqual(4);
    }

    expect(report.states.petting.maxHeadWidthGrowthRatio).toBeGreaterThanOrEqual(1.25);
    expect(report.states.hissing.maxHeadWidthGrowthRatio).toBeGreaterThanOrEqual(1.25);

    for (const transition of Object.values(report.idleTransitions)) {
      expect(transition.frameCount).toBe(8);
      expect(transition.maxCenterDriftPx).toBeLessThanOrEqual(2);
      expect(transition.maxBaselineDriftPx).toBeLessThanOrEqual(1);
      expect(transition.maxFurColorDistance).toBeLessThanOrEqual(4);
    }
  });
});
