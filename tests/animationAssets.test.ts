import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import {
  ANIMATION_CONFIG,
  IDLE_TRANSITION_CONFIG,
  IDLE_TRANSITION_PAIRS,
  VISUAL_STATES,
  nextAnimationFrame,
  resolveIdleTransition,
} from "../src/pet/types";

describe("animation asset contract", () => {
  const expectedFrameCounts = {
    sitting: 32,
    walking: 64,
    sleeping: 32,
    happy: 32,
    petting: 33,
    hissing: 31,
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
      sitting: 16,
      walking: 24,
      sleeping: 12,
      happy: 24,
      petting: 24,
      hissing: 24,
    });
    for (const state of VISUAL_STATES) {
      expect(ANIMATION_CONFIG[state]).not.toHaveProperty("frameDurationsMs");
    }
  });

  it("contains one reversible approved eight-frame clip for every idle-state pair", () => {
    expect(IDLE_TRANSITION_CONFIG.fps).toBe(10);
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
      readFileSync(resolve("artifacts/asset-work/v6/quality-report.json"), "utf8"),
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
      readFileSync(resolve("artifacts/asset-work/v6/quality-report.json"), "utf8"),
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
          maxAdjacentVisualChange: number;
          maxToMedianAdjacentVisualChangeRatio: number;
        }
      >;
      idleTransitions: Record<
        string,
        {
          frameCount: number;
          maxCenterDriftPx: number;
          maxBaselineDriftPx: number;
          maxFurColorDistance: number;
          source: string;
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
    expect(report.states.walking.maxAdjacentVisualChange).toBeLessThanOrEqual(22);
    expect(report.states.walking.maxToMedianAdjacentVisualChangeRatio).toBeLessThanOrEqual(1.7);

    for (const state of ["sitting", "walking", "sleeping"] as const) {
      expect(report.states[state].maxCenterDriftPx).toBeLessThanOrEqual(1);
      expect(report.states[state].maxBaselineDriftPx).toBe(0);
    }

    const sittingAnchor = readFileSync(resolve("src/assets/pet/sitting/00.png"));
    for (const state of ["petting", "hissing"] as const) {
      const directory = resolve("src/assets/pet", state);
      const names = readdirSync(directory).filter((name) => name.endsWith(".png")).sort();
      expect(readFileSync(resolve(directory, names[0]))).toEqual(sittingAnchor);
      expect(readFileSync(resolve(directory, names.at(-1)!))).toEqual(sittingAnchor);
    }

    for (const transition of Object.values(report.idleTransitions)) {
      expect(transition.frameCount).toBe(8);
      expect(transition.maxCenterDriftPx).toBeLessThanOrEqual(1);
      expect(transition.maxBaselineDriftPx).toBe(0);
      expect(transition.maxFurColorDistance).toBeLessThanOrEqual(4);
      expect(transition.source).toMatch(
        /^artifacts\/asset-work\/v6\/approved-idle-transition-frames\//,
      );
    }
  });

  it("loops the calm sitting half and only sometimes enters the blink tail", () => {
    const config = ANIMATION_CONFIG.sitting;
    expect(config.optionalTail).toEqual({ startFrame: 16, playProbability: 0.25 });
    expect(nextAnimationFrame(15, 32, config, 0.24)).toBe(16);
    expect(nextAnimationFrame(15, 32, config, 0.25)).toBe(0);
    expect(nextAnimationFrame(31, 32, config, 0)).toBe(0);
  });
});
