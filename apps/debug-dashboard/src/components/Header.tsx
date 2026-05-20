import type { GameUser } from "../lib/gameAuth";
import { useLanguage } from "../i18n/LanguageContext";

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
  const { locale, toggleLocale, t } = useLanguage();
  const displayName = authUser?.gameName || authUser?.displayName;
  const initial = (displayName || (locale === "zh" ? "学" : "L")).charAt(0).toUpperCase();

  return (
    <header className="site-header">
      <div className="brand">
        <img src="/logo.svg" alt="Swigar" className="brand-logo" width={40} height={40} />
        <div>
          <span className="brand-name">Swigar Agent</span>
          <span className="brand-tagline">{t("header.tagline")}</span>
        </div>
      </div>
      <nav className="header-nav">
        <a href="#overview">{t("header.nav.overview")}</a>
        <a href="#demo">{t("header.nav.demo")}</a>
        <a href="#modules">{t("header.nav.modules")}</a>
      </nav>
      <div className="header-badges">
        <button
          type="button"
          className="lang-toggle"
          onClick={toggleLocale}
          aria-label={t("lang.toggleAria")}
          title={t("lang.toggleAria")}
        >
          <span className="lang-toggle-label">{locale === "zh" ? "中文" : "EN"}</span>
          <span className="lang-toggle-sep" aria-hidden>
            /
          </span>
          <span className="lang-toggle-target">{t("lang.toggle")}</span>
        </button>
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
                {t("header.switchAccount")}
              </button>
            )}
          </div>
        )}
        <span
          className={`badge ${!apiOnline ? "badge-warn" : connected ? "badge-ok" : "badge-muted"}`}
          title={
            !apiOnline
              ? t("header.apiOffTitle")
              : connected
                ? t("header.traceOkTitle")
                : t("header.traceReconnectTitle")
          }
        >
          {!apiOnline ? t("header.apiOff") : connected ? t("header.traceOk") : t("header.traceReconnect")}
        </span>
        {!apiOnline ? (
          <span className="badge badge-muted" title={t("header.llmUnknownTitle")}>
            {t("header.llmUnknown")}
          </span>
        ) : (
          <span className={`badge ${llmConfigured ? "badge-ok" : "badge-warn"}`}>
            LLM {llmConfigured ? llmModel || t("header.llmOn") : t("header.llmOff")}
          </span>
        )}
      </div>
    </header>
  );
}
