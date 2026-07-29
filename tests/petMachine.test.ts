import { DEFAULT_SETTINGS } from "../src/settings/defaults";
import { chooseIdleState, INITIAL_PET_STATE, reducePet } from "../src/pet/petMachine";

describe("pet state machine", () => {
  it("starts sitting and completes every interaction back to sitting", () => {
    for (const random of [0, 1]) {
      const interaction = reducePet(INITIAL_PET_STATE, { type: "LEFT_CLICK", random }, DEFAULT_SETTINGS);
      expect(["petting", "hissing"]).toContain(interaction.visual);
      expect(
        reducePet(
          interaction,
          { type: "ANIMATION_COMPLETE", state: interaction.visual },
          DEFAULT_SETTINGS,
        ).visual,
      ).toBe("sitting");
    }
    const happy = reducePet(
      INITIAL_PET_STATE,
      { type: "FILE_TRASH_SUCCESS", count: 1 },
      DEFAULT_SETTINGS,
    );
    expect(happy.visual).toBe("happy");
    expect(
      reducePet(happy, { type: "ANIMATION_COMPLETE", state: "happy" }, DEFAULT_SETTINGS).visual,
    ).toBe("sitting");
  });

  it("honors hiss probability boundaries", () => {
    const never = structuredClone(DEFAULT_SETTINGS);
    never.interaction.hissProbability = 0;
    expect(reducePet(INITIAL_PET_STATE, { type: "LEFT_CLICK", random: 0 }, never).visual).toBe(
      "petting",
    );
    const always = structuredClone(DEFAULT_SETTINGS);
    always.interaction.hissProbability = 1;
    expect(reducePet(INITIAL_PET_STATE, { type: "LEFT_CLICK", random: 0.999 }, always).visual).toBe(
      "hissing",
    );
  });

  it("does not immediately repeat idle states", () => {
    for (const random of [0, 0.25, 0.5, 0.999]) {
      expect(chooseIdleState("sitting", random, DEFAULT_SETTINGS.idleScheduler)).not.toBe("sitting");
    }
  });

  it("queues chat until an interaction completes", () => {
    const busy = { ...INITIAL_PET_STATE, visual: "hissing" as const };
    const queued = reducePet(busy, { type: "RIGHT_CLICK" }, DEFAULT_SETTINGS);
    expect(queued.pendingChat).toBe(true);
    const complete = reducePet(
      queued,
      { type: "ANIMATION_COMPLETE", state: "hissing" },
      DEFAULT_SETTINGS,
    );
    expect(complete.mode).toBe("chat_open");
  });

  it("leaves dragging mode when the native window drag finishes", () => {
    const dragging = reducePet(INITIAL_PET_STATE, { type: "PET_DRAG_START" }, DEFAULT_SETTINGS);
    expect(dragging.mode).toBe("dragging_pet");
    const finished = reducePet(dragging, { type: "PET_DRAG_END" }, DEFAULT_SETTINGS);
    expect(finished.mode).toBeNull();
    expect(finished.visual).toBe("sitting");
  });
});
