import { useMemo, useState } from "react";
import { usePaperWorkbench } from "../hooks/usePaperWorkbench";
import { filterSessionWorkflowLogs } from "../lib/workflowLog";
import { PaperArchitectureLive } from "./PaperArchitectureLive";
import { PaperModuleInspector } from "./PaperModuleInspector";
import type { TraceItem } from "../hooks/useAgentSocket";
import type { PaperModuleId } from "../data/paperModules";

type Props = {
  learnerId: string;
  workflowFeed: Array<{ category: string; message: string; ts: string }>;
  traces: TraceItem[];
  connected?: boolean;
  apiOnline?: boolean;
  activePaperModule: PaperModuleId | null;
  selectedPaperModule: PaperModuleId | null;
  onSelectPaperModule: (id: PaperModuleId) => void;
  paperWorkflowEvents: Array<{ category: string; message: string; ts: string; raw?: unknown }>;
};

export function AgentWorkbench({
  learnerId,
  workflowFeed,
  traces,
  connected,
  apiOnline,
  activePaperModule,
  selectedPaperModule,
  onSelectPaperModule,
  paperWorkflowEvents,
}: Props) {
  const {
    profile,
    paper,
    preview,
    workflow,
    loading,
    assembling,
    error,
    playIndex,
    canAnswer,
    awaitingNext,
    isLastQuestion,
    lastFeedback,
    refresh,
    startNextPaper,
    canStartNextPaper,
    hasActivePaper,
    nextPaperQueued,
    reserveCount,
    assemblyMode,
    assemblyHint,
    submitAnswer,
    goNext,
    finishPaper,
    submitting,
  } = usePaperWorkbench(learnerId);

  const [selected, setSelected] = useState("");

  const mergedLogs = useMemo(() => {
    const fromApi = filterSessionWorkflowLogs(
      workflow.map((w) => ({
        category: w.category,
        message: w.message,
        ts: w.created_at,
        data: w.data,
      }))
    ).map((w) => ({
      category: w.category,
      message: w.message,
      ts: w.ts,
    }));
    const key = (l: { category: string; message: string }) => `${l.category}|${l.message}`;
    const seen = new Set(fromApi.map(key));
    const extra = workflowFeed
      .filter((l) => !l.message.startsWith("[后台]"))
      .filter((l) => !seen.has(key(l)));
    return [...fromApi, ...extra].slice(-40);
  }, [workflow, workflowFeed]);

  const accuracy =
    profile && profile.total_answers > 0
      ? Math.round((profile.total_correct / profile.total_answers) * 100)
      : 0;

  const activeQ = preview.find((q) => q.index === playIndex);
  const answeredCount = preview.filter((q) => q.answered).length;
  const currentAnswered = Boolean(activeQ?.answered);
  const showNextNav =
    paper?.status === "active" && (awaitingNext || currentAnswered) && Boolean(activeQ);
  const showFinish =
    showNextNav && isLastQuestion && playIndex === (paper.total_questions ?? 1) - 1;

  return (
    <section className="workbench-section">
      <h2 id="workbench">Agent 工作台</h2>
      <p className="section-lead muted">
        顺序答题 · 完成当前卷并交卷后，方可点击「开始下一卷」组卷 · 与 TacticalDuel 共用 Paper API（同一
        learner_id 才同步进度）。
      </p>
      <p className="wb-learner-id muted" title={learnerId}>
        当前 learner_id：<code>{learnerId}</code>
      </p>

      <div className="wb-toolbar">
        <button
          type="button"
          className="btn-primary"
          onClick={() => void startNextPaper()}
          disabled={!canStartNextPaper}
          title={
            hasActivePaper
              ? "请先完成当前试卷并点击「完成试卷」"
              : nextPaperQueued
                ? "激活已预生成的下一卷"
                : "组卷生成下一卷（约 1–3 分钟）"
          }
        >
          {assembling
            ? "组卷中…"
            : !paper
              ? "获取第一份试卷"
              : nextPaperQueued
                ? "开始下一卷（已备好）"
                : "开始下一卷（组卷）"}
        </button>
        <button type="button" className="btn-ghost" onClick={() => void refresh()} disabled={loading}>
          刷新
        </button>
        {reserveCount > 0 && (
          <span className="wb-hint muted">
            Reserve 池 {reserveCount} 题（点「开始下一卷」时优先用于 hybrid 加速，无需等到更晚）
          </span>
        )}
        {hasActivePaper && assemblyHint && (
          <span className="wb-hint wb-hint-ok">
            {assemblyHint}
            {assemblyMode ? ` · ${assemblyMode}` : ""}
          </span>
        )}
        {hasActivePaper && (
          <span className="wb-hint muted">完成全部题目后点击「完成试卷」，即可解锁下一卷</span>
        )}
        {error && <span className="wb-error">{error}</span>}
      </div>

      <div className="workbench-grid">
        <aside className="wb-col wb-profile panel-card">
          <h3>学生画像</h3>
          {!profile ? (
            <p className="muted">暂无画像数据</p>
          ) : (
            <ul className="profile-stats">
              <li>
                <span>等级</span>
                <strong>Lv.{profile.current_level}</strong>
              </li>
              <li>
                <span>偏好难度</span>
                <strong>{profile.difficulty_preference}/5</strong>
              </li>
              <li>
                <span>已完成试卷</span>
                <strong>{profile.papers_completed}</strong>
              </li>
              <li>
                <span>答题正确率</span>
                <strong>{accuracy}%</strong>
              </li>
            </ul>
          )}
          {profile?.last_paper_summary && <p className="wb-summary">{profile.last_paper_summary}</p>}
        </aside>

        <main className="wb-col wb-paper panel-card">
          <h3>当前试卷 · {paper?.knowledge_point || (assembling ? "组卷中…" : "—")}</h3>

          {(assembling || paper) && (
            <PaperArchitectureLive
              activeModule={activePaperModule}
              selected={selectedPaperModule}
              onSelect={onSelectPaperModule}
              connected={connected}
              apiOnline={apiOnline}
              hasPaper={Boolean(paper)}
              assembling={assembling}
              traces={traces}
            />
          )}

          {paper && preview.length > 0 ? (
            <>
              <p className="muted">
                {paper.strategy} · 进度 {Math.min(answeredCount, paper.total_questions)}/{paper.total_questions} ·{" "}
                {paper.status}
              </p>
              <p className="wb-rationale">{paper.rationale}</p>

              <div className="paper-outline paper-outline-readonly" role="list" aria-label="答题进度">
                {preview.map((q) => {
                  const done = Boolean(q.answered);
                  const current = q.index === playIndex && paper.status === "active";
                  const correct = q.is_correct;
                  return (
                    <div
                      key={q.id}
                      role="listitem"
                      className={`paper-outline-item ${done ? (correct ? "done ok" : "done bad") : ""} ${current ? "active" : ""} ${q.index > playIndex && !done ? "locked" : ""}`}
                    >
                      <span className="paper-outline-num">#{q.index + 1}</span>
                      {q.origin === "mistake_review" && <span className="badge-mistake">往期错题</span>}
                      {q.origin === "carry_over" && <span className="badge-carry">未答结转</span>}
                      <span className={`src src-${q.source}`}>{q.source === "database" ? "真题" : "AI"}</span>
                      <span className="paper-outline-prompt">{q.prompt}</span>
                    </div>
                  );
                })}
              </div>

              {activeQ && (
                <div className="wb-quiz">
                  <div className="wb-quiz-header">
                    {activeQ.origin === "mistake_review" && <span className="badge-mistake">往期错题</span>}
                    {activeQ.origin === "carry_over" && <span className="badge-carry">未答结转</span>}
                    <span className={`src src-${activeQ.source}`}>
                      第 {playIndex + 1} 题 · {activeQ.source === "database" ? "真题" : "AI 变式"} · 难度 {activeQ.level}
                    </span>
                  </div>
                  <p className="quiz-prompt">{activeQ.prompt}</p>

                  {activeQ.answered && activeQ.user_answer !== undefined ? (
                    <>
                      <div className={`wb-feedback ${activeQ.is_correct ? "ok" : "bad"}`}>
                        <p>{activeQ.is_correct ? "回答正确" : "回答错误"}</p>
                        {!activeQ.is_correct && (lastFeedback?.correct_answer || activeQ.user_answer) && (
                          <p>正确答案：{lastFeedback?.correct_answer || "见解析"}</p>
                        )}
                        {(activeQ.explanation || lastFeedback?.explanation) && (
                          <p className="wb-explanation">{activeQ.explanation || lastFeedback?.explanation}</p>
                        )}
                      </div>
                      {showNextNav && (
                        <div className="wb-next-row">
                          {showFinish ? (
                            <button type="button" className="btn-primary" onClick={() => void finishPaper()}>
                              完成试卷
                            </button>
                          ) : (
                            <button type="button" className="btn-primary" onClick={goNext}>
                              下一题
                            </button>
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      <div className="quiz-choices">
                        {activeQ.choices.map((c) => (
                          <button
                            key={c}
                            type="button"
                            className={selected === c ? "selected" : ""}
                            disabled={!canAnswer || submitting}
                            onClick={() => setSelected(c)}
                          >
                            {c}
                          </button>
                        ))}
                      </div>
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={!selected || !canAnswer || submitting || (assembling && !paper)}
                        onClick={() => {
                          if (submitting) return;
                          void (async () => {
                            await submitAnswer(selected);
                            setSelected("");
                          })();
                        }}
                      >
                        {submitting ? "判题中…" : "提交答案"}
                      </button>
                      {lastFeedback && lastFeedback.index === playIndex && (
                        <div className={`wb-feedback ${lastFeedback.is_correct ? "ok" : "bad"}`}>
                          <p>{lastFeedback.is_correct ? "回答正确" : "回答错误"}</p>
                          {!lastFeedback.is_correct && <p>正确答案：{lastFeedback.correct_answer}</p>}
                          {lastFeedback.explanation && (
                            <p className="wb-explanation">{lastFeedback.explanation}</p>
                          )}
                        </div>
                      )}
                      {showNextNav && (
                        <div className="wb-next-row">
                          {showFinish ? (
                            <button type="button" className="btn-primary" onClick={() => void finishPaper()}>
                              完成试卷
                            </button>
                          ) : (
                            <button type="button" className="btn-primary" onClick={goNext}>
                              下一题
                            </button>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </>
          ) : assembling ? (
            <p className="muted wb-assembling-hint">
              组卷进行中，工作流日志与拓扑仅显示本次会话。完整 AI 组卷约 2–8 分钟；首卷冷启动通常更快。
            </p>
          ) : paper ? (
            <p className="muted">试卷已创建，正在加载题目…请点「刷新」</p>
          ) : (
            <p className="muted">点击「获取第一份试卷」开始组卷</p>
          )}
        </main>

        <aside className="wb-col wb-workflow panel-card">
          <h3>模块输出</h3>
          <PaperModuleInspector
            moduleId={selectedPaperModule}
            traces={traces}
            workflowEvents={[
              ...workflow.map((w) => ({
                category: w.category,
                message: w.message,
                ts: w.created_at,
                data: w.data,
              })),
              ...paperWorkflowEvents,
            ]}
          />
          <h3 className="wb-wf-title">工作流日志</h3>
          <ul className="workflow-feed">
            {mergedLogs.length === 0 ? (
              <li className="muted">等待出题 / 记忆 / 调整日志…</li>
            ) : (
              mergedLogs.map((log, i) => (
                <li key={`${log.ts}-${i}`} className={`wf-${log.category}`}>
                  <span className="wf-cat">[{log.category}]</span>
                  <span>{log.message}</span>
                  <time>{log.ts}</time>
                </li>
              ))
            )}
          </ul>
        </aside>
      </div>
    </section>
  );
}
