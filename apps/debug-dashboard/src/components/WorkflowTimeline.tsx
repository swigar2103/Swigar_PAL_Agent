import { useMemo, useState } from "react";
import type { TraceItem } from "../hooks/useAgentSocket";
import { presentTrace, summarizePipeline, type PresentedStep } from "../utils/tracePresenters";
import { QuestionCard } from "./QuestionCard";

type Props = {
  traces: TraceItem[];
  llmConfigured?: boolean;
};

function EngineBadge({ engine }: { engine: PresentedStep["engine"] }) {
  if (engine === "llm") return <span className="engine-badge engine-llm">百炼 LLM</span>;
  if (engine === "rules") return <span className="engine-badge engine-rules">规则引擎</span>;
  return <span className="engine-badge engine-sys">系统</span>;
}

function StepCard({ step }: { step: PresentedStep }) {
  const [showJson, setShowJson] = useState(false);

  return (
    <li className="wf-step">
      <div className="wf-step-rail">
        <span className="wf-dot" />
      </div>
      <div className="wf-step-body">
        <header className="wf-step-header">
          <div>
            <h4>{step.title}</h4>
            <p className="wf-subtitle">{step.subtitle}</p>
          </div>
          <div className="wf-badges">
            <EngineBadge engine={step.engine} />
            {step.durationMs != null && (
              <span className="wf-dur">{step.durationMs.toFixed(0)} ms</span>
            )}
            <span className="wf-ts">{step.ts}</span>
          </div>
        </header>

        <div className="wf-io-grid">
          <div className="wf-io-box wf-input">
            <span className="wf-io-label">输入</span>
            <ul>
              {step.inputLines.length > 0 ? (
                step.inputLines.map((line, i) => <li key={i}>{line}</li>)
              ) : (
                <li className="muted">—</li>
              )}
            </ul>
          </div>
          <div className="wf-io-box wf-output">
            <span className="wf-io-label">输出</span>
            <ul>
              {step.outputLines.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          </div>
        </div>

        {step.narrativeHook ? <blockquote className="wf-narrative">{step.narrativeHook}</blockquote> : null}

        {step.questions.length > 0 ? (
          <div className="wf-questions">
            <h5>生成的练习 / 试卷内容</h5>
            {step.questions.map((q, i) => (
              <QuestionCard key={q.id || String(i)} q={q} index={i} />
            ))}
          </div>
        ) : null}

        {step.showJson ? (
          <button type="button" className="wf-json-toggle" onClick={() => setShowJson(!showJson)}>
            {showJson ? "隐藏原始 JSON" : "查看原始 JSON"}
          </button>
        ) : null}
        {showJson ? <pre className="wf-json">{JSON.stringify(step.raw, null, 2)}</pre> : null}
      </div>
    </li>
  );
}

export function WorkflowTimeline({ traces, llmConfigured }: Props) {
  const summary = useMemo(() => summarizePipeline(traces, llmConfigured), [traces, llmConfigured]);

  if (traces.length === 0) {
    return (
      <div className="wf-empty">
        <p>运行左侧演示场景后，这里将以可读卡片展示完整闭环。</p>
        <ol>
          <li>理解答题行为，写入记忆</li>
          <li>召回历史，LLM 诊断与规划</li>
          <li>匹配题库题目，LLM 生成剧情，推送给游戏</li>
        </ol>
        <p className="muted">每步标注「百炼 LLM」或「规则引擎」，便于确认是否调用了模型。</p>
      </div>
    );
  }

  const engineChain = [summary.diagnoseEngine, summary.planEngine, summary.actEngine]
    .map((e) => (e === "llm" ? "LLM" : e === "rules" ? "规则" : "—"))
    .join(" → ");

  return (
    <div className="workflow-timeline">
      <div className="wf-summary">
        <div className="wf-summary-item">
          <span className="wf-summary-label">百炼 API</span>
          <strong className={summary.llmConfigured ? "ok" : "warn"}>
            {summary.llmConfigured ? "已配置" : "未配置"}
          </strong>
        </div>
        <div className="wf-summary-item">
          <span className="wf-summary-label">LLM 调用次数</span>
          <strong>{summary.llmCallCount}</strong>
        </div>
        <div className="wf-summary-item">
          <span className="wf-summary-label">诊断 → 规划 → 映射</span>
          <strong>{engineChain}</strong>
        </div>
        <div className="wf-summary-item">
          <span className="wf-summary-label">题库题目</span>
          <strong>{summary.questionCount} 道</strong>
        </div>
      </div>

      {!summary.llmConfigured ? (
        <p className="wf-warn-banner">
          未配置 DASHSCOPE_API_KEY 时，诊断/规划/剧情使用规则引擎，不会出现 LLM 步骤。
        </p>
      ) : null}

      {summary.llmConfigured && summary.llmCallCount === 0 ? (
        <p className="wf-info-banner">已配置 LLM 但本次未观察到 LLM 请求，可能 API 失败或已回退规则。</p>
      ) : null}

      <ul className="wf-steps">
        {summary.presented.map((step) => (
          <StepCard key={step.id} step={step} />
        ))}
      </ul>
    </div>
  );
}
