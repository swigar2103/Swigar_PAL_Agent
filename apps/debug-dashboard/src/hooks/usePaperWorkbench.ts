import { useCallback, useEffect, useRef, useState } from "react";
import { filterSessionWorkflowLogs } from "../lib/workflowLog";

const API = import.meta.env.VITE_API_URL || "";
const ASSEMBLY_FETCH_MS = 900_000;

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error("组卷请求超时（>15 分钟）。后端可能仍在运行，请稍后点「刷新」查看是否已生成试卷。");
    }
    if (e instanceof TypeError) {
      throw new Error(
        "网络中断（failed to fetch）。完整组卷在 LLM 较慢时可能超过 10 分钟；请确认 API 窗口无报错，或稍后刷新。"
      );
    }
    throw e;
  } finally {
    window.clearTimeout(timer);
  }
}

export type PaperMeta = {
  paper_id: string;
  knowledge_point: string;
  status: string;
  strategy: string;
  rationale: string;
  current_index: number;
  total_questions: number;
  questions_meta: Array<{
    index: number;
    id: string;
    source: string;
    origin?: string;
    level: number;
    validation_status?: string;
  }>;
};

export type PaperQuestionPreview = {
  index: number;
  id: string;
  source: string;
  origin?: string;
  level: number;
  prompt: string;
  choices: string[];
  validation_status?: string;
  answered?: boolean;
  is_correct?: boolean;
  user_answer?: string;
  explanation?: string;
};

export type LearnerProfileData = {
  learner_id: string;
  current_level: number;
  weak_points: string[];
  avg_response_ms: number;
  accuracy_by_kp: Record<string, number>;
  difficulty_preference: number;
  papers_completed: number;
  last_paper_summary: string;
  total_answers: number;
  total_correct: number;
};

export function usePaperWorkbench(learnerId: string) {
  const [profile, setProfile] = useState<LearnerProfileData | null>(null);
  const [paper, setPaper] = useState<PaperMeta | null>(null);
  const [preview, setPreview] = useState<PaperQuestionPreview[]>([]);
  const [workflow, setWorkflow] = useState<Array<{ category: string; message: string; created_at: string; data?: Record<string, unknown> }>>([]);
  const [loading, setLoading] = useState(false);
  const [assembling, setAssembling] = useState(false);
  const [nextPaperQueued, setNextPaperQueued] = useState(false);
  const [reserveCount, setReserveCount] = useState(0);
  const [assemblyMode, setAssemblyMode] = useState<string | null>(null);
  const [assemblyHint, setAssemblyHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playIndex, setPlayIndex] = useState(0);
  const playIndexRef = useRef(0);
  const [submitting, setSubmitting] = useState(false);
  const [awaitingNext, setAwaitingNext] = useState(false);
  const awaitingNextRef = useRef(false);

  useEffect(() => {
    playIndexRef.current = playIndex;
  }, [playIndex]);
  const startInFlight = useRef(false);
  const submitInFlight = useRef(false);
  const sessionSinceRef = useRef(new Date().toISOString());

  const workflowUrl = useCallback(() => {
    const since = encodeURIComponent(sessionSinceRef.current);
    return `${API}/v1/learners/${encodeURIComponent(learnerId)}/workflow?since=${since}`;
  }, [learnerId]);

  const beginLogSession = useCallback(() => {
    sessionSinceRef.current = new Date().toISOString();
    setWorkflow([]);
  }, []);

  useEffect(() => {
    beginLogSession();
    setPaper(null);
    setPreview([]);
    setError(null);
    setPlayIndex(0);
    setLastFeedback(null);
    setAwaitingNext(false);
    awaitingNextRef.current = false;
  }, [learnerId, beginLogSession]);
  const [lastFeedback, setLastFeedback] = useState<{
    index: number;
    is_correct: boolean;
    correct_answer: string;
    explanation: string;
  } | null>(null);

  /**
   * 轮询时若服务端 current_index 已前进（如游戏端已提交答案），工作台自动进入下一题作答区。
   * 游戏端仍须手动「确认并结算技能」；此处只同步试卷题序，不干预战斗流程。
   */
  const syncPlayIndexFromPreview = useCallback(
    (questions: PaperQuestionPreview[], serverIdx: number, total: number) => {
      const pi = playIndexRef.current;
      if (serverIdx > pi) {
        setPlayIndex(Math.min(serverIdx, total - 1));
        setAwaitingNext(false);
        awaitingNextRef.current = false;
        setLastFeedback(null);
        return;
      }
      const cur = questions.find((q) => q.index === pi);
      const isLast = pi >= total - 1;
      if (cur?.answered && isLast) {
        setAwaitingNext(true);
        awaitingNextRef.current = true;
      }
    },
    []
  );

  const loadPreview = useCallback(
    async (paperId: string, opts?: { keepPlayIndex?: boolean }) => {
      const r = await fetch(`${API}/v1/papers/${paperId}/preview`);
      if (!r.ok) return;
      const data = await r.json();
      const questions: PaperQuestionPreview[] = data.questions || [];
      setPreview(questions);
      const serverIdx = typeof data.current_index === "number" ? data.current_index : 0;
      const total = questions.length || 1;

      if (opts?.keepPlayIndex) {
        syncPlayIndexFromPreview(questions, serverIdx, total);
      } else if (!awaitingNextRef.current) {
        setPlayIndex(Math.min(Math.max(0, serverIdx), total - 1));
      }

      setPaper((prev) =>
        prev
          ? {
              ...prev,
              status: data.status ?? prev.status,
              current_index: Math.max(prev.current_index, serverIdx),
            }
          : prev
      );
    },
    [syncPlayIndexFromPreview]
  );

  const pullWorkflow = useCallback(async () => {
    if (!learnerId) return;
    const wRes = await fetch(workflowUrl());
    if (wRes.ok) {
      const w = await wRes.json();
      setWorkflow(filterSessionWorkflowLogs(w.workflow_logs || []));
    }
  }, [learnerId, workflowUrl]);

  const refresh = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!learnerId) return false;
      if (!opts?.silent) setLoading(true);
      setError(null);
      try {
        const pRes = await fetch(`${API}/v1/learners/${encodeURIComponent(learnerId)}/profile`);
        if (pRes.ok) setProfile(await pRes.json());
        const wRes = await fetch(workflowUrl());
        if (wRes.ok) {
          const w = await wRes.json();
          setWorkflow(filterSessionWorkflowLogs(w.workflow_logs || []));
          if (w.active_paper) setPaper(w.active_paper);
        }
        const qRes = await fetch(`${API}/v1/papers/queue?learner_id=${encodeURIComponent(learnerId)}`);
        if (qRes.ok) {
          const q = (await qRes.json()) as { ready?: boolean };
          setNextPaperQueued(Boolean(q.ready));
        } else {
          setNextPaperQueued(false);
        }
        const rRes = await fetch(`${API}/v1/learners/${encodeURIComponent(learnerId)}/reserve`);
        if (rRes.ok) {
          const r = (await rRes.json()) as { reserve_count?: number };
          setReserveCount(r.reserve_count ?? 0);
        } else {
          setReserveCount(0);
        }
        const cur = await fetch(`${API}/v1/papers/current?learner_id=${encodeURIComponent(learnerId)}`);
        if (cur.ok) {
          const p = await cur.json();
          setPaper(p);
          await loadPreview(p.paper_id);
          return true;
        }
        setPaper(null);
        setPreview([]);
        return false;
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return false;
      } finally {
        if (!opts?.silent) setLoading(false);
      }
    },
    [learnerId, loadPreview, workflowUrl]
  );

  const applyPaperFromStart = useCallback(
    async (body: { paper?: PaperMeta; assembly_mode?: string; message?: string }) => {
      if (!body.paper) return;
      setPaper(body.paper);
      setPlayIndex(0);
      const mode = body.assembly_mode || null;
      setAssemblyMode(mode);
      if (body.message) {
        setAssemblyHint(body.message);
      } else if (mode === "hybrid") {
        setAssemblyHint("本卷已由 Reserve + 题库 + AI 补缺口组好，请直接答题。");
      } else if (mode === "promoted" || mode?.includes("promot")) {
        setAssemblyHint("已激活预生成试卷，请直接答题。");
      } else {
        setAssemblyHint("试卷已激活，请直接答题。");
      }
      await loadPreview(body.paper.paper_id);
      void pullWorkflow();
      const qRes = await fetch(`${API}/v1/papers/queue?learner_id=${encodeURIComponent(learnerId)}`);
      if (qRes.ok) {
        const q = (await qRes.json()) as { ready?: boolean };
        setNextPaperQueued(Boolean(q.ready));
      }
      const rRes = await fetch(`${API}/v1/learners/${encodeURIComponent(learnerId)}/reserve`);
      if (rRes.ok) {
        const r = (await rRes.json()) as { reserve_count?: number };
        setReserveCount(r.reserve_count ?? 0);
      }
    },
    [loadPreview, pullWorkflow, learnerId]
  );

  /** 完成当前卷后：激活排队卷或组下一卷（intent=next） */
  const startNextPaper = useCallback(async () => {
      if (!learnerId || startInFlight.current) return;
      if (paper?.status === "active") {
        setError("请先完成当前试卷并点击「完成试卷」");
        return;
      }
      startInFlight.current = true;
      beginLogSession();
      setAssembling(true);
      setError(null);
      setLastFeedback(null);
      setAwaitingNext(false);
      awaitingNextRef.current = false;
      const pollId = window.setInterval(() => {
        void pullWorkflow();
      }, 1500);
      try {
        const startQuery = paper ? "intent=next" : "fresh=true";
        const r = await fetchWithTimeout(
          `${API}/v1/sessions/${encodeURIComponent(learnerId)}/start?${startQuery}`,
          { method: "POST" },
          ASSEMBLY_FETCH_MS
        );
        if (!r.ok) {
          let detail = await r.text();
          try {
            const j = JSON.parse(detail) as { detail?: string };
            detail = j.detail ?? detail;
          } catch {
            /* plain */
          }
          if (r.status === 500 || r.status === 503) {
            try {
              const h = await fetch(`${API}/health`);
              if (h.ok) {
                const snap = (await h.json()) as { db_ready?: boolean; status?: string };
                if (snap.db_ready === false) {
                  detail =
                    (detail || `HTTP ${r.status}`) +
                    " — 数据库未就绪（/health 显示 db_ready=false）。请查看「Swigar API :8000」窗口日志并重启 API。";
                }
              }
            } catch {
              detail =
                (detail || `HTTP ${r.status}`) +
                " — 无法连接 Agent API。请确认已运行 scripts/dev_all.ps1 或 scripts/run_api.ps1。";
            }
          }
          throw new Error(detail || `HTTP ${r.status}`);
        }
        const body = (await r.json()) as {
          paper?: PaperMeta;
          message?: string;
          reused?: boolean;
          assembly_mode?: string;
        };
        if (body.reused && body.message) {
          setError(body.message);
        }
        await applyPaperFromStart(body);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        window.clearInterval(pollId);
        startInFlight.current = false;
        setAssembling(false);
      }
    },
    [learnerId, paper?.status, pullWorkflow, applyPaperFromStart, beginLogSession]
  );

  const syncPaperProgress = useCallback(async () => {
    const cur = await fetch(`${API}/v1/papers/current?learner_id=${encodeURIComponent(learnerId)}`);
    if (!cur.ok) return null;
    const p = (await cur.json()) as PaperMeta;
    setPaper(p);
    return p;
  }, [learnerId]);

  const advanceToServerIndex = useCallback(
    async (answeredIdx: number) => {
      const p = await syncPaperProgress();
      if (!p) return;
      const nextIdx = Math.min(Math.max(0, p.current_index), p.total_questions - 1);
      if (nextIdx > answeredIdx) {
        setPlayIndex(nextIdx);
        setAwaitingNext(false);
        awaitingNextRef.current = false;
        setLastFeedback(null);
      }
    },
    [syncPaperProgress]
  );

  const applyAnswerResult = useCallback(
    (idx: number, userAnswer: string, result: { is_correct: boolean; correct_answer: string; explanation: string }) => {
      setLastFeedback({
        index: idx,
        is_correct: Boolean(result.is_correct),
        correct_answer: String(result.correct_answer || ""),
        explanation: String(result.explanation || ""),
      });
      setAwaitingNext(true);
      awaitingNextRef.current = true;
      setPreview((prev) =>
        prev.map((q) =>
          q.index === idx
            ? {
                ...q,
                answered: true,
                is_correct: result.is_correct,
                user_answer: userAnswer,
                explanation: result.explanation || q.explanation,
              }
            : q
        )
      );
    },
    []
  );

  const submitAnswer = useCallback(
    async (userAnswer: string) => {
      if (!paper?.paper_id || submitInFlight.current) return null;
      submitInFlight.current = true;
      setSubmitting(true);
      setError(null);
      const synced = await syncPaperProgress();
      const serverIdx = synced?.current_index ?? paper.current_index ?? playIndex;
      if (serverIdx !== playIndex) {
        setPlayIndex(serverIdx);
        setError("请按顺序作答当前题（已同步到第 " + (serverIdx + 1) + " 题）");
        submitInFlight.current = false;
        setSubmitting(false);
        return null;
      }
      const idx = serverIdx;
      try {
        const r = await fetch(`${API}/v1/papers/${paper.paper_id}/answers`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_answer: userAnswer, question_index: idx, time_spent_ms: 5000 }),
        });
        const raw = await r.text();
        let result: {
          is_correct: boolean;
          correct_answer: string;
          explanation: string;
          question_index?: number;
        } | null = null;
        try {
          result = JSON.parse(raw) as typeof result;
        } catch {
          result = null;
        }
        if (!r.ok) {
          const detail =
            (result as { detail?: string } | null)?.detail ||
            raw ||
            `HTTP ${r.status}`;
          throw new Error(typeof detail === "string" ? detail : String(detail));
        }
        if (!result) {
          throw new Error("Invalid answer response");
        }
        applyAnswerResult(idx, userAnswer, result);
        await loadPreview(paper.paper_id, { keepPlayIndex: true });
        const p = await syncPaperProgress();
        const total = p?.total_questions ?? paper.total_questions;
        if (idx >= total - 1) {
          setAwaitingNext(true);
          awaitingNextRef.current = true;
        } else if (p && p.current_index > idx) {
          await advanceToServerIndex(idx);
        } else {
          setAwaitingNext(true);
          awaitingNextRef.current = true;
        }
        return result;
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.toLowerCase().includes("already answered")) {
          const pr = await fetch(`${API}/v1/papers/${paper.paper_id}/preview`);
          if (pr.ok) {
            const data = (await pr.json()) as { questions?: PaperQuestionPreview[]; current_index?: number };
            const q = data.questions?.find((x) => x.index === idx);
            if (q?.answered) {
              setPreview(data.questions || []);
              if (typeof data.current_index === "number") {
                setPaper((prev) => (prev ? { ...prev, current_index: data.current_index! } : prev));
              }
              applyAnswerResult(idx, q.user_answer || userAnswer, {
                is_correct: Boolean(q.is_correct),
                correct_answer: "",
                explanation: q.explanation || "",
              });
              setError(null);
              return null;
            }
          }
        }
        setError(msg);
        return null;
      } finally {
        submitInFlight.current = false;
        setSubmitting(false);
      }
    },
    [paper, playIndex, loadPreview, applyAnswerResult, syncPaperProgress, advanceToServerIndex]
  );

  const goNext = useCallback(() => {
    if (!paper?.paper_id) return;
    void advanceToServerIndex(playIndex);
  }, [paper, playIndex, advanceToServerIndex]);

  const finishPaper = useCallback(async () => {
    if (!paper?.paper_id) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API}/v1/papers/${paper.paper_id}/finish`, { method: "POST" });
      if (!r.ok) throw new Error(await r.text());
      setLastFeedback(null);
      setAwaitingNext(false);
      awaitingNextRef.current = false;
      setPaper(null);
      setPreview([]);
      setNextPaperQueued(false);
      setAssemblyMode(null);
      setAssemblyHint(null);
      await refresh({ silent: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [paper, loadPreview, refresh]);

  // 登录 / 切换学习者：仅恢复当前卷，不自动组卷
  useEffect(() => {
    if (!learnerId) return;
    void refresh({ silent: true });
  }, [learnerId, refresh]);

  useEffect(() => {
    if (!learnerId || !paper?.paper_id || paper.status !== "active") return;
    const tick = () => void loadPreview(paper.paper_id, { keepPlayIndex: true });
    tick();
    const id = window.setInterval(tick, 2000);
    const onFocus = () => tick();
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, [learnerId, paper?.paper_id, paper?.status, loadPreview]);

  const hasActivePaper = paper?.status === "active";
  const canStartNextPaper = !hasActivePaper && !assembling;
  const canAnswer =
    Boolean(paper?.paper_id) &&
    paper?.status === "active" &&
    !preview.find((q) => q.index === playIndex)?.answered;
  const isLastQuestion = paper ? playIndex >= paper.total_questions - 1 : false;

  return {
    profile,
    paper,
    preview,
    workflow,
    loading,
    assembling,
    nextPaperQueued,
    reserveCount,
    assemblyMode,
    assemblyHint,
    canStartNextPaper,
    hasActivePaper,
    error,
    playIndex,
    canAnswer,
    awaitingNext,
    isLastQuestion,
    lastFeedback,
    refresh,
    startNextPaper,
    submitAnswer,
    goNext,
    finishPaper,
    submitting,
  };
}
