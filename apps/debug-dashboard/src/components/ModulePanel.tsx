import { ARCH_MODULES, type ModuleId } from "../data/modules";

type Props = {
  moduleId: ModuleId | null;
};

export function ModulePanel({ moduleId }: Props) {
  const mod = ARCH_MODULES.find((m) => m.id === moduleId);
  if (!mod) {
    return (
      <div className="module-panel module-panel-empty">
        <p>点击架构图中的模块，查看职责与 API</p>
      </div>
    );
  }

  return (
    <div className="module-panel" style={{ borderColor: mod.color }}>
      <div className="module-panel-head" style={{ background: `${mod.color}18` }}>
        <span className="module-panel-dot" style={{ background: mod.color }} />
        <div>
          <h3>{mod.name}</h3>
          <span className="module-panel-en">{mod.nameEn}</span>
        </div>
      </div>
      <p className="module-panel-desc">{mod.description}</p>
      <h4>核心职责</h4>
      <ul>
        {mod.responsibilities.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      {mod.apis && mod.apis.length > 0 && (
        <>
          <h4>相关 API</h4>
          <ul className="api-list">
            {mod.apis.map((a) => (
              <li key={a}>
                <code>{a}</code>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
