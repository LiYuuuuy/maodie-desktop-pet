import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { VISUAL_STATES } from "../src/pet/types";

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
});
