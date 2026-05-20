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
import { useLanguage } from "../i18n/LanguageContext";

type Mode = "quick" | "login" | "register";

type Props = {
  onAuthenticated: (user: GameUser) => void;
};

export function LoginOverlay({ onAuthenticated }: Props) {
  const { locale, t } = useLanguage();
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
      setError(t("login.err.phonePassword"));
      return;
    }
    setLoading(true);
    setError("");
    try {
      const user = await loginWithPhone(phoneNumber, password);
      finish(user);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("login.err.loginFailed"));
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async () => {
    if (!phoneNumber || !password || !displayName) {
      setError(t("login.err.required"));
      return;
    }
    if (phoneNumber.length !== 11) {
      setError(t("login.err.phoneLen"));
      return;
    }
    if (password.length < 6) {
      setError(t("login.err.passwordLen"));
      return;
    }
    setLoading(true);
    setError("");
    try {
      const user = await registerUser(phoneNumber, password, displayName);
      finish(user);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("login.err.registerFailed"));
    } finally {
      setLoading(false);
    }
  };

  const initial = (saved?.gameName || saved?.displayName || (locale === "zh" ? "学" : "L"))
    .charAt(0)
    .toUpperCase();

  return (
    <div className={`login-overlay ${visible ? "login-overlay-visible" : ""}`} role="dialog" aria-modal="true">
      <div className="login-overlay-backdrop" aria-hidden />
      <div className="login-overlay-grid">
        <aside className="login-overlay-brand">
          <div className="login-brand-glow" aria-hidden />
          <img src="/logo.svg" alt="" className="login-brand-logo" width={56} height={56} />
          <p className="login-brand-kicker">{t("login.brand.kicker")}</p>
          <h1 className="login-brand-title">{t("login.brand.title")}</h1>
          <p className="login-brand-desc">{t("login.brand.desc")}</p>
          <ul className="login-brand-features">
            <li>{t("login.brand.f1")}</li>
            <li>{t("login.brand.f2")}</li>
            <li>{t("login.brand.f3")}</li>
          </ul>
        </aside>

        <div className={`login-card ${visible ? "login-card-visible" : ""}`}>
          <header className="login-card-header">
            <h2>
              {mode === "register"
                ? t("login.title.register")
                : mode === "quick"
                  ? t("login.title.quick")
                  : t("login.title.login")}
            </h2>
            <p className="muted">
              {mode === "quick" ? t("login.subtitle.quick") : t("login.subtitle.default")}
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
                {t("login.enter")}
              </button>
              <button type="button" className="btn-login-ghost" onClick={handleSwitchAccount}>
                {t("login.switchAccount")}
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
                <span>{t("login.phone")}</span>
                <input
                  type="tel"
                  inputMode="numeric"
                  maxLength={11}
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value.replace(/\D/g, ""))}
                  placeholder={t("login.phonePlaceholder")}
                  autoComplete="tel"
                />
              </label>

              {mode === "register" && (
                <label className="login-field">
                  <span>{t("login.nickname")}</span>
                  <input
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder={t("login.nicknamePlaceholder")}
                    maxLength={20}
                    autoComplete="nickname"
                  />
                </label>
              )}

              <label className="login-field">
                <span>{t("login.password")}</span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={
                    mode === "register" ? t("login.passwordRegisterPlaceholder") : t("login.passwordPlaceholder")
                  }
                  autoComplete={mode === "register" ? "new-password" : "current-password"}
                />
              </label>

              <button type="submit" className="btn-login-primary" disabled={loading}>
                {loading
                  ? t("login.processing")
                  : mode === "register"
                    ? t("login.submitRegister")
                    : t("login.submitLogin")}
              </button>

              <p className="login-switch">
                {mode === "register" ? (
                  <>
                    {t("login.hasAccount")}
                    <button type="button" onClick={() => { setMode("login"); setError(""); }}>
                      {t("login.goLogin")}
                    </button>
                  </>
                ) : (
                  <>
                    {t("login.noAccount")}
                    <button type="button" onClick={() => { setMode("register"); setError(""); }}>
                      {t("login.register")}
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
