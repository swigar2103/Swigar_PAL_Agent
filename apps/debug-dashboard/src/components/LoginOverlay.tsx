import { useCallback, useEffect, useState } from "react";
import {
  clearGameSession,
  getSavedQuickAuth,
  loginWithPhone,
  persistGameSession,
  registerUser,
  type GameUser,
  type SavedUserAuth,
} from "../lib/gameAuth";

type Mode = "quick" | "login" | "register";

type Props = {
  onAuthenticated: (user: GameUser) => void;
};

export function LoginOverlay({ onAuthenticated }: Props) {
  const [mode, setMode] = useState<Mode>("login");
  const [saved, setSaved] = useState<SavedUserAuth | null>(null);
  const [phoneNumber, setPhoneNumber] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const q = getSavedQuickAuth();
    if (q) {
      setSaved(q);
      setPhoneNumber(q.phoneNumber || "");
      setMode("quick");
    }
    requestAnimationFrame(() => setVisible(true));
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  const finish = useCallback(
    (user: GameUser) => {
      persistGameSession(user);
      onAuthenticated(user);
    },
    [onAuthenticated]
  );

  const handleQuick = () => {
    if (!saved) return;
    finish(saved);
  };

  const handleSwitchAccount = () => {
    clearGameSession();
    setSaved(null);
    setMode("login");
    setPassword("");
    setPhoneNumber("");
    setError("");
  };

  const handleLogin = async () => {
    if (!phoneNumber || !password) {
      setError("请输入手机号和密码");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const user = await loginWithPhone(phoneNumber, password);
      finish(user);
    } catch (e) {
      setError(e instanceof Error ? e.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async () => {
    if (!phoneNumber || !password || !displayName) {
      setError("请填写所有必填项");
      return;
    }
    if (phoneNumber.length !== 11) {
      setError("请输入正确的 11 位手机号");
      return;
    }
    if (password.length < 6) {
      setError("密码至少需要 6 位");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const user = await registerUser(phoneNumber, password, displayName);
      finish(user);
    } catch (e) {
      setError(e instanceof Error ? e.message : "注册失败");
    } finally {
      setLoading(false);
    }
  };

  const initial = (saved?.gameName || saved?.displayName || "学").charAt(0).toUpperCase();

  return (
    <div className={`login-overlay ${visible ? "login-overlay-visible" : ""}`} role="dialog" aria-modal="true">
      <div className="login-overlay-backdrop" aria-hidden />
      <div className="login-overlay-grid">
        <aside className="login-overlay-brand">
          <div className="login-brand-glow" aria-hidden />
          <img src="/logo.svg" alt="" className="login-brand-logo" width={56} height={56} />
          <p className="login-brand-kicker">PAL Paper-Agent</p>
          <h1 className="login-brand-title">学习与记忆，同一账号贯通</h1>
          <p className="login-brand-desc">
            使用与《战术对决》相同的账号登录。学习者 ID（uid）将同步至 MemPalace、组卷与 Agent 工作台。
          </p>
          <ul className="login-brand-features">
            <li>共享 game_user_id / savedUserAuth</li>
            <li>独立记忆库与学习者画像</li>
            <li>每次登录可开启全新试卷</li>
          </ul>
        </aside>

        <div className={`login-card ${visible ? "login-card-visible" : ""}`}>
          <header className="login-card-header">
            <h2>{mode === "register" ? "创建账号" : mode === "quick" ? "欢迎回来" : "登录"}</h2>
            <p className="muted">
              {mode === "quick"
                ? "检测到本机已保存的游戏账号"
                : "连接 TacticalDuel 用户服务（需游戏后端运行）"}
            </p>
          </header>

          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          {mode === "quick" && saved ? (
            <div className="login-quick">
              <div className="login-avatar" aria-hidden>
                {initial}
              </div>
              <div className="login-quick-meta">
                <strong>{saved.gameName || saved.displayName}</strong>
                <span className="muted">{saved.phoneNumber}</span>
                <span className="login-uid-tag">uid: {saved.uid}</span>
              </div>
              <button type="button" className="btn-login-primary" onClick={handleQuick}>
                进入工作台
              </button>
              <button type="button" className="btn-login-ghost" onClick={handleSwitchAccount}>
                切换账号
              </button>
            </div>
          ) : (
            <form
              className="login-form"
              onSubmit={(e) => {
                e.preventDefault();
                void (mode === "register" ? handleRegister() : handleLogin());
              }}
            >
              <label className="login-field">
                <span>手机号</span>
                <input
                  type="tel"
                  inputMode="numeric"
                  maxLength={11}
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value.replace(/\D/g, ""))}
                  placeholder="11 位手机号"
                  autoComplete="tel"
                />
              </label>

              {mode === "register" && (
                <label className="login-field">
                  <span>游戏昵称</span>
                  <input
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="用于游戏内显示"
                    maxLength={20}
                    autoComplete="nickname"
                  />
                </label>
              )}

              <label className="login-field">
                <span>密码</span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === "register" ? "至少 6 位" : "请输入密码"}
                  autoComplete={mode === "register" ? "new-password" : "current-password"}
                />
              </label>

              <button type="submit" className="btn-login-primary" disabled={loading}>
                {loading ? "处理中…" : mode === "register" ? "注册并进入" : "登录"}
              </button>

              <p className="login-switch">
                {mode === "register" ? (
                  <>
                    已有账号？
                    <button type="button" onClick={() => { setMode("login"); setError(""); }}>
                      去登录
                    </button>
                  </>
                ) : (
                  <>
                    还没有账号？
                    <button type="button" onClick={() => { setMode("register"); setError(""); }}>
                      注册
                    </button>
                  </>
                )}
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
