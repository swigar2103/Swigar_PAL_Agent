import { useMemo, type CSSProperties } from "react";
import type { TraceItem } from "../hooks/useAgentSocket";
import {
  buildModuleActivity,
  edgePath,
  getPaperModule,
  getPipelineModules,
  PAPER_DISPLAY_EDGES,
  PAPER_GRAPH_SIZE,
  PAPER_LAYERS,
  PAPER_MODULES,
  PAPER_NODE_POSITIONS,
  type ModuleActivity,
  type PaperLayerId,
  type PaperModuleId,
} from "../data/paperModules";
import { useLanguage } from "../i18n/LanguageContext";
import type { MessageKey } from "../i18n/messages";

const PAPER_LAYER_KEYS: Record<PaperLayerId, MessageKey> = {
  ingress: "paperLayer.ingress",
  control: "paperLayer.control",
  generation: "paperLayer.generation",
  infra: "paperLayer.infra",
  delivery: "paperLayer.delivery",
  answer: "paperLayer.answer",
  adapt: "paperLayer.adapt",
};

type Props = {
  activeModule: PaperModuleId | null;
  selected: PaperModuleId | null;
  onSelect: (id: PaperModuleId) => void;
  connected?: boolean;
  apiOnline?: boolean;
  hasPaper?: boolean;
  assembling?: boolean;
  traces?: TraceItem[];
};

function GearIcon({ spinning, color }: { spinning: boolean; color: string }) {
  return (
    <svg
      className={`paper-arch-gear ${spinning ? "paper-arch-gear-spin" : ""}`}
      viewBox="0 0 24 24"
      width="14"
      height="14"
      style={{ color }}
      aria-hidden
    >
      <path
        fill="currentColor"
        d="M12 15.5A3.5 3.5 0 0 1 8.5 12 3.5 3.5 0 0 1 12 8.5a3.5 3.5 0 0 1 3.5 3.5 3.5 3.5 0 0 1-3.5 3.5m7.43-2.53c.04-.32.07-.64.07-.97 0-.33-.03-.66-.07-.98l2.11-1.65c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.39-.3-.61-.22l-2.49 1c-.52-.4-1.08-.73-1.69-.98l-.38-2.65A.506.506 0 0 0 14 2h-4c-.25 0-.46.18-.5.42l-.38 2.65c-.61.25-1.17.59-1.69.98l-2.49-1c-.22-.08-.49 0-.61.22l-2 3.46c-.13.22-.07.49.12.64l2.11 1.65c-.04.32-.07.65-.07.98 0 .33.03.66.07.98l-2.11 1.65c-.19.15-.24.42-.12.64l2 3.46c.12.22.39.3.61.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.04.24.25.42.5.42h4c.25 0 .46-.18.5-.42l.38-2.65c.61-.25 1.17-.59 1.69-.98l2.49 1c.22.08.49 0 .61-.22l2-3.46c.12-.22.07-.49-.12-.64l-2.11-1.65Z"
      />
    </svg>
  );
}

function StatusDot({ state }: { state: ModuleActivity["state"] }) {
  return <span className={`paper-arch-status paper-arch-status-${state}`} aria-hidden />;
}

function ArchLegend({
  connected,
  apiOnline,
  t,
}: {
  connected?: boolean;
  apiOnline?: boolean;
  t: (key: MessageKey) => string;
}) {
  return (
    <ul className="paper-arch-legend" aria-label={t("paperArch.legendAria")}>
      <li>
        <span className="paper-arch-status paper-arch-status-active" /> {t("paperArch.legend.active")}
      </li>
      <li>
        <span className="paper-arch-status paper-arch-status-warm" /> {t("paperArch.legend.warm")}
      </li>
      <li>
        <span className="paper-arch-status paper-arch-status-seen" /> {t("paperArch.legend.seen")}
      </li>
      <li>
        <span className="paper-arch-status paper-arch-status-cold" /> {t("paperArch.legend.cold")}
      </li>
      {!apiOnline && <li className="paper-arch-legend-warn">{t("paperArch.apiOff")}</li>}
      {apiOnline && !connected && <li className="paper-arch-legend-warn">{t("paperArch.traceReconnect")}</li>}
    </ul>
  );
}

export function PaperArchitectureLive({
  activeModule,
  selected,
  onSelect,
  connected,
  apiOnline,
  hasPaper,
  assembling,
  traces = [],
}: Props) {
  const { locale, t } = useLanguage();
  const idleModule: PaperModuleId | null =
    connected && !activeModule
      ? assembling
        ? "orchestrator"
        : hasPaper
          ? "orchestrator"
          : "event_bus"
      : null;
  const highlight = activeModule || idleModule;

  const traceRows = useMemo(
    () =>
      traces.map((t) => ({
        paperModuleId: t.paperModuleId,
        step: t.step,
        ts: t.ts,
      })),
    [traces]
  );

  const activity = useMemo(
    () => buildModuleActivity(traceRows, activeModule),
    [traceRows, activeModule]
  );

  const pipeline = getPipelineModules();
  const pipelineDone = pipeline.filter((m) => activity[m.id].state !== "cold").length;

  const recentSteps = useMemo(() => {
    return [...traces]
      .reverse()
      .filter((t) => t.paperModuleId)
      .slice(0, 4)
      .map((t) => ({
        step: t.step,
        mod:
          (locale === "en"
            ? getPaperModule(t.paperModuleId!)?.nameEn
            : getPaperModule(t.paperModuleId!)?.name) ?? t.paperModuleId,
        ts: t.ts,
      }));
  }, [traces, locale]);

  return (
    <section
      className={`paper-arch-live${assembling ? " paper-arch-live-assembling" : ""}`}
      aria-label={t("paperArch.aria")}
    >
      <div className="paper-arch-head">
        <h4 className="paper-arch-title">{t("paperArch.title")}</h4>
        <ArchLegend connected={connected} apiOnline={apiOnline} t={t} />
      </div>
      <div
        className="paper-arch-pipeline"
        role="progressbar"
        aria-valuenow={pipelineDone}
        aria-valuemax={pipeline.length}
      >
        <span className="paper-arch-pipeline-label">
          {t("paperArch.pipeline")} {pipelineDone}/{pipeline.length}
        </span>
        <div className="paper-arch-pipeline-track">
          {pipeline.map((m) => {
            const st = activity[m.id].state;
            return (
              <span
                key={m.id}
                className={`paper-arch-pipeline-step paper-arch-pipeline-${st}${
                  activeModule === m.id ? " is-current" : ""
                }`}
                title={m.name}
              />
            );
          })}
        </div>
      </div>

      <div className="paper-arch-svg-wrap paper-arch-whiteboard">
        <svg
          viewBox={`0 0 ${PAPER_GRAPH_SIZE.width} ${PAPER_GRAPH_SIZE.height}`}
          className="paper-arch-svg"
          role="img"
        >
          <defs>
            <marker id="arrow-flow" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto">
              <polygon points="0 0, 7 3.5, 0 7" fill="#64748b" />
            </marker>
            <marker id="arrow-lit" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto">
              <polygon points="0 0, 7 3.5, 0 7" fill="#2dd4bf" />
            </marker>
          </defs>
          {PAPER_LAYERS.map((layer) => (
            <g key={layer.id}>
              <rect
                x={12}
                y={layer.y}
                width={PAPER_GRAPH_SIZE.width - 24}
                height={layer.height}
                rx={8}
                className="paper-arch-layer-bg"
                fill={layer.tint}
              />
              <text x={20} y={layer.y + 16} className="paper-arch-layer-label-svg">
                {t(PAPER_LAYER_KEYS[layer.id])}
              </text>
            </g>
          ))}
          {PAPER_DISPLAY_EDGES.map((edge) => {
            const a = PAPER_NODE_POSITIONS[edge.from];
            const b = PAPER_NODE_POSITIONS[edge.to];
            const lit =
              highlight === edge.from ||
              highlight === edge.to ||
              activity[edge.from].state === "active" ||
              activity[edge.to].state === "active" ||
              activity[edge.from].state === "warm" ||
              activity[edge.to].state === "warm";
            const d = edgePath(a, b, edge.kind);
            return (
              <path
                key={`${edge.from}-${edge.to}`}
                d={d}
                fill="none"
                className={`paper-arch-edge paper-arch-edge-${edge.kind}${
                  lit ? " paper-arch-edge-lit" : ""
                }`}
                markerEnd={lit ? "url(#arrow-lit)" : "url(#arrow-flow)"}
              />
            );
          })}
        </svg>
        {PAPER_MODULES.map((mod) => {
          const pos = PAPER_NODE_POSITIONS[mod.id];
          const act = activity[mod.id];
          const isActive = act.state === "active" || highlight === mod.id;
          const isSelected = selected === mod.id;
          const leftPct = (pos.x / PAPER_GRAPH_SIZE.width) * 100;
          const topPct = (pos.y / PAPER_GRAPH_SIZE.height) * 100;
          const modLabel = locale === "en" ? mod.nameEn : mod.name;
          const tip = act.lastStep
            ? `${mod.description}\n${t("paperArch.recentColon")}${act.lastStep}`
            : mod.description;
          return (
            <button
              key={mod.id}
              type="button"
              className={`paper-arch-node paper-arch-node-abs paper-arch-node-${act.state}${
                isActive ? " paper-arch-node-active" : ""
              }${isSelected ? " paper-arch-node-selected" : ""}${
                idleModule === mod.id ? " paper-arch-node-idle" : ""
              }`}
              style={
                {
                  "--node-color": mod.color,
                  left: `${leftPct}%`,
                  top: `${topPct}%`,
                } as CSSProperties
              }
              onClick={() => onSelect(mod.id)}
                title={tip}
              >
                <StatusDot state={act.state} />
                <GearIcon spinning={isActive} color={mod.color} />
                <span className="paper-arch-node-name">{modLabel}</span>
              {act.count > 0 ? <span className="paper-arch-node-count">{act.count}</span> : null}
            </button>
          );
        })}
      </div>

      {recentSteps.length > 0 ? (
        <ul className="paper-arch-recent" aria-label={t("paperArch.recentAria")}>
          {recentSteps.map((r, i) => (
            <li key={`${r.ts}-${i}`}>
              <time>{r.ts}</time>
              <strong>{r.mod}</strong>
              <code>{r.step}</code>
            </li>
          ))}
        </ul>
      ) : null}

      <p className="muted paper-arch-hint">
        {t("paperArch.hint")}
        {!apiOnline ? t("paperArch.hintApiOff") : !connected ? t("paperArch.hintWsOff") : ""}
      </p>
    </section>
  );
}
