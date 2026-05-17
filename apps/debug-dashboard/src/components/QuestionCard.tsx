export type Question = {
  id?: string;
  prompt?: string;
  type?: string;
  choices?: string[];
  correct_answer?: string;
  skill_tags?: string[];
  difficulty?: number;
};

export function QuestionCard({ q, index }: { q: Question; index?: number }) {
  const label = index != null ? `题目 ${index + 1}` : "题目";
  return (
    <article className="question-card">
      <header className="question-card-head">
        <span className="question-label">{label}</span>
        {q.id && <code className="question-id">{q.id}</code>}
        {q.skill_tags?.map((t) => (
          <span key={t} className="question-tag">
            {t}
          </span>
        ))}
        {q.difficulty != null && <span className="question-diff">难度 {q.difficulty}</span>}
      </header>
      <p className="question-prompt">{q.prompt || "（无题干）"}</p>
      {q.choices && q.choices.length > 0 && (
        <ul className="question-choices">
          {q.choices.map((c, i) => (
            <li key={i} className={c === q.correct_answer ? "choice-correct" : ""}>
              {String.fromCharCode(65 + i)}. {c}
            </li>
          ))}
        </ul>
      )}
      {q.correct_answer && !q.choices?.length && (
        <p className="question-answer">
          <strong>参考答案：</strong>
          {q.correct_answer}
        </p>
      )}
    </article>
  );
}

export function extractQuestions(data: unknown): Question[] {
  if (!data || typeof data !== "object") return [];
  const d = data as Record<string, unknown>;
  const content = d.content as Record<string, unknown> | undefined;
  const sources = [d.questions, content?.questions, d];
  for (const src of sources) {
    if (Array.isArray(src)) return src as Question[];
  }
  return [];
}
