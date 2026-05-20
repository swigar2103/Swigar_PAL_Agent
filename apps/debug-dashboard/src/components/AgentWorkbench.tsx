import { useMemo, useState } from "react";
import { usePaperWorkbench } from "../hooks/usePaperWorkbench";
import { filterSessionWorkflowLogs } from "../lib/workflowLog";
import { PaperArchitectureLive } from "./PaperArchitectureLive";
import { PaperModuleInspector } from "./PaperModuleInspector";
import type { TraceItem } from "../hooks/useAgentSocket";
import type { PaperModuleId } from "../data/paperModules";
import { useLanguage } from "../i18n/LanguageContext";

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

  const { t } = useLanguage();
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
      <h2 id="workbench">{t("workbench.title")}</h2>
      <p className="section-lead muted">{t("workbench.lead")}</p>
      <p className="wb-learner-id muted" title={learnerId}>
        {t("workbench.learnerId")} <code>{learnerId}</code>
      </p>

      <div className="wb-toolbar">
        <button
          type="button"
          className="btn-primary"
          onClick={() => void startNextPaper()}
          disabled={!canStartNextPaper}
          title={
            hasActivePaper
              ? t("workbench.titleFinishFirst")
              : nextPaperQueued
                ? t("workbench.titleActivateQueued")
                : t("workbench.titleAssembleNext")
          }
        >
          {assembling
            ? t("workbench.assembling")
            : !paper
              ? t("workbench.firstPaper")
              : nextPaperQueued
                ? t("workbench.nextReady")
                : t("workbench.nextAssemble")}
        </button>
        <button type="button" className="btn-ghost" onClick={() => void refresh()} disabled={loading}>
          {t("workbench.refresh")}
        </button>
        {reserveCount > 0 && (
          <span className="wb-hint muted">{t("workbench.reserveHint", { count: reserveCount })}</span>
        )}
        {hasActivePaper && assemblyHint && (
          <span className="wb-hint wb-hint-ok">
            {assemblyHint}
            {assemblyMode ? ` · ${assemblyMode}` : ""}
          </span>
        )}
        {hasActivePaper && <span className="wb-hint muted">{t("workbench.unlockHint")}</span>}
        {error && <span className="wb-error">{error}</span>}
      </div>

      <div className="workbench-grid">
        <aside className="wb-col wb-profile panel-card">
          <h3>{t("workbench.profile")}</h3>
          {!profile ? (
            <p className="muted">{t("workbench.noProfile")}</p>
          ) : (
            <ul className="profile-stats">
              <li>
                <span>{t("workbench.level")}</span>
                <strong>Lv.{profile.current_level}</strong>
              </li>
              <li>
                <span>{t("workbench.difficultyPref")}</span>
                <strong>{profile.difficulty_preference}/5</strong>
              </li>
              <li>
                <span>{t("workbench.papersDone")}</span>
                <strong>{profile.papers_completed}</strong>
              </li>
              <li>
                <span>{t("workbench.accuracy")}</span>
                <strong>{accuracy}%</strong>
              </li>
            </ul>
          )}
          {profile?.last_paper_summary && <p className="wb-summary">{profile.last_paper_summary}</p>}
        </aside>

        <main className="wb-col wb-paper panel-card">
          <h3>
            {t("workbench.currentPaper")} · {paper?.knowledge_point || (assembling ? t("workbench.assembling") : "—")}
          </h3>

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
                {paper.strategy} · {t("workbench.progress")}{" "}
                {Math.min(answeredCount, paper.total_questions)}/{paper.total_questions} ·{" "}
                {paper.status}
              </p>
              <p className="wb-rationale">{paper.rationale}</p>

              <div className="paper-outline paper-outline-readonly" role="list" aria-label={t("workbench.outlineAria")}>
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
                      {q.origin === "mistake_review" && <span className="badge-mistake">{t("workbench.badge.mistake")}</span>}
                      {q.origin === "carry_over" && <span className="badge-carry">{t("workbench.badge.carry")}</span>}
                      <span className={`src src-${q.source}`}>{q.source === "database" ? t("workbench.source.db") : t("workbench.source.ai")}</span>
                      <span className="paper-outline-prompt">{q.prompt}</span>
                    </div>
                  );
                })}
              </div>

              {activeQ && (
                <div className="wb-quiz">
                  <div className="wb-quiz-header">
                    {activeQ.origin === "mistake_review" && <span className="badge-mistake">{t("workbench.badge.mistake")}</span>}
                    {activeQ.origin === "carry_over" && <span className="badge-carry">{t("workbench.badge.carry")}</span>}
                    <span className={`src src-${activeQ.source}`}>
                      {t("workbench.questionN", { n: playIndex + 1 })} ·{" "}
                      {activeQ.source === "database" ? t("workbench.source.db") : t("workbench.source.aiVariant")} ·{" "}
                      {t("workbench.difficultyLevel")} {activeQ.level}
                    </span>
                  </div>
                  <p className="quiz-prompt">{activeQ.prompt}</p>

                  {activeQ.answered && activeQ.user_answer !== undefined ? (
                    <>
                      <div className={`wb-feedback ${activeQ.is_correct ? "ok" : "bad"}`}>
                        <p>{activeQ.is_correct ? t("workbench.correct") : t("workbench.incorrect")}</p>
                        {!activeQ.is_correct && (lastFeedback?.correct_answer || activeQ.user_answer) && (
                          <p>
                            {t("workbench.correctAnswer")}
                            {lastFeedback?.correct_answer || t("workbench.seeExplanation")}
                          </p>
                        )}
                        {(activeQ.explanation || lastFeedback?.explanation) && (
                          <p className="wb-explanation">{activeQ.explanation || lastFeedback?.explanation}</p>
                        )}
                      </div>
                      {showNextNav && (
                        <div className="wb-next-row">
                          {showFinish ? (
                            <button type="button" className="btn-primary" onClick={() => void finishPaper()}>
                              {t("workbench.finishPaper")}
                            </button>
                          ) : (
                            <button type="button" className="btn-primary" onClick={goNext}>
                              {t("workbench.nextQuestion")}
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
                        {submitting ? t("workbench.submitting") : t("workbench.submit")}
                      </button>
                      {lastFeedback && lastFeedback.index === playIndex && (
                        <div className={`wb-feedback ${lastFeedback.is_correct ? "ok" : "bad"}`}>
                          <p>{lastFeedback.is_correct ? t("workbench.correct") : t("workbench.incorrect")}</p>
                          {!lastFeedback.is_correct && (
                            <p>
                              {t("workbench.correctAnswer")}
                              {lastFeedback.correct_answer}
                            </p>
                          )}
                          {lastFeedback.explanation && (
                            <p className="wb-explanation">{lastFeedback.explanation}</p>
                          )}
                        </div>
                      )}
                      {showNextNav && (
                        <div className="wb-next-row">
                          {showFinish ? (
                            <button type="button" className="btn-primary" onClick={() => void finishPaper()}>
                              {t("workbench.finishPaper")}
                            </button>
                          ) : (
                            <button type="button" className="btn-primary" onClick={goNext}>
                              {t("workbench.nextQuestion")}
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
            <p className="muted wb-assembling-hint">{t("workbench.assemblingHint")}</p>
          ) : paper ? (
            <p className="muted">{t("workbench.loadingQuestions")}</p>
          ) : (
            <p className="muted">{t("workbench.startHint")}</p>
          )}
        </main>

        <aside className="wb-col wb-workflow panel-card">
          <h3>{t("workbench.moduleOutput")}</h3>
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
          <h3 className="wb-wf-title">{t("workbench.workflowLog")}</h3>
          <ul className="workflow-feed">
            {mergedLogs.length === 0 ? (
              <li className="muted">{t("workbench.waitingLogs")}</li>
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
