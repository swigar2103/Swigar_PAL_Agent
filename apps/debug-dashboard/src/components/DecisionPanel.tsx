type Props = {
  decision: Record<string, unknown> | null;
};

export function DecisionPanel({ decision }: Props) {
  if (!decision) {
    return (
      <div className="decision-panel decision-panel-empty">
        <div className="decision-placeholder">
          <span className="decision-icon">🏆</span>
          <p>LearningDecision 将在此展示</p>
          <p className="muted">包含 action_type、narrative_hook、题目与奖励内容</p>
        </div>
      </div>
    );
  }

  const hook = String(decision.narrative_hook || "");
  const action = String(decision.action_type || "");
  const rationale = String(decision.rationale || "");
  const content = decision.content as Record<string, unknown> | undefined;

  return (
    <div className="decision-panel">
      <div className="decision-badge">{action}</div>
      <blockquote className="decision-hook">{hook}</blockquote>
      <p className="decision-rationale">
        <strong>教学理由：</strong>
        {rationale}
      </p>
      {content?.questions && Array.isArray(content.questions) ? (
        <div className="decision-questions">
          <h4>关联题目（题库工具）</h4>
          {(content.questions as Record<string, unknown>[]).map((q, i) => (
            <div key={i} className="question-chip">
              <span>{String(q.prompt || q.id)}</span>
            </div>
          ))}
        </div>
      ) : null}
      <details className="decision-raw">
        <summary>完整 JSON</summary>
        <pre>{JSON.stringify(decision, null, 2)}</pre>
      </details>
    </div>
  );
}
