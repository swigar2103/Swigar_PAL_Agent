import { useCallback, useEffect, useRef, useState } from "react";
import { stepToModule, type ModuleId } from "../data/modules";
import { paperStepToModule, type PaperModuleId } from "../data/paperModules";
import { isBackgroundWorkflow } from "../lib/workflowLog";

const API = import.meta.env.VITE_API_URL || "";

async function fetchWithTimeout(url: string, ms: number): Promise<Response> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { signal: ctrl.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

function resolveDebugWsUrl(): string {
  const explicit = import.meta.env.VITE_API_URL as string | undefined;
  if (explicit) {
    try {
      const base = new URL(explicit);
      const proto = base.protocol === "https:" ? "wss:" : "ws:";
      return `${proto}//${base.host}/debug/stream`;
    } catch {
      /* fall through */
    }
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/debug/stream`;
}

export type TraceItem = {
  id: string;
  step: string;
  phase: string;
  moduleId: ModuleId | null;
  paperModuleId: PaperModuleId | null;
  raw: unknown;
  ts: string;
  durationMs?: number;
};

export type EventItem = {
  id: string;
  kind: string;
  raw: unknown;
  ts: string;
};

export function useAgentSocket() {
  const [connected, setConnected] = useState(false);
  const [apiOnline, setApiOnline] = useState(false);
  const [activeModule, setActiveModule] = useState<ModuleId | null>(null);
  const [activePaperModule, setActivePaperModule] = useState<PaperModuleId | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [traces, setTraces] = useState<TraceItem[]>([]);
  const [decision, setDecision] = useState<Record<string, unknown> | null>(null);
  const [llmStatus, setLlmStatus] = useState<{
    llm_configured?: boolean;
    llm_model?: string;
    llm_enabled?: boolean;
  } | null>(null);
  const [running, setRunning] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const reconnectAttempt = useRef(0);
  const moduleHighlightTimer = useRef<ReturnType<typeof setTimeout>>();
  const paperHighlightTimer = useRef<ReturnType<typeof setTimeout>>();
  const workflowListeners = useRef(new Set<(msg: { category: string; message: string; ts: string }) => void>());
  const unmounted = useRef(false);

  const pulseModule = useCallback((id: ModuleId | null) => {
    if (moduleHighlightTimer.current) clearTimeout(moduleHighlightTimer.current);
    setActiveModule(id);
    if (id) {
      moduleHighlightTimer.current = setTimeout(() => setActiveModule(null), 2400);
    }
  }, []);

  const pulsePaperModule = useCallback((id: PaperModuleId | null, holdMs = 5000) => {
    if (paperHighlightTimer.current) clearTimeout(paperHighlightTimer.current);
    setActivePaperModule(id);
    if (id) {
      paperHighlightTimer.current = setTimeout(() => setActivePaperModule(null), holdMs);
    }
  }, []);

  const checkHealth = useCallback(async () => {
    try {
      const r = await fetchWithTimeout(`${API}/health`, 20_000);
      if (!r.ok) {
        setApiOnline(false);
        setLlmStatus(null);
        return false;
      }
      const data = await r.json();
      setApiOnline(true);
      setLlmStatus(data);
      return true;
    } catch {
      setApiOnline(false);
      setLlmStatus(null);
      return false;
    }
  }, []);

  const connectWs = useCallback(() => {
    if (unmounted.current) return;
    const existing = wsRef.current;
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const ws = new WebSocket(resolveDebugWsUrl());
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttempt.current = 0;
      setConnected(true);
      pulsePaperModule("orchestrator");
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      if (unmounted.current) return;
      const delay = Math.min(8000, 500 * 2 ** reconnectAttempt.current);
      reconnectAttempt.current += 1;
      reconnectTimer.current = setTimeout(() => {
        void checkHealth().then((ok) => {
          if (ok) connectWs();
        });
      }, delay);
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        const kind = msg.kind || "message";
        const ts = new Date().toLocaleTimeString();

        if (kind === "connected") {
          setConnected(true);
          return;
        }

        if (kind === "trace") {
          const stepObj = msg.step || {};
          const step = stepObj.step || "trace";
          const phase = stepObj.phase || "";
          const paperMod = paperStepToModule(step, phase, undefined, stepObj, step);
          const mod = paperMod ? null : stepToModule(step, phase);
          if (paperMod) pulsePaperModule(paperMod, 90_000);
          else pulseModule(mod);
          setTraces((prev) =>
            [
              ...prev,
              {
                id: crypto.randomUUID(),
                step,
                phase,
                moduleId: mod,
                paperModuleId: paperMod,
                raw: msg.step || msg,
                ts,
                durationMs: stepObj.duration_ms,
              },
            ].slice(-80)
          );
        } else if (kind === "workflow") {
          const wf = {
            category: String(msg.category || "info"),
            message: String(msg.message || ""),
            ts,
          };
          const wfData = (msg.data || {}) as Record<string, unknown>;
          if (isBackgroundWorkflow({ message: wf.message, data: wfData })) {
            workflowListeners.current.forEach((fn) =>
              fn({ ...wf, category: "后台", message: `[后台] ${wf.message}` })
            );
            return;
          }
          const paperMod = paperStepToModule(undefined, undefined, wf.category, msg.data, wf.message);
          const holdMs = wf.category === "出题" ? 120_000 : 8000;
          if (paperMod) {
            pulsePaperModule(paperMod, holdMs);
            setTraces((prev) =>
              [
                ...prev,
                {
                  id: crypto.randomUUID(),
                  step: wf.message || "workflow",
                  phase: wf.category,
                  moduleId: null,
                  paperModuleId: paperMod,
                  raw: msg,
                  ts,
                },
              ].slice(-80)
            );
          }
          workflowListeners.current.forEach((fn) => fn(wf));
          setEvents((prev) =>
            [...prev, { id: crypto.randomUUID(), kind: `workflow:${wf.category}`, raw: msg, ts }].slice(-40)
          );
        } else if (kind === "decision") {
          pulseModule("decision");
          setDecision(msg.decision);
          setTraces((prev) =>
            [
              ...prev,
              {
                id: crypto.randomUUID(),
                step: "decision",
                phase: "orchestrator",
                moduleId: "decision" as ModuleId,
                paperModuleId: null,
                raw: msg.decision,
                ts,
              },
            ].slice(-60)
          );
        } else {
          if (kind === "event_processed") pulseModule("events");
          setEvents((prev) => [...prev, { id: crypto.randomUUID(), kind, raw: msg, ts }].slice(-40));
        }
      } catch {
        /* ignore */
      }
    };
  }, [checkHealth, pulseModule, pulsePaperModule]);

  useEffect(() => {
    unmounted.current = false;
    void checkHealth().then((ok) => {
      if (ok) connectWs();
    });

    const healthPoll = window.setInterval(() => {
      void checkHealth().then((ok) => {
        if (ok && !wsRef.current) connectWs();
      });
    }, 12000);

    return () => {
      unmounted.current = true;
      window.clearInterval(healthPoll);
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (moduleHighlightTimer.current) clearTimeout(moduleHighlightTimer.current);
      if (paperHighlightTimer.current) clearTimeout(paperHighlightTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [checkHealth, connectWs]);

  const postEvent = useCallback(
    async (body: Record<string, unknown>) => {
      setRunning(true);
      pulseModule("game");
      try {
        const res = await fetch(`${API}/v1/events`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        setEvents((prev) =>
          [...prev, { id: crypto.randomUUID(), kind: "api_response", raw: data, ts: new Date().toLocaleTimeString() }].slice(-40)
        );
        return data;
      } finally {
        setRunning(false);
      }
    },
    [pulseModule]
  );

  const orchestrate = useCallback(
    async (learnerId: string, sessionId: string) => {
      setRunning(true);
      pulseModule("orchestrator");
      try {
        const res = await fetch(
          `${API}/v1/orchestrate?learner_id=${encodeURIComponent(learnerId)}&session_id=${encodeURIComponent(sessionId)}`,
          { method: "POST" }
        );
        const data = await res.json();
        setDecision(data);
        return data;
      } finally {
        setRunning(false);
      }
    },
    [pulseModule]
  );

  const clearLogs = useCallback(() => {
    setEvents([]);
    setTraces([]);
    setDecision(null);
    setActiveModule(null);
    setActivePaperModule(null);
  }, []);

  const onWorkflow = useCallback(
    (listener: (msg: { category: string; message: string; ts: string }) => void) => {
      workflowListeners.current.add(listener);
      return () => {
        workflowListeners.current.delete(listener);
      };
    },
    []
  );

  return {
    API,
    connected,
    apiOnline,
    activeModule,
    activePaperModule,
    events,
    traces,
    decision,
    llmStatus,
    running,
    postEvent,
    orchestrate,
    clearLogs,
    pulseModule,
    onWorkflow,
  };
}
