import type { CSSProperties } from "react";
import { getPaperModule, paperStepToModule, type PaperModuleId } from "../data/paperModules";
import type { TraceItem } from "../hooks/useAgentSocket";

type WorkflowItem = {
  category: string;
  message: string;
  ts: string;
  raw?: unknown;
  data?: Record<string, unknown>;
};

type Props = {
  moduleId: PaperModuleId | null;
  traces: TraceItem[];
  workflowEvents: WorkflowItem[];
};

function extractLlmPayload(raw: unknown): { request?: unknown; response?: unknown } {
  if (!raw || typeof raw !== "object") return {};
  const o = raw as Record<string, unknown>;
  const step = (o.step as Record<string, unknown>) || o;
  const stepName = String(step.step || "");
  if (stepName === "llm_request") {
    return { request: step.messages ?? step };
  }
  if (stepName === "llm_response") {
    return { response: step.content ?? step.text ?? step };
  }
  return { request: step.messages, response: step.content };
}

export function PaperModuleInspector({ moduleId, traces, workflowEvents }: Props) {
  const mod = moduleId ? getPaperModule(moduleId) : null;

  const moduleTraces = traces.filter((t) => {
    if (t.paperModuleId === moduleId) return true;
    const data = (t.raw as Record<string, unknown>) || {};
    const step = (data.step as Record<string, unknown>) || data;
    return (
      paperStepToModule(String(step.step || t.step), String(step.phase || t.phase), undefined, {
        module: String(step.module || ""),
        ...step,
      }) === moduleId
    );
  });

  const moduleWf = workflowEvents.filter((e) => {
    const data = (e.data as Record<string, unknown>) || (e.raw as Record<string, unknown>)?.data as Record<string, unknown> || {};
    return paperStepToModule(undefined, undefined, e.category, data, e.message) === moduleId;
  });

  if (!mod) {
    return (
      <div className="paper-inspector paper-inspector-empty">
        <p className="muted">点击架构图中的模块，查看实时输出与 LLM 调用</p>
      </div>
    );
  }

  return (
    <div className="paper-inspector" style={{ borderColor: mod.color } as CSSProperties}>
      <div className="paper-inspector-head" style={{ background: `${mod.color}18` }}>
        <span className="paper-inspector-dot" style={{ background: mod.color }} />
        <div>
          <h3>{mod.name}</h3>
          <span className="muted">{mod.nameEn}</span>
        </div>
      </div>
      <p className="paper-inspector-desc">{mod.description}</p>

      <h4>Trace / LLM</h4>
      {moduleTraces.length === 0 && moduleWf.length === 0 ? (
        <p className="muted">
          {mod.id === "orchestrator" || mod.id === "event_bus"
            ? "系统在线；组卷或答题时此处将显示实时 trace。"
            : "组卷或答题后，与此模块相关的 LLM / 工作流会出现在此处。"}
        </p>
      ) : (
        <ul className="paper-inspector-list">
          {moduleTraces
            .slice()
            .reverse()
            .slice(0, 8)
            .map((t) => {
              const { request, response } = extractLlmPayload(t.raw);
              return (
                <li key={t.id} className="paper-inspector-item">
                  <header>
                    <code>{t.step}</code>
                    <time>{t.ts}</time>
                  </header>
                  {request !== undefined && (
                    <details open>
                      <summary>LLM 输入 (prompt / messages)</summary>
                      <pre>{JSON.stringify(request, null, 2)}</pre>
                    </details>
                  )}
                  {response !== undefined && (
                    <details>
                      <summary>LLM 输出</summary>
                      <pre>{JSON.stringify(response, null, 2)}</pre>
                    </details>
                  )}
                  {request === undefined && response === undefined && (
                    <pre className="paper-inspector-raw">{JSON.stringify(t.raw, null, 2)}</pre>
                  )}
                </li>
              );
            })}
          {moduleWf
            .slice()
            .reverse()
            .slice(0, 6)
            .map((w, i) => (
              <li key={`wf-${i}-${w.ts}`} className="paper-inspector-item paper-inspector-wf">
                <header>
                  <span>[{w.category}]</span>
                  <time>{w.ts}</time>
                </header>
                <p>{w.message}</p>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
