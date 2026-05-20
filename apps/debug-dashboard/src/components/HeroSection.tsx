import { useLanguage } from "../i18n/LanguageContext";

export function HeroSection() {
  const { t } = useLanguage();

  return (
    <section id="overview" className="hero">
      <div className="hero-content">
        <p className="hero-eyebrow">{t("hero.eyebrow")}</p>
        <h1>
          {t("hero.title1")}
          <br />
          <span className="hero-accent">{t("hero.title2")}</span>
        </h1>
        <p className="hero-lead">{t("hero.lead")}</p>
        <ul className="hero-stats">
          <li>
            <strong>9</strong>
            <span>{t("hero.stat.modules")}</span>
          </li>
          <li>
            <strong>3</strong>
            <span>{t("hero.stat.llm")}</span>
          </li>
          <li>
            <strong>∞</strong>
            <span>{t("hero.stat.memory")}</span>
          </li>
        </ul>
      </div>
      <div className="hero-visual">
        <img src="/swigar-logo.png" alt="" className="hero-logo" />
        <div className="hero-loop-card">
          <span className="loop-step">{t("hero.loop.behavior")}</span>
          <span className="loop-arrow">→</span>
          <span className="loop-step">{t("hero.loop.understand")}</span>
          <span className="loop-arrow">→</span>
          <span className="loop-step">{t("hero.loop.orchestrate")}</span>
          <span className="loop-arrow">→</span>
          <span className="loop-step">{t("hero.loop.gamify")}</span>
          <span className="loop-arrow">→</span>
          <span className="loop-step">{t("hero.loop.memory")}</span>
        </div>
      </div>
    </section>
  );
}
