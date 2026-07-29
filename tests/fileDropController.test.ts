import { deduplicatePaths, summarizeTrashResult } from "../src/pet/fileDropController";

describe("file feeding", () => {
  it("deduplicates paths without altering unicode", () => {
    expect(deduplicatePaths(["/tmp/猫.txt", "/tmp/猫.txt", " ", "/tmp/a b.txt"])).toEqual([
      "/tmp/猫.txt",
      "/tmp/a b.txt",
    ]);
  });

  it("summarizes partial success", () => {
    expect(
      summarizeTrashResult({
        succeeded: 2,
        failed: 1,
        errors: [{ code: "protected_path", message: "拒绝系统文件" }],
      }),
    ).toBe("成功吃掉 2 个，1 个失败");
  });
});
