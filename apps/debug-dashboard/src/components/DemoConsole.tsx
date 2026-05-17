import { DEMO_SCENARIOS } from "../data/modules";

type Props = {
  learnerId: string;
  sessionId: string;
  onLearnerId: (v: string) => void;
  onSessionId: (v: string) => void;
  running: boolean;
  onRunScenario: (scenarioId: string) => void;
  onOrchestrate: () => void;
  onClear: () => void;
};

export function DemoConsole({
  learnerId,
  sessionId,
  onLearnerId,
  onSessionId,
  running,
  onRunScenario,
  onOrchestrate,
  onClear,
}: Props) {
  return (
    <div className="demo-console">
      <div className="demo-console-head">
        <h2>实时演示控制台</h2>
        <p>选择预设场景，观察各模块如何协作完成一次学习闭环</p>
      </div>

      <div className="demo-fields">
        <label>
          <span>学习者 ID</span>
          <input value={learnerId} onChange={(e) => onLearnerId(e.target.value)} />
        </label>
        <label>
          <span>会话 ID</span>
          <input value={sessionId} onChange={(e) => onSessionId(e.target.value)} />
        </label>
      </div>

      <div className="scenario-grid">
        {DEMO_SCENARIOS.map((s) => (
          <button
            key={s.id}
            type="button"
            className="scenario-card"
            disabled={running}
            onClick={() => onRunScenario(s.id)}
          >
            <strong>{s.label}</strong>
            <span>{s.desc}</span>
          </button>
        ))}
        <button type="button" className="scenario-card scenario-card-alt" disabled={running} onClick={onOrchestrate}>
          <strong>仅触发调度</strong>
          <span>跳过事件，直接 Observe → Plan → Act</span>
        </button>
      </div>

      <div className="demo-actions">
        <button type="button" className="btn-ghost" onClick={onClear} disabled={running}>
          清空日志
        </button>
        {running && <span className="demo-running">Agent 运行中…</span>}
      </div>
    </div>
  );
}
