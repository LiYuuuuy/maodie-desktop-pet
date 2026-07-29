import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { ANIMATION_CONFIG, VISUAL_STATES } from "../src/pet/types";

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

  it("keeps the generated subject anchored and color-matched", () => {
    const report = JSON.parse(
      readFileSync(resolve("artifacts/asset-work/v2/quality-report.json"), "utf8"),
    ) as {
      states: Record<
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
  });
});
