import { classifyGesture } from "../src/pet/clickGesture";

const start = { x: 10, y: 10, time: 100 };

describe("click gesture", () => {
  it("uses the six-pixel and 500ms thresholds", () => {
    expect(classifyGesture(start, { x: 15.9, y: 10, time: 599 })).toBe("click");
    expect(classifyGesture(start, { x: 16, y: 10, time: 200 })).toBe("drag");
    expect(classifyGesture(start, { x: 10, y: 10, time: 600 })).toBe("long-press");
  });
});
