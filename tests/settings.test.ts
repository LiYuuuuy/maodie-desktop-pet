import { DEFAULT_SETTINGS, migrateSettings } from "../src/settings/defaults";

describe("settings", () => {
  it("returns defaults for corrupt data", () => {
    expect(migrateSettings(null)).toEqual(DEFAULT_SETTINGS);
  });

  it("migrates partial values and clamps risky ranges", () => {
    const settings = migrateSettings({
      pet: { scale: 9 },
      interaction: { hissProbability: -1 },
      idleScheduler: { minDelayMs: 20_000, maxDelayMs: 4_000 },
    });
    expect(settings.pet.scale).toBe(2);
    expect(settings.interaction.hissProbability).toBe(0);
    expect(settings.idleScheduler.minDelayMs).toBe(4_000);
    expect(settings.idleScheduler.maxDelayMs).toBe(20_000);
  });
});
