export type ModuleId =
  | "game"
  | "events"
  | "memory"
  | "orchestrator"
  | "skills"
  | "tools"
  | "llm"
  | "situation"
  | "decision";

export interface ArchModule {
  id: ModuleId;
  name: string;
  nameEn: string;
  color: string;
  description: string;
  responsibilities: string[];
  apis?: string[];
}

export const ARCH_MODULES: ArchModule[] = [
  {
    id: "game",
    name: "游戏客户端",
    nameEn: "Game Client",
    color: "#22c55e",
    description: "TypeScript 网页游戏：地牢、NPC、战斗与嵌入式答题。",
    responsibilities: ["上报学习事件", "拉取并渲染 LearningDecision", "确认决策已展示"],
    apis: ["POST /v1/events", "GET /v1/decisions/.../pending"],
  },
  {
    id: "events",
    name: "学习事件层",
    nameEn: "Event Bus",
    color: "#3b82f6",
    description: "统一接收 onAnswer / onMistake 等回调，转化为学习信号。",
    responsibilities: ["事件 enrich", "触发调度", "Debug 广播"],
    apis: ["POST /v1/events", "WS /debug/stream"],
  },
  {
    id: "memory",
    name: "记忆宫殿",
    nameEn: "MemPalace Memory",
    color: "#8b5cf6",
    description: "每位学习者独立 palace：原文 Drawer + 索引 Closet + 时间知识图谱。",
    responsibilities: ["Verbatim 写入", "语义检索", "薄弱点时间线"],
  },
  {
    id: "situation",
    name: "学习情境",
    nameEn: "Learning Situation",
    color: "#06b6d4",
    description: "当前地图、NPC、最近错题、对话线程等短期上下文。",
    responsibilities: ["情境快照", "叙事钩子上下文"],
    apis: ["GET /v1/situation/{id}"],
  },
  {
    id: "orchestrator",
    name: "学习调度中心",
    nameEn: "Orchestrator",
    color: "#f59e0b",
    description: "学习导演：Observe → Recall → Plan → Act 闭环。",
    responsibilities: ["组装 prompt 上下文", "编排技能调用", "输出游戏 Impact"],
    apis: ["POST /v1/orchestrate"],
  },
  {
    id: "skills",
    name: "技能注册表",
    nameEn: "Skill Registry",
    color: "#ec4899",
    description: "诊断、规划、任务映射、报告等可组合能力模块。",
    responsibilities: ["DiagnosisSkill", "PlanSkill", "QuestMappingSkill", "ReportSkill"],
  },
  {
    id: "llm",
    name: "百炼 LLM",
    nameEn: "DashScope",
    color: "#14b8a6",
    description: "阿里云百炼 OpenAI 兼容 API，结构化 JSON 驱动各技能。",
    responsibilities: ["语法诊断推理", "学习路径规划", "剧情 narrative_hook"],
  },
  {
    id: "tools",
    name: "工具注册表",
    nameEn: "Tool Registry",
    color: "#64748b",
    description: "题库、判题、安全过滤等确定性工具。",
    responsibilities: ["QuestionBank", "Evaluator", "SafetyFilter"],
  },
  {
    id: "decision",
    name: "游戏 Impact",
    nameEn: "Learning Decision",
    color: "#ef4444",
    description: "调度结果：地牢出题、NPC 对话、奖励、提示等。",
    responsibilities: ["action_type", "narrative_hook", "content 题目/奖励"],
    apis: ["POST /v1/decisions/{id}/ack"],
  },
];

/** Map trace step names to architecture modules for live highlight */
export function stepToModule(step: string, phase?: string): ModuleId | null {
  const s = step.toLowerCase();
  const p = (phase || "").toLowerCase();
  if (p === "llm" || s.startsWith("llm_")) return "llm";
  if (s === "enrich" || s === "verbatim_write") return s === "enrich" ? "events" : "memory";
  if (s === "observe" || s === "act") return "orchestrator";
  if (s === "recall") return "memory";
  if (s === "diagnose") return "skills";
  if (s === "plan") return "skills";
  if (s === "decision") return "decision";
  return null;
}

export const DEMO_SCENARIOS = [
  {
    id: "wrong_answer",
    label: "答错 · 现在完成时",
    desc: "模拟 onAnswer 错题，观察 enrich → 记忆 → 调度",
    eventType: "onAnswer" as const,
    payload: {
      question_id: "q_pp_001",
      skill_tags: ["grammar.present_perfect"],
      user_answer: "I have went",
      correct_answer: "gone",
      is_correct: false,
      time_spent_ms: 12000,
    },
  },
  {
    id: "mistake",
    label: "连续失误",
    desc: "发送 onMistake，触发 Orchestrator",
    eventType: "onMistake" as const,
    payload: {
      skill_tags: ["grammar.present_perfect"],
      is_correct: false,
    },
  },
  {
    id: "session",
    label: "开始学习",
    desc: "onSessionStart + 强制调度",
    eventType: "onSessionStart" as const,
    payload: {},
    orchestrateAfter: true,
  },
];
