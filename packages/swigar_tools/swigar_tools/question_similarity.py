"""Lexical, structural, and semantic similarity for question deduplication."""

from __future__ import annotations

import os
import re
from typing import Any

_STOP = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "could should may might must i you he she it we they my your his her its our their "
    "to of in on at for with from by as and or but not".split()
)

_TIME_PATTERNS = re.compile(
    r"\b(yesterday|today|tomorrow|last\s+\w+|next\s+\w+|\d{4}|ago|morning|evening|night|lunch)\b",
    re.I,
)

_CONTEXT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "school": ("school", "class", "teacher", "homework", "student"),
    "meal": ("dinner", "lunch", "breakfast", "eat", "food", "restaurant"),
    "shopping": ("shop", "store", "buy", "bought", "market"),
    "sports": ("game", "play", "team", "ball", "match"),
    "travel": ("trip", "travel", "airport", "hotel", "vacation"),
    "family": ("family", "mother", "father", "brother", "sister", "home"),
}

_IRREGULAR_PAST = frozenset(
    "went ate saw took bought wrote gave made did had left spoke ran came got".split()
)

_VARIATION_SLOTS = ("G1", "G2", "G3", "G4", "G5", "G6")


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOP and len(w) > 1}


def token_overlap_ratio(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    denom = min(len(ta), len(tb))
    return inter / denom if denom else 0.0


def options_overlap(a: list[str], b: list[str]) -> float:
    sa = [frozenset(_tokens(c)) for c in a]
    sb = [frozenset(_tokens(c)) for c in b]
    if not sa or not sb:
        return 0.0
    best = 0.0
    for oa in sa:
        for ob in sb:
            if not oa or not ob:
                continue
            inter = len(set(oa) & set(ob))
            denom = min(len(oa), len(ob))
            if denom:
                best = max(best, inter / denom)
    return best


def extract_blank_target(stem: str) -> str | None:
    m = re.search(r"___\s*([a-z']+)?", stem, re.I)
    if m and m.group(1):
        return m.group(1).lower()
    return None


def time_expressions(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TIME_PATTERNS.finditer(text)}


def structural_frame(stem: str) -> str:
    """Abstract sentence frame: normalize names/pronouns, keep blank slots."""
    s = stem.lower().strip()
    s = re.sub(r"\b(?:tom|mary|john|betty|emma|sarah|james|he|she|i|we|they|my|your|his|her)\b", "SUBJ", s)
    s = re.sub(r"___+", "BLANK", s)
    s = re.sub(r"\s+", " ", s)
    # collapse content words to slots for frame comparison
    parts = s.split()
    frame_parts: list[str] = []
    for p in parts:
        if p in ("BLANK", "SUBJ") or p in _STOP:
            frame_parts.append(p)
        elif re.match(r"^(yesterday|today|last|next|ago)$", p):
            frame_parts.append("TIME")
        else:
            frame_parts.append("W")
    return " ".join(frame_parts)


def structural_overlap(a: str, b: str) -> float:
    fa, fb = structural_frame(a), structural_frame(b)
    if not fa or not fb:
        return 0.0
    ta, tb = set(fa.split()), set(fb.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def target_verb_family(stem: str, correct: str = "") -> str:
    for w in _tokens(stem + " " + correct):
        if w.endswith("ed") or w in _IRREGULAR_PAST:
            return w
    return ""


def infer_context_type(stem: str) -> str:
    low = stem.lower()
    for ctx, kws in _CONTEXT_KEYWORDS.items():
        if any(k in low for k in kws):
            return ctx
    return "general"


def is_surface_tweak_only(source_stem: str, candidate_stem: str) -> bool:
    norm = lambda s: re.sub(r"[^a-z0-9\s]", "", s.lower())
    a, b = norm(source_stem), norm(candidate_stem)
    if a == b:
        return True
    ta, tb = a.split(), b.split()
    if len(ta) == len(tb) and sum(x != y for x, y in zip(ta, tb)) <= 1:
        diff_pairs = [(x, y) for x, y in zip(ta, tb) if x != y]
        if len(diff_pairs) == 1:
            old, _ = diff_pairs[0]
            if old in ("tom", "mary", "john", "betty", "he", "she", "his", "her", "my", "your", "emma"):
                return True
    return False


def _semantic_swap_only(source_stem: str, candidate_stem: str) -> bool:
    """Same frame, high lexical overlap — e.g. went→class vs went→school."""
    struct_ov = structural_overlap(source_stem, candidate_stem)
    lex_ov = token_overlap_ratio(source_stem, candidate_stem)
    return struct_ov >= 0.75 and lex_ov >= 0.35


def similarity_report(
    candidate: dict[str, Any],
    reference: dict[str, Any],
) -> dict[str, Any]:
    c_stem = str(candidate.get("prompt") or candidate.get("stem") or "")
    r_stem = str(reference.get("prompt") or reference.get("stem") or "")
    c_choices = list(candidate.get("choices") or candidate.get("options") or [])
    r_choices = list(reference.get("choices") or reference.get("options") or [])
    c_correct = str(candidate.get("correct_answer") or candidate.get("answer") or "")

    lexical = token_overlap_ratio(c_stem, r_stem)
    structural = structural_overlap(c_stem, r_stem)
    opt_ov = options_overlap(c_choices, r_choices)

    c_frame = structural_frame(c_stem)
    r_frame = structural_frame(r_stem)
    c_verb = target_verb_family(c_stem, c_correct)
    r_verb = target_verb_family(r_stem, str(reference.get("correct_answer") or ""))

    too_similar = False
    reasons: list[str] = []

    if is_surface_tweak_only(r_stem, c_stem):
        too_similar = True
        reasons.append("surface_tweak_only")
    if lexical >= 0.45:
        too_similar = True
        reasons.append(f"lexical_overlap={lexical:.2f}")
    if structural >= 0.82 and lexical >= 0.30:
        too_similar = True
        reasons.append(f"structural_overlap={structural:.2f}")
    if _semantic_swap_only(r_stem, c_stem):
        too_similar = True
        reasons.append("semantic_frame_clone")
    if opt_ov >= 0.70:
        too_similar = True
        reasons.append(f"options_overlap={opt_ov:.2f}")
    if c_frame == r_frame and c_verb and r_verb and c_verb == r_verb:
        too_similar = True
        reasons.append("same_frame_same_verb")
    if c_frame == r_frame and c_verb != r_verb:
        # same frame but different verb — allow if context/distractors differ enough
        if infer_context_type(c_stem) == infer_context_type(r_stem) and opt_ov >= 0.5:
            too_similar = True
            reasons.append("same_frame_same_context")

    return {
        "too_similar": too_similar,
        "reason": ";".join(reasons) if reasons else "ok",
        "lexical": round(lexical, 3),
        "structural": round(structural, 3),
        "options": round(opt_ov, 3),
    }


def check_duplicate_against_sources(
    candidate: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    stem_overlap_max: float = 0.45,
    options_overlap_max: float = 0.70,
) -> tuple[bool, str]:
    """Return (too_similar, reason) vs seed questions."""
    for src in sources:
        rep = similarity_report(candidate, src)
        if rep["too_similar"]:
            return True, str(rep["reason"])
    return False, "ok"


def check_duplicate_against_pool(
    candidate: dict[str, Any],
    pool: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Intra-paper / intra-generated diversity vs already-selected items."""
    c_stem = str(candidate.get("prompt") or candidate.get("stem") or "").strip().lower()
    for item in pool:
        r_stem = str(item.get("prompt") or item.get("stem") or "").strip().lower()
        if c_stem == r_stem:
            return True, "identical_stem"
        rep = similarity_report(candidate, item)
        if rep["too_similar"]:
            return True, f"intra_{rep['reason']}"
    return False, "ok"


def check_intra_paper_diversity(questions: list[dict[str, Any]]) -> list[str]:
    """Validate full paper; return list of issue strings (empty = ok)."""
    issues: list[str] = []
    stems: list[str] = []
    frames: list[str] = []
    verbs: list[str] = []
    contexts: list[str] = []

    for i, q in enumerate(questions):
        stem = str(q.get("prompt") or "")
        stems.append(stem.lower().strip())
        frames.append(structural_frame(stem))
        verbs.append(target_verb_family(stem, str(q.get("correct_answer") or "")))
        contexts.append(infer_context_type(stem))

    for i in range(len(stems)):
        for j in range(i + 1, len(stems)):
            if stems[i] == stems[j]:
                issues.append(f"duplicate_stem_Q{i+1}_Q{j+1}")
            rep = similarity_report(questions[i], questions[j])
            if rep["too_similar"]:
                issues.append(f"too_similar_Q{i+1}_Q{j+1}:{rep['reason']}")

    from collections import Counter

    frame_counts = Counter(frames)
    for fr, cnt in frame_counts.items():
        if fr and cnt > 1:
            issues.append(f"repeated_frame:{fr}x{cnt}")

    verb_counts = Counter(v for v in verbs if v)
    for v, cnt in verb_counts.items():
        if cnt > 2:
            issues.append(f"repeated_verb:{v}x{cnt}")

    ctx_counts = Counter(contexts)
    for ctx, cnt in ctx_counts.items():
        if ctx != "general" and cnt > 2:
            issues.append(f"repeated_context:{ctx}x{cnt}")

    return issues


def _kp_counts(selected: list[dict[str, Any]]) -> dict[str, int]:
    from swigar_tools.knowledge_clusters import question_kp_key

    out: dict[str, int] = {}
    for s in selected:
        k = question_kp_key(s)
        out[k] = out.get(k, 0) + 1
    return out


def _kp_mix_ok(
    selected: list[dict[str, Any]],
    cand: dict[str, Any],
    *,
    min_distinct_kp: int,
    max_per_kp: int,
    count: int,
) -> bool:
    if min_distinct_kp <= 1:
        return True
    from swigar_tools.knowledge_clusters import question_kp_key

    counts = _kp_counts(selected)
    nk = question_kp_key(cand)
    new_count = counts.get(nk, 0) + 1
    if new_count > max_per_kp:
        return False
    future = list(selected) + [cand]
    if len(future) >= count:
        distinct = len(_kp_counts(future))
        if distinct < min_distinct_kp:
            return False
    return True


def select_diverse_candidates(
    scored: list[tuple[float, dict[str, Any], dict[str, Any]]],
    sources: list[dict[str, Any]],
    count: int,
    *,
    slots: tuple[str, ...] = _VARIATION_SLOTS,
    min_distinct_kp: int = 0,
    max_per_kp: int = 4,
) -> list[dict[str, Any]]:
    """Greedy select top candidates with intra-generated diversity and slot coverage."""
    selected: list[dict[str, Any]] = []
    used_slots: set[str] = set()

    for _, cand, _ in sorted(scored, key=lambda x: x[0], reverse=True):
        if len(selected) >= count:
            break
        too_src, _ = check_duplicate_against_sources(cand, sources)
        if too_src:
            continue
        too_intra, _ = check_duplicate_against_pool(cand, selected)
        if too_intra:
            continue
        if not _kp_mix_ok(
            selected, cand, min_distinct_kp=min_distinct_kp, max_per_kp=max_per_kp, count=count
        ):
            continue
        slot = str(cand.get("variation_slot") or cand.get("slot") or "")
        if slot and slot in used_slots and len(used_slots) < len(slots):
            continue
        selected.append(cand)
        if slot:
            used_slots.add(slot)

    # fill remaining without slot constraint
    if len(selected) < count:
        for _, cand, _ in sorted(scored, key=lambda x: x[0], reverse=True):
            if len(selected) >= count:
                break
            c_stem = str(cand.get("prompt") or cand.get("stem") or "").strip().lower()
            if any(
                c_stem == str(s.get("prompt") or s.get("stem") or "").strip().lower()
                for s in selected
            ):
                continue
            too_src, _ = check_duplicate_against_sources(cand, sources)
            too_intra, _ = check_duplicate_against_pool(cand, selected)
            if too_src or too_intra:
                continue
            if not _kp_mix_ok(
                selected, cand, min_distinct_kp=min_distinct_kp, max_per_kp=max_per_kp, count=count
            ):
                continue
            selected.append(cand)

    # boost KP diversity if still homogeneous
    if min_distinct_kp > 1 and len(_kp_counts(selected)) < min_distinct_kp:
        have = _kp_counts(selected)
        for _, cand, _ in sorted(scored, key=lambda x: x[0], reverse=True):
            from swigar_tools.knowledge_clusters import question_kp_key

            nk = question_kp_key(cand)
            if nk in have:
                continue
            c_stem = str(cand.get("prompt") or cand.get("stem") or "").strip().lower()
            if any(
                c_stem == str(s.get("prompt") or s.get("stem") or "").strip().lower()
                for s in selected
            ):
                continue
            too_intra, _ = check_duplicate_against_pool(cand, selected)
            if too_intra:
                continue
            if len(selected) >= count and selected:
                selected[-1] = cand
            else:
                selected.append(cand)
            have[nk] = have.get(nk, 0) + 1
            if len(have) >= min_distinct_kp:
                break

    return selected[:count]
