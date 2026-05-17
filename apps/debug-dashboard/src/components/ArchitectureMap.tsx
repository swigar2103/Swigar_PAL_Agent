import type { CSSProperties } from "react";
import { ARCH_MODULES, type ModuleId } from "../data/modules";

type Props = {
  activeModule: ModuleId | null;
  onSelect: (id: ModuleId) => void;
  selected: ModuleId | null;
};

const FLOW_ORDER: ModuleId[] = [
  "game",
  "events",
  "memory",
  "situation",
  "orchestrator",
  "skills",
  "llm",
  "tools",
  "decision",
];

const ICONS: Record<ModuleId, string> = {
  game: "🎮",
  events: "⚡",
  memory: "🧠",
  situation: "🗺️",
  orchestrator: "🎯",
  skills: "✦",
  llm: "☁️",
  tools: "🔧",
  decision: "🏆",
};

export function ArchitectureMap({ activeModule, onSelect, selected }: Props) {
  return (
    <section className="arch-map" aria-label="系统架构">
      <div className="arch-flow-hint">
        <span className="arch-flow-label">数据流向</span>
        <span className="arch-arrow">
          游戏事件 → 事件层 → 记忆 / 情境 → 调度中心 → 技能 + LLM → 游戏 Impact
        </span>
      </div>
      <div className="arch-grid">
        {FLOW_ORDER.map((id, i) => {
          const mod = ARCH_MODULES.find((m) => m.id === id)!;
          const isActive = activeModule === id;
          const isSelected = selected === id;
          return (
            <div key={id} className="arch-cell-wrap">
              {i > 0 && <span className="arch-connector" />}
              <button
                type="button"
                className={`arch-node ${isActive ? "arch-node-pulse" : ""} ${isSelected ? "arch-node-selected" : ""}`}
                style={{ "--node-color": mod.color } as CSSProperties}
                onClick={() => onSelect(id)}
              >
                <span className="arch-node-icon">{ICONS[id]}</span>
                <span className="arch-node-name">{mod.name}</span>
                <span className="arch-node-en">{mod.nameEn}</span>
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}
