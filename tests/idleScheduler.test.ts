import { IdleScheduler, type Clock } from "../src/pet/idleScheduler";
import { DEFAULT_SETTINGS } from "../src/settings/defaults";

it("maintains exactly one timer", () => {
  let created = 0;
  let cleared = 0;
  const clock: Clock = {
    setTimeout: (() => {
      created += 1;
      return created;
    }) as unknown as Clock["setTimeout"],
    clearTimeout: () => {
      cleared += 1;
    },
  };
  const scheduler = new IdleScheduler(clock, () => 0.5);
  scheduler.schedule(DEFAULT_SETTINGS.idleScheduler, () => undefined);
  scheduler.schedule(DEFAULT_SETTINGS.idleScheduler, () => undefined);
  expect(created).toBe(2);
  expect(cleared).toBe(1);
  expect(scheduler.active).toBe(true);
  scheduler.cancel();
  expect(scheduler.active).toBe(false);
});
