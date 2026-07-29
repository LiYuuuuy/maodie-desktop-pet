export function deduplicatePaths(paths: string[]): string[] {
  const seen = new Set<string>();
  return paths.filter((path) => {
    const normalized = path.trim();
    if (!normalized || seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });
}

export type TrashBatchResult = {
  succeeded: number;
  failed: number;
  errors: Array<{ code: string; message: string }>;
};

export function summarizeTrashResult(result: TrashBatchResult): string {
  if (result.failed === 0) return `耄耋吃掉了 ${result.succeeded} 个文件，可在回收站恢复`;
  if (result.succeeded === 0) return `投喂失败：${result.errors[0]?.message ?? "文件没有移动"}`;
  return `成功吃掉 ${result.succeeded} 个，${result.failed} 个失败`;
}
