"""Score generated question candidates (0-100)."""

from __future__ import annotations

from typing import Any

from swigar_tools.error_pattern import score_error_targeting
from swigar_tools.knowledge_clusters import normalize_kp_key
from swigar_tools.question_similarity import check_duplicate_against_sources, similarity_report, token_overlap_ratio


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def score_candidate(
    candidate: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    target_knowledge_point: str,
    target_level_min: int,
    target_level_max: int,
    error_pattern: dict[str, Any] | None = None,
    learner_level: int = 2,
    allowed_knowledge_points: list[str] | None = None,
) -> dict[str, Any]:
    failed: list[str] = []
    kp = target_knowledge_point.lower()
    cand_kp = str(candidate.get("knowledge_point") or "").lower()
    stem = str(candidate.get("prompt") or candidate.get("stem") or "")
    tag_blob = " ".join(candidate.get("skill_tags") or []).lower()
    choices = list(candidate.get("choices") or candidate.get("options") or [])
    correct = str(candidate.get("correct_answer") or candidate.get("answer") or "")
    explanation = str(candidate.get("explanation") or "")
    level = int(candidate.get("level") or candidate.get("difficulty") or 2)

    ka = 70.0
    if allowed_knowledge_points:
        allowed_norm = {normalize_kp_key(a) for a in allowed_knowledge_points}
        cand_norm = normalize_kp_key(cand_kp or tag_blob or stem[:40])
        matched = cand_norm in allowed_norm
        if not matched:
            for a in allowed_knowledge_points:
                al = a.lower()
                if al in cand_kp or al in tag_blob or al in stem.lower():
                    matched = True
                    break
        ka = 95.0 if matched else 55.0
        if not matched:
            failed.append("kp_not_in_allowed_cluster")
    elif kp and (kp in cand_kp or kp in stem.lower() or kp in tag_blob):
        ka = 95.0
    elif cand_kp:
        ka = 80.0

    too_sim, reason = check_duplicate_against_sources(candidate, sources)
    nd = 20.0 if too_sim else 95.0
    if too_sim:
        failed.append(reason)
    else:
        max_struct = 0.0
        for src in sources:
            rep = similarity_report(candidate, src)
            max_struct = max(max_struct, float(rep.get("structural") or 0))
        if max_struct >= 0.70:
            nd = max(40.0, 95.0 - max_struct * 50)

    let_score = score_error_targeting(candidate, error_pattern or {})

    dq = 50.0
    if len(choices) >= 3 and correct:
        norms = [c.strip().lower() for c in choices]
        if correct.strip().lower() in norms:
            dq = 85.0
            if len(set(norms)) == len(norms):
                dq = 92.0
        else:
            failed.append("correct_not_in_choices")
            dq = 10.0

    df = 80.0
    if level < target_level_min - 1 or level > target_level_max + 2:
        df = 55.0
    if target_level_min <= level <= target_level_max:
        df = 90.0
    if learner_level <= 2 and len(stem.split()) > 18:
        df = min(df, 60.0)
        failed.append("too_complex_for_level")

    eq = 40.0
    if 10 <= len(explanation) <= 400:
        eq = 85.0
    if len(explanation) < 5:
        failed.append("explanation_too_short")
        eq = 30.0

    gcf = 80.0
    if len(stem) > 220:
        gcf = 55.0
        failed.append("stem_too_long_for_battle")

    final = (
        ka * 0.22
        + nd * 0.20
        + dq * 0.18
        + let_score * 0.15
        + df * 0.12
        + eq * 0.08
        + gcf * 0.05
    )

    decision = "reject"
    if final >= 85 and not too_sim:
        decision = "accept"
    elif final >= 70 and not too_sim:
        decision = "revise"
    if too_sim:
        decision = "reject"

    max_src_overlap = 0.0
    for src in sources:
        max_src_overlap = max(
            max_src_overlap,
            token_overlap_ratio(stem, str(src.get("prompt") or src.get("stem") or "")),
        )

    return {
        "score": round(_clamp(final), 1),
        "failed_reasons": failed,
        "final_decision": decision,
        "similarity_check": {
            "too_similar_to_source": too_sim,
            "reason": reason,
            "max_stem_overlap": round(max_src_overlap, 3),
        },
        "dimension_scores": {
            "knowledge_alignment": ka,
            "non_duplication": nd,
            "distractor_quality": dq,
            "learner_error_targeting": let_score,
            "difficulty_fit": df,
            "explanation_quality": eq,
            "game_context_fit": gcf,
        },
    }
