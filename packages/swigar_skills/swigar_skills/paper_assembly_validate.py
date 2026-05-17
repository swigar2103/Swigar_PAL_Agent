"""Paper-level assembly validation (structure, diversity, error targeting)."""

from __future__ import annotations

import os
from typing import Any

from swigar_core.models import ExamPaper, PaperPlan, QuestionItem
from swigar_tools.error_pattern import infer_error_pattern, score_error_targeting
from swigar_tools.knowledge_clusters import check_knowledge_point_mix, kp_mix_enabled
from swigar_tools.paper_builder import DB_COUNT, GENERATED_COUNT, PAPER_SIZE
from swigar_tools.question_similarity import check_intra_paper_diversity


def _min_error_targeted() -> int:
    return max(1, min(6, int(os.environ.get("SWIGAR_MIN_ERROR_TARGETED_GENERATED", "3"))))


def validate_paper_assembly(
    paper: ExamPaper,
    plan: PaperPlan,
    *,
    error_pattern: dict[str, Any] | None = None,
    learner_level: int = 2,
) -> dict[str, Any]:
    """Validate assembled 10-question paper; return score, issues, recommendation."""
    issues: list[str] = []
    qs = paper.questions
    qdicts = [q.model_dump(mode="json") for q in qs]

    if len(qs) != PAPER_SIZE:
        issues.append(f"paper_size:{len(qs)}_expected_{PAPER_SIZE}")

    db_n = sum(
        1
        for q in qs
        if q.source in ("bank", "database", "db")
        and q.origin not in ("mistake_review", "carry_over")
    )
    gen_n = sum(1 for q in qs if q.source == "generated")
    mistake_n = sum(1 for q in qs if q.origin in ("mistake_review", "carry_over"))
    if gen_n < GENERATED_COUNT:
        issues.append(f"generated_count:{gen_n}_lt_{GENERATED_COUNT}")
    if db_n + mistake_n < DB_COUNT and gen_n + db_n + mistake_n < PAPER_SIZE:
        issues.append(f"db_anchor_low:{db_n}")

    kp_issues, kp_distribution = check_knowledge_point_mix(qdicts, plan)
    issues.extend(kp_issues)

    levels = [q.level for q in qs]
    difficulty_path = levels[:]
    for i in range(1, len(levels)):
        if levels[i] - levels[i - 1] > 2:
            issues.append(f"level_jump_Q{i}_to_Q{i+1}:{levels[i-1]}->{levels[i]}")

    diversity_issues = check_intra_paper_diversity(qdicts)
    issues.extend(diversity_issues)

    ep = error_pattern or infer_error_pattern([], plan.skill_tags)
    targeted = 0
    for q in qs:
        if q.source != "generated":
            continue
        sc = score_error_targeting(q.model_dump(mode="json"), ep)
        meta = q.generation_meta or {}
        if sc >= 80 or meta.get("targets_error_pattern"):
            targeted += 1
    min_t = _min_error_targeted()
    if ep.get("pattern") != "general_practice" and targeted < min_t:
        issues.append(f"error_targeting:{targeted}_lt_{min_t}")

    for i, q in enumerate(qs):
        if len(q.prompt) > 220:
            issues.append(f"stem_too_long_Q{i+1}")
        if len(q.explanation or "") > 500:
            issues.append(f"explanation_too_long_Q{i+1}")

    paper_score = max(0.0, 100.0 - len(issues) * 8.0)
    if not diversity_issues and len(qs) == PAPER_SIZE:
        paper_score = min(100.0, paper_score + 10.0)
    if kp_mix_enabled() and len(kp_distribution) >= 2 and not kp_issues:
        paper_score = min(100.0, paper_score + 5.0)

    recommendation = "accept"
    if paper_score < 60 or any("duplicate_stem" in x for x in issues):
        recommendation = "reject"
    elif paper_score < 85 or diversity_issues or kp_issues:
        recommendation = "revise"

    return {
        "paper_score": round(paper_score, 1),
        "issues": issues,
        "difficulty_path": difficulty_path,
        "recommendation": recommendation,
        "error_targeted_generated": targeted,
        "db_count": db_n,
        "generated_count": gen_n,
        "mistake_count": mistake_n,
        "kp_distribution": kp_distribution,
    }


def try_fix_paper_conflicts(
    paper: ExamPaper,
    issues: list[str],
    *,
    plan: PaperPlan | None = None,
    tools: Any = None,
) -> ExamPaper:
    """Dedupe stems; optionally swap in cluster questions for KP homogeneity."""
    paper = _dedupe_stems(paper, issues)

    if not plan or not tools or not kp_mix_enabled():
        return paper

    kp_bad = any(
        x.startswith("kp_homogeneous") or x.startswith("kp_dominant") for x in issues
    )
    if not kp_bad or not plan.related_knowledge_points:
        return paper

    from swigar_tools.question_normalize import normalize_choices, normalize_correct_answer

    rel = plan.related_knowledge_points[0]
    raw = tools.question_bank.find(
        skill_tags=rel.skill_tags or plan.skill_tags,
        knowledge_point=rel.knowledge_point,
        limit=3,
    )
    if not raw:
        return paper

    replacement = QuestionItem.from_bank_dict(raw[0])
    replacement.source = "generated"
    replacement.choices = normalize_choices(list(replacement.choices))
    replacement.correct_answer = normalize_correct_answer(
        replacement.correct_answer, replacement.choices
    )
    replacement.generation_meta = {"kp_slot": "related_1", "kp_fix_swap": True}

    questions = list(paper.questions)
    for idx in range(len(questions) - 1, -1, -1):
        if questions[idx].source == "generated":
            questions[idx] = replacement
            break
    return paper.model_copy(update={"questions": questions})


def _dedupe_stems(paper: ExamPaper, issues: list[str]) -> ExamPaper:
    if not any("duplicate_stem" in i for i in issues):
        return paper
    seen: set[str] = set()
    kept = []
    for q in paper.questions:
        stem = q.prompt.strip().lower()
        if stem in seen:
            continue
        seen.add(stem)
        kept.append(q)
    if len(kept) == len(paper.questions):
        return paper
    return paper.model_copy(update={"questions": kept})
