import type { GameUser } from "../lib/gameAuth";

type Props = {
  connected: boolean;
  apiOnline?: boolean;
  llmConfigured?: boolean;
  llmModel?: string;
  authUser?: GameUser | null;
  onSwitchAccount?: () => void;
};

export function Header({
  connected,
  apiOnline = false,
  llmConfigured,
  llmModel,
  authUser,
  onSwitchAccount,
}: Props) {
  const displayName = authUser?.gameName || authUser?.displayName;
  const initial = (displayName || "学").charAt(0).toUpperCase();

  return (
    <header className="site-header">
      <div className="brand">
        <img src="/logo.svg" alt="Swigar" className="brand-logo" width={40} height={40} />
        <div>
          <span className="brand-name">Swigar Agent</span>
          <span className="brand-tagline">AI 驱动的游戏化英语学习闭环</span>
        </div>
      </div>
      <nav className="header-nav">
        <a href="#overview">产品概览</a>
        <a href="#demo">实时演示</a>
        <a href="#modules">模块说明</a>
      </nav>
      <div className="header-badges">
        {authUser && (
          <div className="header-user">
            <span className="header-user-avatar" aria-hidden>
              {initial}
            </span>
            <span className="header-user-meta">
              <strong>{displayName}</strong>
              <span className="header-user-uid">{authUser.uid}</span>
            </span>
            {onSwitchAccount && (
              <button type="button" className="header-user-switch" onClick={onSwitchAccount}>
                切换账号
              </button>
            )}
          </div>
        )}
        <span
          className={`badge ${!apiOnline ? "badge-warn" : connected ? "badge-ok" : "badge-muted"}`}
          title={
            !apiOnline
              ? "请先运行 scripts/run_api.ps1（端口 8000）"
              : connected
                ? "Debug WebSocket 已连接，拓扑与 trace 实时更新"
                : "REST API 可用，WebSocket 正在重连（组卷/答题不受影响）"
          }
        >
          {!apiOnline ? "API 未连接" : connected ? "实时 trace 已连接" : "trace 重连中"}
        </span>
        {!apiOnline ? (
          <span className="badge badge-muted" title="需先连通 API 才能读取 LLM 配置">
            LLM 状态未知
          </span>
        ) : (
          <span className={`badge ${llmConfigured ? "badge-ok" : "badge-warn"}`}>
            LLM {llmConfigured ? llmModel || "已配置" : "未配置（检查 .env 中 DASHSCOPE_API_KEY）"}
          </span>
        )}
      </div>
    </header>
  );
}
