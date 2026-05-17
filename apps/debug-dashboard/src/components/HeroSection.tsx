export function HeroSection() {
  return (
    <section id="overview" className="hero">
      <div className="hero-content">
        <p className="hero-eyebrow">Product Showcase · Agent Platform</p>
        <h1>
          让学习藏在游戏里，
          <br />
          <span className="hero-accent">让 AI 成为学习导演</span>
        </h1>
        <p className="hero-lead">
          Swigar 将诊断、规划、记忆宫殿与游戏 Impact 连成闭环。学生在地牢与 NPC 中练习英语，
          系统在后台理解每一次失误并生成个性化任务。
        </p>
        <ul className="hero-stats">
          <li>
            <strong>9</strong>
            <span>协作模块</span>
          </li>
          <li>
            <strong>3</strong>
            <span>LLM 调度步骤</span>
          </li>
          <li>
            <strong>∞</strong>
            <span>学习者记忆演化</span>
          </li>
        </ul>
      </div>
      <div className="hero-visual">
        <img src="/swigar-logo.png" alt="" className="hero-logo" />
        <div className="hero-loop-card">
          <span className="loop-step">行为</span>
          <span className="loop-arrow">→</span>
          <span className="loop-step">理解</span>
          <span className="loop-arrow">→</span>
          <span className="loop-step">调度</span>
          <span className="loop-arrow">→</span>
          <span className="loop-step">游戏化</span>
          <span className="loop-arrow">→</span>
          <span className="loop-step">记忆</span>
        </div>
      </div>
    </section>
  );
}
