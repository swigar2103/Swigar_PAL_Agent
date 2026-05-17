/** 后台预生成 / 排队卷 的工作流条目，不应与当前组卷会话混在一起展示。 */
export function isBackgroundWorkflow(log: {
  message: string;
  data?: Record<string, unknown> | null;
}): boolean {
  const d = log.data || {};
  if (d.background === true) return true;
  if (d.phase === "queued_prefetch") return true;
  if (d.assembly_mode === "full_prefetch") return true;
  const msg = log.message || "";
  if (msg.includes("后台预生成") || msg.includes("已预生成（排队）")) return true;
  return false;
}

export function filterSessionWorkflowLogs<
  T extends { message: string; data?: Record<string, unknown> | null },
>(logs: T[]): T[] {
  return logs.filter((l) => !isBackgroundWorkflow(l));
}
