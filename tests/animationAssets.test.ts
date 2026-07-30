import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import {
  ANIMATION_CONFIG,
  IDLE_TRANSITION_PAIRS,
  VISUAL_STATES,
  resolveIdleTransition,
} from "../src/pet/types";

describe("animation asset contract", () => {
  const expectedFrameCounts = {
    sitting: 16,
    walking: 32,
    sleeping: 16,
    happy: 16,
    petting: 17,
    hissing: 16,
  } as const;

  it.each(VISUAL_STATES)("%s contains the intended 512px RGBA frame sequence", (state) => {
    const directory = resolve("src/assets/pet", state);
    const names = readdirSync(directory).filter((name) => name.endsWith(".png")).sort();
    expect(names).toEqual(
      Array.from(
        { length: expectedFrameCounts[state] },
        (_, index) => `${index.toString().padStart(2, "0")}.png`,
      ),
    );

    for (const name of names) {
      const png = readFileSync(resolve(directory, name));
      expect(png.readUInt32BE(16)).toBe(512);
      expect(png.readUInt32BE(20)).toBe(512);
      expect(png[25]).toBe(6);
    }
  });

  it("uses one fixed interval within each sequence", () => {
    expect(Object.fromEntries(VISUAL_STATES.map((state) => [state, ANIMATION_CONFIG[state].fps]))).toEqual({
      sitting: 8,
      walking: 16,
      sleeping: 6,
      happy: 12,
      petting: 12,
      hissing: 12,
    });
    for (const state of VISUAL_STATES) {
      expect(ANIMATION_CONFIG[state]).not.toHaveProperty("frameDurationsMs");
    }
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

  it("encodes reaction timing with different in-between counts", () => {
    const report = JSON.parse(
      readFileSync(resolve("artifacts/asset-work/v4/quality-report.json"), "utf8"),
    ) as {
      states: Record<
        string,
        {
          frameCount: number;
          fixedRatePlayback: boolean;
          insertionCounts: number[];
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

    expect(report.states.walking.insertionCounts).toEqual([3, 3, 3, 3, 3, 3, 3, 3]);
    expect(report.states.petting.insertionCounts).toEqual([0, 0, 1, 3, 3, 1, 1]);
    expect(report.states.hissing.insertionCounts).toEqual([0, 1, 0, 3, 0, 1, 3]);
    expect(new Set(report.states.petting.insertionCounts).size).toBeGreaterThan(2);
    expect(new Set(report.states.hissing.insertionCounts).size).toBeGreaterThan(2);
  });

  it("keeps the generated subject anchored, color-matched, and subtly scaled", () => {
    const report = JSON.parse(
      readFileSync(resolve("artifacts/asset-work/v4/quality-report.json"), "utf8"),
    ) as {
      states: Record<
        string,
        {
          frameCount: number;
          fixedRatePlayback: boolean;
          insertionCounts: number[];
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
      expect(report.states[state].frameCount).toBe(expectedFrameCounts[state]);
      expect(report.states[state].fixedRatePlayback).toBe(true);
      expect(report.states[state].maxCenterDriftPx).toBeLessThanOrEqual(3);
      expect(report.states[state].maxBaselineDriftPx).toBeLessThanOrEqual(1);
      expect(report.states[state].maxFurColorDistance).toBeLessThanOrEqual(4);
    }

    expect(report.states.petting.maxHeadWidthGrowthRatio).toBeLessThanOrEqual(1.08);
    expect(report.states.hissing.maxHeadWidthGrowthRatio).toBeLessThanOrEqual(1.08);

    for (const transition of Object.values(report.idleTransitions)) {
      expect(transition.frameCount).toBe(8);
      expect(transition.maxCenterDriftPx).toBeLessThanOrEqual(2);
      expect(transition.maxBaselineDriftPx).toBeLessThanOrEqual(1);
      expect(transition.maxFurColorDistance).toBeLessThanOrEqual(4);
    }
  });
});
