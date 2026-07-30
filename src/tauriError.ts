type StructuredError = {
  code?: unknown;
  message?: unknown;
  error?: unknown;
};

export function commandErrorMessage(reason: unknown, fallback = "操作失败"): string {
  if (reason instanceof Error && reason.message.trim()) return reason.message;
  if (typeof reason === "string" && reason.trim()) return reason;
  if (reason && typeof reason === "object") {
    const value = reason as StructuredError;
    if (typeof value.message === "string" && value.message.trim()) return value.message;
    if (typeof value.error === "string" && value.error.trim()) return value.error;
    if (typeof value.code === "string" && value.code.trim()) return `${fallback}（${value.code}）`;
  }
  return fallback;
}
