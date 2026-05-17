/** PAL Paper-Agent architecture graph for live debug dashboard. */

export type PaperModuleId =
  | "input"
  | "event_bus"
  | "orchestrator"
  | "paper_plan"
  | "mistake_review"
  | "retrieve"
  | "generate"
  | "validate"
  | "paper_validate"
  | "tools"
  | "llm"
  | "memory"
  | "paper_out"
  | "evaluator"
  | "feedback"
  | "situation"
  | "next_adapt";

export type PaperModuleDef = {
  id: PaperModuleId;
  name: string;
  nameEn: string;
  layer: PaperLayerId;
  color: string;
  description: string;
  pipelineOrder?: number;
};

export type PaperLayerId =
  | "ingress"
  | "control"
  | "generation"
  | "infra"
  | "delivery"
  | "answer"
  | "adapt";

export type PaperLayerDef = {
  id: PaperLayerId;
  label: string;
  y: number;
  height: number;
  tint: string;
};

export const PAPER_LAYERS: PaperLayerDef[] = [
  { id: "ingress", label: "输入", y: 8, height: 56, tint: "rgba(34, 197, 94, 0.06)" },
  { id: "control", label: "编排控制", y: 72, height: 72, tint: "rgba(139, 92, 246, 0.07)" },
  { id: "generation", label: "组卷流水线", y: 152, height: 118, tint: "rgba(99, 102, 241, 0.06)" },
  { id: "infra", label: "基础设施", y: 278, height: 62, tint: "rgba(100, 116, 139, 0.06)" },
  { id: "delivery", label: "试卷交付", y: 348, height: 56, tint: "rgba(249, 115, 22, 0.07)" },
  { id: "answer", label: "答题判题", y: 412, height: 56, tint: "rgba(239, 68, 68, 0.06)" },
  { id: "adapt", label: "闭环适配", y: 476, height: 72, tint: "rgba(34, 197, 94, 0.05)" },
];

export const PAPER_GRAPH_SIZE = { width: 920, height: 560 };

export const NODE_BOX = { w: 96, h: 34 };

export const PAPER_MODULES: PaperModuleDef[] = [
  {
    id: "input",
    name: "输入层",
    nameEn: "Input",
    layer: "ingress",
    color: "#22c55e",
    description: "学生作答、学习事件、题库、教学目标。",
  },
  {
    id: "event_bus",
    name: "事件总线",
    nameEn: "Event Bus",
    layer: "ingress",
    color: "#334155",
    description: "onSessionStart / onAnswer / onPaperFinished 分发。",
  },
  {
    id: "orchestrator",
    name: "Paper 编排",
    nameEn: "Orchestrator",
    layer: "control",
    color: "#8b5cf6",
    description: "PaperOrchestrator 总控：Plan → 检索 → 生成 → 校验 → 组卷。",
  },
  {
    id: "paper_plan",
    name: "组卷规划",
    nameEn: "Plan",
    layer: "generation",
    color: "#7c3aed",
    description: "主/辅知识点簇、难度带、策略。",
    pipelineOrder: 1,
  },
  {
    id: "mistake_review",
    name: "往期错题",
    nameEn: "Mistake",
    layer: "generation",
    color: "#d97706",
    description: "错题混入 + 卷内去重。",
    pipelineOrder: 2,
  },
  {
    id: "retrieve",
    name: "题库检索",
    nameEn: "Retrieve",
    layer: "generation",
    color: "#6366f1",
    description: "分配额检索 4 道 DB 种子。",
    pipelineOrder: 3,
  },
  {
    id: "generate",
    name: "AI 变式",
    nameEn: "Generate",
    layer: "generation",
    color: "#4f46e5",
    description: "G1–G6 槽位、三级相似度、错题模式 targeting。",
    pipelineOrder: 4,
  },
  {
    id: "validate",
    name: "单题校验",
    nameEn: "Validate",
    layer: "generation",
    color: "#4338ca",
    description: "泄露/词性/等级 + 打分选入。",
    pipelineOrder: 5,
  },
  {
    id: "paper_validate",
    name: "卷级校验",
    nameEn: "Assembly",
    layer: "generation",
    color: "#312e81",
    description: "10 题结构、KP 混排、卷内多样性。",
    pipelineOrder: 6,
  },
  {
    id: "tools",
    name: "工具层",
    nameEn: "Tools",
    layer: "infra",
    color: "#64748b",
    description: "QuestionBank、PaperBuilder、Similarity。",
  },
  {
    id: "llm",
    name: "LLM",
    nameEn: "LLM",
    layer: "infra",
    color: "#0284c7",
    description: "百炼异步线程池：规划/生成/修订。",
  },
  {
    id: "memory",
    name: "MemPalace",
    nameEn: "Memory",
    layer: "infra",
    color: "#2563eb",
    description: "答题记忆写入与召回。",
  },
  {
    id: "paper_out",
    name: "10 题试卷",
    nameEn: "Paper",
    layer: "delivery",
    color: "#ea580c",
    description: "DB/GEN 交错组卷输出。",
  },
  {
    id: "evaluator",
    name: "规则判题",
    nameEn: "Evaluator",
    layer: "answer",
    color: "#dc2626",
    description: "EvaluatorTool（无 LLM）。",
  },
  {
    id: "feedback",
    name: "反馈",
    nameEn: "Feedback",
    layer: "answer",
    color: "#e11d48",
    description: "解析、正确答案、游戏 Impact。",
  },
  {
    id: "situation",
    name: "学情更新",
    nameEn: "Situation",
    layer: "adapt",
    color: "#64748b",
    description: "画像、正确率、薄弱点。",
  },
  {
    id: "next_adapt",
    name: "下一卷",
    nameEn: "Next",
    layer: "adapt",
    color: "#16a34a",
    description: "预生成 queued 卷 + 激活。",
  },
];

/** Layered layout — left-to-right pipeline in generation band. */
export const PAPER_NODE_POSITIONS: Record<PaperModuleId, { x: number; y: number }> = {
  input: { x: 460, y: 36 },
  event_bus: { x: 460, y: 100 },
  orchestrator: { x: 460, y: 168 },
  paper_plan: { x: 88, y: 218 },
  mistake_review: { x: 200, y: 218 },
  retrieve: { x: 312, y: 218 },
  generate: { x: 424, y: 218 },
  validate: { x: 536, y: 218 },
  paper_validate: { x: 648, y: 218 },
  tools: { x: 520, y: 308 },
  llm: { x: 680, y: 308 },
  memory: { x: 820, y: 168 },
  paper_out: { x: 460, y: 376 },
  evaluator: { x: 380, y: 440 },
  feedback: { x: 540, y: 440 },
  situation: { x: 360, y: 512 },
  next_adapt: { x: 560, y: 512 },
};

export type PaperEdgeKind = "flow" | "support" | "loop";

export type PaperEdgeDef = {
  from: PaperModuleId;
  to: PaperModuleId;
  kind: PaperEdgeKind;
};

/** 白板拓扑：仅主流水线 + 少量竖向支撑，避免虚线交叉 */
export const PAPER_DISPLAY_EDGES: PaperEdgeDef[] = [
  { from: "input", to: "event_bus", kind: "flow" },
  { from: "event_bus", to: "orchestrator", kind: "flow" },
  { from: "orchestrator", to: "paper_plan", kind: "flow" },
  { from: "paper_plan", to: "mistake_review", kind: "flow" },
  { from: "mistake_review", to: "retrieve", kind: "flow" },
  { from: "retrieve", to: "generate", kind: "flow" },
  { from: "generate", to: "validate", kind: "flow" },
  { from: "validate", to: "paper_validate", kind: "flow" },
  { from: "paper_validate", to: "paper_out", kind: "flow" },
  { from: "paper_out", to: "evaluator", kind: "flow" },
  { from: "evaluator", to: "feedback", kind: "flow" },
  { from: "feedback", to: "situation", kind: "flow" },
  { from: "situation", to: "next_adapt", kind: "flow" },
  { from: "orchestrator", to: "tools", kind: "support" },
  { from: "generate", to: "llm", kind: "support" },
  { from: "paper_plan", to: "llm", kind: "support" },
  { from: "orchestrator", to: "memory", kind: "support" },
];

export const PAPER_EDGES: PaperEdgeDef[] = [
  { from: "input", to: "event_bus", kind: "flow" },
  { from: "event_bus", to: "orchestrator", kind: "flow" },
  { from: "orchestrator", to: "paper_plan", kind: "flow" },
  { from: "paper_plan", to: "mistake_review", kind: "flow" },
  { from: "mistake_review", to: "retrieve", kind: "flow" },
  { from: "retrieve", to: "generate", kind: "flow" },
  { from: "generate", to: "validate", kind: "flow" },
  { from: "validate", to: "paper_validate", kind: "flow" },
  { from: "paper_validate", to: "paper_out", kind: "flow" },
  { from: "paper_out", to: "evaluator", kind: "flow" },
  { from: "evaluator", to: "feedback", kind: "flow" },
  { from: "feedback", to: "situation", kind: "flow" },
  { from: "situation", to: "next_adapt", kind: "flow" },
  { from: "next_adapt", to: "orchestrator", kind: "loop" },
  { from: "orchestrator", to: "memory", kind: "support" },
  { from: "memory", to: "orchestrator", kind: "loop" },
  { from: "generate", to: "llm", kind: "support" },
  { from: "paper_plan", to: "llm", kind: "support" },
  { from: "llm", to: "generate", kind: "loop" },
  { from: "tools", to: "retrieve", kind: "support" },
  { from: "tools", to: "generate", kind: "support" },
  { from: "tools", to: "paper_out", kind: "support" },
  { from: "orchestrator", to: "tools", kind: "support" },
];

export type ModuleActivityState = "cold" | "seen" | "warm" | "active";

export type ModuleActivity = {
  state: ModuleActivityState;
  count: number;
  lastStep?: string;
  lastTs?: string;
};

export function getPaperModule(id: PaperModuleId): PaperModuleDef | undefined {
  return PAPER_MODULES.find((m) => m.id === id);
}

export function paperStepToModule(
  step?: string,
  phase?: string,
  category?: string,
  data?: Record<string, unknown> | null,
  message?: string
): PaperModuleId | null {
  const mod = data?.module;
  if (typeof mod === "string") {
    const m = mod as PaperModuleId;
    if (PAPER_MODULES.some((x) => x.id === m)) return m;
  }
  const raw = (message || step || "").toLowerCase();
  if (raw.includes("step1") || raw.includes("analyse_sources")) return "paper_plan";
  if (raw.includes("step3") || raw.includes("transformation_plan")) return "paper_plan";
  if (raw.includes("step4") || raw.includes("over_generate")) return "generate";
  if (raw.includes("step5") || raw.includes("filter_duplicate")) return "validate";
  if (raw.includes("step6_revise")) return "llm";
  if (raw.includes("step6_score")) return "validate";
  if (raw.includes("step7") || raw.includes("assembly_validate")) return "paper_validate";
  if (raw.includes("cold_start")) return "retrieve";
  if (raw.includes("reserve") || raw.includes("hybrid")) return "retrieve";
  if (raw.includes("promote") || raw.includes("queued")) return "next_adapt";

  const skill = String(data?.skill || "");
  const skillMap: Record<string, PaperModuleId> = {
    question_generate: "generate",
    question_validate: "validate",
    question_revise: "generate",
    paper_plan: "paper_plan",
    mistake_review: "mistake_review",
    paper_validate: "paper_validate",
    retrieve: "retrieve",
    orchestrator: "orchestrator",
    llm: "llm",
    paper_out: "paper_out",
    next_adapt: "next_adapt",
    evaluator: "evaluator",
  };
  if (skill === "paper_assembly_validate") return "paper_validate";
  if (skill && skillMap[skill]) return skillMap[skill];

  const s = (step || raw).toLowerCase();
  const p = (phase || "").toLowerCase();
  const c = (category || "").toLowerCase();

  if (p === "llm" || s.startsWith("llm_")) return "llm";
  if (s.includes("paper_validate")) return "paper_validate";
  if (s.includes("mistake")) return "mistake_review";
  if (s.includes("retrieve")) return "retrieve";
  if (s.includes("step4") || s.includes("generate")) return "generate";
  if (s.includes("step5") || s.includes("step6_score") || s.includes("validate")) return "validate";
  if (s.includes("step6_revise")) return "llm";
  if (s.includes("plan")) return "paper_plan";
  if (s.includes("assemble") || s.includes("paper_out")) return "paper_out";
  if (c === "记忆" || s.includes("memory") || s.includes("mempalace")) return "memory";
  if (c === "调整" || s.includes("adapt") || s.includes("profile")) return "situation";
  if (c === "答题" || s.includes("answer") || s.includes("evaluat")) return "evaluator";
  if (c === "出题" || s.includes("orchestrat")) return "orchestrator";
  if (s.includes("feedback")) return "feedback";
  if (s.includes("situation")) return "situation";
  if (s.includes("next")) return "next_adapt";
  return null;
}

/** Orthogonal SVG path between node centers. */
export function edgePath(
  from: { x: number; y: number },
  to: { x: number; y: number },
  kind: PaperEdgeKind
): string {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (kind === "loop" && Math.abs(dx) > 80) {
    const bump = Math.min(60, Math.abs(dy) * 0.35 + 24);
    const midX = from.x + dx * 0.5;
    return `M ${from.x} ${from.y} C ${midX} ${from.y - bump}, ${midX} ${to.y - bump}, ${to.x} ${to.y}`;
  }
  if (Math.abs(dx) < 36 || Math.abs(dy) < 36) {
    return `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
  }
  const midY = from.y + dy * 0.5;
  return `M ${from.x} ${from.y} L ${from.x} ${midY} L ${to.x} ${midY} L ${to.x} ${to.y}`;
}

export function buildModuleActivity(
  traces: Array<{ paperModuleId: PaperModuleId | null; step: string; ts: string }>,
  activeId: PaperModuleId | null
): Record<PaperModuleId, ModuleActivity> {
  const out = {} as Record<PaperModuleId, ModuleActivity>;
  for (const m of PAPER_MODULES) {
    out[m.id] = { state: "cold", count: 0 };
  }
  const recent = traces.filter((t): t is { paperModuleId: PaperModuleId; step: string; ts: string } =>
    Boolean(t.paperModuleId)
  ).slice(-40);
  for (const t of recent) {
    const id = t.paperModuleId!;
    const cur = out[id];
    cur.count += 1;
    cur.lastStep = t.step;
    cur.lastTs = t.ts;
    cur.state = cur.state === "cold" ? "seen" : cur.state;
  }
  if (recent.length > 0) {
    const lastFew = recent.slice(-8);
    for (const t of lastFew) {
      if (t.paperModuleId) out[t.paperModuleId].state = "warm";
    }
  }
  if (activeId) {
    out[activeId].state = "active";
  }
  return out;
}

export function getPipelineModules(): PaperModuleDef[] {
  return PAPER_MODULES.filter((m) => m.pipelineOrder != null).sort(
    (a, b) => (a.pipelineOrder || 0) - (b.pipelineOrder || 0)
  );
}
