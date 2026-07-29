import { advanceWalkingPosition } from "../src/pet/movementController";

describe("walking window movement", () => {
  it("advances in physical screen coordinates", () => {
    expect(advanceWalkingPosition(100, "right", 12, 0, 500)).toEqual({
      x: 112,
      direction: "right",
    });
    expect(advanceWalkingPosition(100, "left", 12, 0, 500)).toEqual({
      x: 88,
      direction: "left",
    });
  });

  it("clamps to the work area and reverses at either edge", () => {
    expect(advanceWalkingPosition(495, "right", 12, 0, 500)).toEqual({
      x: 500,
      direction: "left",
    });
    expect(advanceWalkingPosition(4, "left", 12, 0, 500)).toEqual({
      x: 0,
      direction: "right",
    });
  });

  it("handles a work area narrower than the pet window", () => {
    expect(advanceWalkingPosition(20, "right", 12, 40, 10)).toEqual({
      x: 40,
      direction: "left",
    });
  });
});
