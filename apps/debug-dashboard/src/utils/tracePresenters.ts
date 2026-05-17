import type { TraceItem } from "../hooks/useAgentSocket";
import { extractQuestions } from "../components/QuestionCard";

export type Question = {
  id?: string;
  prompt?: string;
  type?: string;
  choices?: string[];
  correct_answer?: string;
  skill_tags?: string[];
  difficulty?: number;
};

export type EngineBadge = "llm" | "rules" | "system" | "none";

export type PresentedStep = {
  id: string;
  stepKey: string;
  title: string;
  subtitle: string;
  moduleName: string;
  engine: EngineBadge;
  inputLines: string[];
  outputLines: string[];
  questions: Question[];
  narrativeHook?: string;
  actionType?: string;
  showJson: boolean;
  raw: unknown;
  ts: string;
  durationMs?: number;
};

const SKILL_LABELS: Record<string, string> = {
  diagnosis: "诊断技能 · Diagnosis",
  plan: "规划技能 · Plan",
  quest_mapping: "任务映射 · Quest Mapping",
};

const INTENT_LABELS: Record<string, string> = {
  review: "复习巩固",
  new_knowledge: "学习新知",
  practice: "针对性练习",
  reward: "游戏奖励",
  hint: "提示引导",
};

const ACTION_LABELS: Record<string, string> = {
  dungeon_quiz: "地牢测验",
  npc_dialogue: "NPC 对话",
  assign_task: "分配任务",
  feedback_reward: "反馈奖励",
  hint: "提示",
  difficulty_adjust: "难度调整",
};

function getIO(raw: unknown): { input: Record<string, unknown>; output: Record<string, unknown> } {
  const r = raw as { input_data?: Record<string, unknown>; output_data?: Record<string, unknown> };
  return { input: r?.input_data || {}, output: r?.output_data || {} };
}

function engineFromOutput(out: Record<string, unknown>, step: string, phase: string): EngineBadge {
  if (step.startsWith("llm_") || phase === "llm") return "llm";
  if (out.engine === "llm") return "llm";
  if (out.engine === "rules") return "rules";
  return "system";
}

export function presentTrace(t: TraceItem): PresentedStep {
  const { input, output } = getIO(t.raw);
  const base = {
    id: t.id,
    stepKey: t.step,
    ts: t.ts,
    durationMs: t.durationMs,
    raw: t.raw,
    showJson: true,
    moduleName: t.moduleId || t.phase,
    engine: engineFromOutput(output, t.step, t.phase),
    inputLines: [] as string[],
    outputLines: [] as string[],
    questions: [] as Question[],
    title: t.step,
    subtitle: "",
  };

  switch (t.step) {
    case "enrich": {
      const signals = (output.signals as unknown[]) || [];
      return {
        ...base,
        title: "① 理解学习行为",
        subtitle: "学习事件层 · 把原始答题变成「学习信号」",
        moduleName: "events",
        engine: "rules",
        inputLines: [
          `事件类型：${input.event_type || "—"}`,
          `摘要：${input.payload_summary || "—"}`,
        ],
        outputLines: signals.map((s) => {
          const sig = s as { signal_type?: string; skill_tag?: string; confidence?: number };
          return `→ ${sig.signal_type}：${sig.skill_tag}（置信 ${((sig.confidence || 0) * 100).toFixed(0)}%）`;
        }),
      };
    }
    case "verbatim_write":
      return {
        ...base,
        title: "② 写入长期记忆",
        subtitle: "记忆宫殿 · 原文 Drawer 存档",
        moduleName: "memory",
        inputLines: ["将本次学习事件逐字写入学习者专属 palace"],
        outputLines: [`Drawer ID：${output.drawer_id || "—"}`],
      };
    case "observe":
      return {
        ...base,
        title: "③ 观察当前情境",
        subtitle: "调度中心 · 合并游戏上下文",
        moduleName: "orchestrator",
        inputLines: [`关联事件：${output.event_id || "手动调度"}`],
        outputLines: ["更新学习者情境快照（地图 / NPC / 最近事件）"],
      };
    case "recall":
      return {
        ...base,
        title: "④ 召回相关记忆",
        subtitle: "记忆宫殿 · 检索历史薄弱点",
        moduleName: "memory",
        inputLines: [`检索 query：${input.query || "—"}`],
        outputLines: [
          `命中记忆片段：${output.snippet_count ?? 0} 条`,
          `唤醒上下文长度：${output.wake_len ?? 0} 字符`,
        ],
      };
    case "diagnose":
      return {
        ...base,
        title: "⑤ 诊断薄弱点",
        subtitle: "诊断技能 · 判断根因与置信度",
        moduleName: "skills",
        engine: (output.engine as EngineBadge) || "rules",
        inputLines: ["输入：学习信号 + 记忆检索 + 知识图谱"],
        outputLines: [
          `主要薄弱点：${output.root_cause || "—"}`,
          `置信度：${((Number(output.confidence) || 0) * 100).toFixed(0)}%`,
          ...((output.weaknesses as { skill_tag?: string; score?: number }[]) || []).map(
            (w, i) => `  ${i + 1}. ${w.skill_tag}（${w.score}）`
          ),
        ],
      };
    case "plan":
      return {
        ...base,
        title: "⑥ 制定学习意图",
        subtitle: "规划技能 · 决定下一步学什么",
        moduleName: "skills",
        engine: (output.engine as EngineBadge) || "rules",
        inputLines: ["输入：诊断结果 + 家长/老师目标"],
        outputLines: [
          `意图：${INTENT_LABELS[String(output.intent)] || output.intent}`,
          `知识点：${(output.skill_tags as string[])?.join(", ") || "—"}`,
          `难度：${output.difficulty || "same"}`,
          `说明：${output.rationale || "—"}`,
        ],
      };
    case "act":
    case "decision": {
      const out = t.step === "decision" ? (t.raw as Record<string, unknown>) : output;
      const questions = extractQuestions(out);
      return {
        ...base,
        title: "⑦ 生成游戏 Impact",
        subtitle: "任务映射 · 题目 + 剧情钩子 → 游戏",
        moduleName: "decision",
        engine: (out.engine as EngineBadge) || base.engine,
        actionType: String(out.action_type || ""),
        narrativeHook: String(out.narrative_hook || ""),
        questions,
        inputLines: [`游戏动作：${ACTION_LABELS[String(out.action_type)] || out.action_type}`],
        outputLines: [
          out.rationale ? `教学理由：${out.rationale}` : "",
          questions.length ? `已从题库匹配 ${questions.length} 道练习题` : "（无题目，可能为纯对话/奖励）",
        ].filter(Boolean),
      };
    }
    case "llm_request": {
      const skill = String(output.skill || input.skill || "");
      const model = String(output.model || "qwen-plus");
      return {
        ...base,
        title: "☁ 调用百炼 LLM",
        subtitle: SKILL_LABELS[skill] || "大模型推理",
        moduleName: "llm",
        engine: "llm",
        inputLines: [`模型：${model}`, `技能：${SKILL_LABELS[skill] || skill || "—"}`],
        outputLines: ["向 DashScope 兼容 API 发送结构化 JSON 请求…"],
        showJson: true,
      };
    }
    case "llm_response": {
      const skill = String(output.skill || "");
      let parsed: Record<string, unknown> | null = null;
      const rawText = output.raw as string | undefined;
      if (rawText) {
        try {
          parsed = JSON.parse(rawText);
        } catch {
          /* ignore */
        }
      }
      const lines: string[] = [`${SKILL_LABELS[skill] || skill} 返回成功`];
      if (parsed?.root_cause) lines.push(`诊断：${parsed.root_cause}`);
      if (parsed?.intent) lines.push(`规划：${INTENT_LABELS[String(parsed.intent)] || parsed.intent}`);
      if (parsed?.narrative_hook) lines.push(`剧情：${String(parsed.narrative_hook).slice(0, 80)}…`);
      return {
        ...base,
        title: "☁ LLM 返回结果",
        subtitle: SKILL_LABELS[skill] || "模型输出",
        moduleName: "llm",
        engine: "llm",
        inputLines: [],
        outputLines: lines,
        questions: extractQuestions(parsed || {}),
        narrativeHook: parsed?.narrative_hook as string | undefined,
      };
    }
    default:
      return {
        ...base,
        title: t.step,
        subtitle: `${t.phase} 模块`,
        inputLines: Object.keys(input).length ? [JSON.stringify(input)] : [],
        outputLines: Object.keys(output).length ? [JSON.stringify(output)] : [],
      };
  }
}

export function summarizePipeline(traces: TraceItem[], llmConfigured?: boolean) {
  const presented = traces.map(presentTrace);
  const llmCalls = presented.filter((p) => p.engine === "llm" || p.stepKey.startsWith("llm_")).length;
  const llmSteps = presented.filter((p) => p.outputLines.some((_, i) => false) || p.engine === "llm");
  const ruleSteps = presented.filter((p) => p.engine === "rules");
  const diagnose = presented.find((p) => p.stepKey === "diagnose");
  const plan = presented.find((p) => p.stepKey === "plan");
  const act = presented.find((p) => p.stepKey === "act" || p.stepKey === "decision");
  const allQuestions = presented.flatMap((p) => p.questions);

  return {
    llmConfigured: !!llmConfigured,
    llmCallCount: llmCalls,
    diagnoseEngine: diagnose?.engine,
    planEngine: plan?.engine,
    actEngine: act?.engine,
    usedLlm: ruleSteps.length < 3 && llmCalls > 0,
    questionCount: allQuestions.length,
    presented,
  };
}
