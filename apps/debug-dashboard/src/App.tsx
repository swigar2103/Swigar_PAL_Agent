import { useCallback, useEffect, useState } from "react";
import { ArchitectureMap } from "./components/ArchitectureMap";
import { DecisionPanel } from "./components/DecisionPanel";
import { DemoConsole } from "./components/DemoConsole";
import { Header } from "./components/Header";
import { HeroSection } from "./components/HeroSection";
import { LoginOverlay } from "./components/LoginOverlay";
import { ModulePanel } from "./components/ModulePanel";
import { WorkflowTimeline } from "./components/WorkflowTimeline";
import { DEMO_SCENARIOS } from "./data/modules";
import type { ModuleId } from "./data/modules";
import type { PaperModuleId } from "./data/paperModules";
import { useAgentSocket } from "./hooks/useAgentSocket";
import { AgentWorkbench } from "./components/AgentWorkbench";
import {
  clearGameSession,
  getCurrentUser,
  type GameUser,
} from "./lib/gameAuth";
import { getLearnerId, setLearnerId } from "./lib/learnerId";
import { useLanguage } from "./i18n/LanguageContext";

export default function App() {
  const { t } = useLanguage();
  const [authUser, setAuthUser] = useState<GameUser | null>(() => getCurrentUser());
  const [learnerId, setLearnerIdState] = useState(() => getLearnerId());
  const [sessionId, setSessionId] = useState("s_demo");
  const [selectedModule, setSelectedModule] = useState<ModuleId | null>(null);
  const [selectedPaperModule, setSelectedPaperModule] = useState<PaperModuleId | null>(null);

  const [workflowFeed, setWorkflowFeed] = useState<
    Array<{ category: string; message: string; ts: string }>
  >([]);

  const {
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
    onWorkflow,
  } = useAgentSocket();

  useEffect(() => {
    return onWorkflow((msg) => {
      setWorkflowFeed((prev) => [...prev, msg].slice(-50));
    });
  }, [onWorkflow]);

  const handleAuthenticated = useCallback(
    (user: GameUser) => {
      clearLogs();
      setWorkflowFeed([]);
      setAuthUser(user);
      setLearnerId(user.uid);
      setLearnerIdState(user.uid);
    },
    [clearLogs]
  );

  const handleSwitchAccountWithReset = useCallback(() => {
    clearLogs();
    setWorkflowFeed([]);
    clearGameSession();
    setAuthUser(null);
  }, [clearLogs]);


  const runScenario = async (scenarioId: string) => {
    const scenario = DEMO_SCENARIOS.find((s) => s.id === scenarioId);
    if (!scenario) return;

    const body = {
      type: scenario.eventType,
      learner_id: learnerId,
      session_id: sessionId,
      game_context: {
        map_id: "castle",
        room_id: "r_07",
        npc_id: "mentor",
        quest_id: "grammar_dungeon_1",
      },
      payload: scenario.payload,
    };

    await postEvent(body);
    if ("orchestrateAfter" in scenario && scenario.orchestrateAfter) {
      await orchestrate(learnerId, sessionId);
    }
  };

  return (
    <div className="site">
      <Header
        connected={connected}
        apiOnline={apiOnline}
        llmConfigured={llmStatus?.llm_configured}
        llmModel={llmStatus?.llm_model as string | undefined}
        authUser={authUser}
        onSwitchAccount={authUser ? handleSwitchAccountWithReset : undefined}
      />

      <main>
        <HeroSection />

        <AgentWorkbench
          key={learnerId}
          learnerId={learnerId}
          workflowFeed={workflowFeed}
          traces={traces}
          connected={connected}
          apiOnline={apiOnline}
          activePaperModule={activePaperModule}
          selectedPaperModule={selectedPaperModule}
          onSelectPaperModule={setSelectedPaperModule}
          paperWorkflowEvents={events
            .filter((e) => e.kind.startsWith("workflow:"))
            .map((e) => {
              const raw = e.raw as { category?: string; message?: string; data?: Record<string, unknown> };
              return {
                category: String(raw?.category || ""),
                message: String(raw?.message || ""),
                ts: e.ts,
                raw: e.raw,
                data: raw?.data,
              };
            })}
        />

        <section id="demo" className="section demo-section">
          <ArchitectureMap
            activeModule={activeModule}
            selected={selectedModule}
            onSelect={setSelectedModule}
          />

          <div className="demo-layout">
            <div className="demo-left">
              <DemoConsole
                learnerId={learnerId}
                sessionId={sessionId}
                onLearnerId={setLearnerIdState}
                onSessionId={setSessionId}
                running={running}
                onRunScenario={runScenario}
                onOrchestrate={() => orchestrate(learnerId, sessionId)}
                onClear={clearLogs}
              />
              <div id="modules" className="module-detail-wrap">
                <ModulePanel moduleId={selectedModule} />
              </div>
            </div>

            <div className="demo-right">
              <div className="panel-card">
                <h3>{t("app.workflowReadable")}</h3>
                <WorkflowTimeline traces={traces} llmConfigured={llmStatus?.llm_configured} />
              </div>
              <div className="panel-card panel-decision">
                <h3>{t("app.gameImpact")}</h3>
                <DecisionPanel decision={decision} />
              </div>
            </div>
          </div>
        </section>

        <section className="section events-section">
          <h2>{t("app.events")}</h2>
          <div className="events-log">
            {events.length === 0 ? (
              <p className="muted">{t("app.noEvents")}</p>
            ) : (
              events.map((e) => (
                <details key={e.id} className="event-item">
                  <summary>
                    {e.kind} · {e.ts}
                  </summary>
                  <pre>{JSON.stringify(e.raw, null, 2)}</pre>
                </details>
              ))
            )}
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <span>{t("footer.platform")}</span>
        <span>{t("footer.docs")}</span>
      </footer>

      {!authUser && <LoginOverlay onAuthenticated={handleAuthenticated} />}
    </div>
  );
}
