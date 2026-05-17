"""Grammar knowledge clusters for intra-paper related KP mixing."""

from __future__ import annotations

import os
import re
from typing import Any

from swigar_core.models import PaperPlan, RelatedKnowledgeEntry


def kp_mix_enabled() -> bool:
    return os.environ.get("SWIGAR_PAPER_KP_MIX", "true").lower() in ("1", "true", "yes")


def min_distinct_kp() -> int:
    return max(2, min(5, int(os.environ.get("SWIGAR_MIN_DISTINCT_KP", "2"))))


def max_same_kp_ratio() -> float:
    return max(0.4, min(1.0, float(os.environ.get("SWIGAR_MAX_SAME_KP_RATIO", "0.6"))))


def normalize_kp_key(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").lower().strip())
    s = re.sub(r"[^\w\s\u4e00-\u9fff]", "", s)
    return s[:64] if s else "general"


_CLUSTER_MEMBER = dict[str, Any]

GRAMMAR_CLUSTERS: dict[str, dict[str, Any]] = {
    "past_tenses": {
        "name": "Past tenses",
        "members": [
            {
                "knowledge_point": "past simple",
                "skill_tags": ["grammar.past_simple"],
                "keywords": ["past_simple", "past simple", "一般过去", "过去式", "不规则动词过去"],
            },
            {
                "knowledge_point": "past continuous",
                "skill_tags": ["grammar.past_continuous"],
                "keywords": ["past_continuous", "past continuous", "过去进行"],
            },
            {
                "knowledge_point": "past perfect",
                "skill_tags": ["grammar.past_perfect"],
                "keywords": ["past_perfect", "past perfect", "过去完成"],
            },
            {
                "knowledge_point": "irregular past",
                "skill_tags": ["grammar.irregular_past"],
                "keywords": ["irregular", "不规则", "went", "不规则动词"],
            },
        ],
    },
    "present_tenses": {
        "name": "Present tenses",
        "members": [
            {
                "knowledge_point": "present simple",
                "skill_tags": ["grammar.present_simple"],
                "keywords": ["present_simple", "present simple", "一般现在", "every day", "usually"],
            },
            {
                "knowledge_point": "present continuous",
                "skill_tags": ["grammar.present_continuous"],
                "keywords": [
                    "present_continuous",
                    "present continuous",
                    "现在进行",
                    "进行时",
                    "be doing",
                ],
            },
            {
                "knowledge_point": "present perfect",
                "skill_tags": ["grammar.present_perfect"],
                "keywords": ["present_perfect", "present perfect", "现在完成", "have done"],
            },
        ],
    },
    "perfect_aspect": {
        "name": "Perfect aspect",
        "members": [
            {
                "knowledge_point": "present perfect",
                "skill_tags": ["grammar.present_perfect"],
                "keywords": ["present_perfect", "present perfect", "现在完成"],
            },
            {
                "knowledge_point": "past perfect",
                "skill_tags": ["grammar.past_perfect"],
                "keywords": ["past_perfect", "past perfect", "过去完成"],
            },
        ],
    },
    "modals": {
        "name": "Modal verbs",
        "members": [
            {
                "knowledge_point": "modal verbs",
                "skill_tags": ["grammar.modal_verbs"],
                "keywords": ["modal", "情态", "can", "could", "should", "must"],
            },
            {
                "knowledge_point": "past modals",
                "skill_tags": ["grammar.past_modals"],
                "keywords": ["couldn't", "would", "might", "past modal"],
            },
        ],
    },
}


def _text_blob(tag_or_kp: str) -> str:
    return (tag_or_kp or "").lower().replace("_", " ")


def _member_matches(member: _CLUSTER_MEMBER, text: str) -> bool:
    blob = _text_blob(text)
    for kw in member.get("keywords") or []:
        if _text_blob(kw) in blob or blob in _text_blob(kw):
            return True
    kp = _text_blob(str(member.get("knowledge_point", "")))
    if kp and (kp in blob or blob in kp):
        return True
    for tag in member.get("skill_tags") or []:
        if _text_blob(tag) in blob or blob in _text_blob(tag):
            return True
    return False


def resolve_cluster(tag_or_kp: str) -> str | None:
    if not tag_or_kp:
        return None
    for cluster_id, cluster in GRAMMAR_CLUSTERS.items():
        for member in cluster.get("members") or []:
            if _member_matches(member, tag_or_kp):
                return cluster_id
    return None


def resolve_cluster_for_plan(primary_kp: str, skill_tags: list[str]) -> str | None:
    for tag in skill_tags:
        cid = resolve_cluster(tag)
        if cid:
            return cid
    return resolve_cluster(primary_kp)


def related_knowledge_points(
    primary_kp: str,
    primary_tags: list[str],
    *,
    count: int = 2,
) -> list[RelatedKnowledgeEntry]:
    """Pick up to `count` related KPs from the same cluster, excluding primary."""
    cluster_id = resolve_cluster_for_plan(primary_kp, primary_tags)
    if not cluster_id:
        return []

    primary_norm = normalize_kp_key(primary_kp)
    primary_blobs = {_text_blob(primary_kp)} | {_text_blob(t) for t in primary_tags}
    members = GRAMMAR_CLUSTERS[cluster_id].get("members") or []
    out: list[RelatedKnowledgeEntry] = []

    for member in members:
        kp = str(member.get("knowledge_point", ""))
        tags = [str(t) for t in (member.get("skill_tags") or [])]
        kn = normalize_kp_key(kp)
        if kn == primary_norm:
            continue
        if any(_member_matches(member, b) for b in primary_blobs):
            continue
        out.append(
            RelatedKnowledgeEntry(
                knowledge_point=kp,
                skill_tags=tags,
                quota=1,
            )
        )
        if len(out) >= count:
            break
    return out


def expand_allowed_tags(plan: PaperPlan) -> list[str]:
    tags: set[str] = set(plan.skill_tags or [])
    cluster_id = plan.knowledge_cluster_id or resolve_cluster_for_plan(
        plan.knowledge_point, plan.skill_tags
    )
    if cluster_id and cluster_id in GRAMMAR_CLUSTERS:
        for member in GRAMMAR_CLUSTERS[cluster_id].get("members") or []:
            tags.update(member.get("skill_tags") or [])
    for rel in plan.related_knowledge_points:
        tags.update(rel.skill_tags)
    return list(tags)


def allowed_knowledge_points(plan: PaperPlan) -> list[str]:
    kps = [plan.knowledge_point]
    for rel in plan.related_knowledge_points:
        if rel.knowledge_point:
            kps.append(rel.knowledge_point)
    if plan.knowledge_cluster_id and plan.knowledge_cluster_id in GRAMMAR_CLUSTERS:
        for member in GRAMMAR_CLUSTERS[plan.knowledge_cluster_id].get("members") or []:
            kp = member.get("knowledge_point")
            if kp:
                kps.append(str(kp))
    seen: set[str] = set()
    out: list[str] = []
    for kp in kps:
        nk = normalize_kp_key(kp)
        if nk not in seen:
            seen.add(nk)
            out.append(kp)
    return out


def kp_slot_plan_for_generation(plan: PaperPlan) -> list[dict[str, str]]:
    """Map G1–G6 to primary / related KP slots."""
    related = list(plan.related_knowledge_points)
    r0 = related[0].knowledge_point if len(related) > 0 else plan.knowledge_point
    r1 = related[1].knowledge_point if len(related) > 1 else r0
    slots = ["G1", "G2", "G3", "G4", "G5", "G6"]
    kps = [
        plan.knowledge_point,
        plan.knowledge_point,
        r0,
        r0,
        r1,
        r1,
    ]
    return [{"slot": s, "knowledge_point": kps[i]} for i, s in enumerate(slots)]


def retrieve_quotas(plan: PaperPlan) -> list[tuple[str, RelatedKnowledgeEntry | None, int]]:
    """Return (kp_slot_label, entry_or_none_for_primary, quota) summing to DB_COUNT."""
    from swigar_tools.paper_builder import DB_COUNT

    related = list(plan.related_knowledge_points)
    if not kp_mix_enabled() or not related:
        return [("primary", None, DB_COUNT)]

    if len(related) >= 2:
        quotas = [("primary", None, 2), ("related_1", related[0], 1), ("related_2", related[1], 1)]
    else:
        quotas = [("primary", None, 3), ("related_1", related[0], 1)]
    total = sum(q for _, _, q in quotas)
    if total < DB_COUNT:
        quotas[0] = (quotas[0][0], quotas[0][1], quotas[0][2] + (DB_COUNT - total))
    return quotas


def kp_mastered_threshold() -> float:
    return max(0.5, min(1.0, float(os.environ.get("SWIGAR_KP_MASTERED_THRESHOLD", "0.8"))))


def _kp_accuracy(profile: Any, kp: str) -> float | None:
    acc_map = getattr(profile, "accuracy_by_kp", None) or {}
    if not isinstance(acc_map, dict):
        return None
    kn = normalize_kp_key(kp)
    for key, val in acc_map.items():
        if normalize_kp_key(str(key)) == kn:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
    return None


def cluster_should_rotate(profile: Any, cluster_id: str) -> bool:
    """True when most members in cluster are at or above mastery threshold."""
    if not cluster_id or cluster_id not in GRAMMAR_CLUSTERS:
        return False
    threshold = kp_mastered_threshold()
    members = GRAMMAR_CLUSTERS[cluster_id].get("members") or []
    if not members:
        return False
    scored = 0
    mastered = 0
    for member in members:
        kp = str(member.get("knowledge_point", ""))
        acc = _kp_accuracy(profile, kp)
        if acc is None:
            continue
        scored += 1
        if acc >= threshold:
            mastered += 1
    if scored == 0:
        return False
    return mastered / scored >= 0.5


def pick_alternate_cluster(profile: Any, avoid_cluster_id: str | None) -> str | None:
    """Pick grammar cluster with lowest average KP accuracy (prefer unseen)."""
    weak = list(getattr(profile, "weak_points", None) or [])
    best_id: str | None = None
    best_score = float("inf")

    for cluster_id, cluster in GRAMMAR_CLUSTERS.items():
        if cluster_id == avoid_cluster_id:
            continue
        members = cluster.get("members") or []
        if not members:
            continue
        accs: list[float] = []
        weak_hit = False
        for member in members:
            kp = str(member.get("knowledge_point", ""))
            tags = [str(t) for t in (member.get("skill_tags") or [])]
            acc = _kp_accuracy(profile, kp)
            if acc is not None:
                accs.append(acc)
            for w in weak:
                if _member_matches(member, w) or normalize_kp_key(kp) == normalize_kp_key(w):
                    weak_hit = True
                    break
        if weak_hit:
            score = -1.0
        elif accs:
            score = sum(accs) / len(accs)
        else:
            score = 0.5
        if score < best_score:
            best_score = score
            best_id = cluster_id
    return best_id


def primary_member_for_cluster(cluster_id: str, profile: Any) -> tuple[str, list[str]]:
    members = GRAMMAR_CLUSTERS.get(cluster_id, {}).get("members") or []
    if not members:
        return "grammar.general", ["grammar.general"]
    weak = list(getattr(profile, "weak_points", None) or [])
    for w in weak:
        for member in members:
            if _member_matches(member, w):
                tags = [str(t) for t in (member.get("skill_tags") or [])]
                kp = str(member.get("knowledge_point", "grammar.general"))
                return kp, tags or [w]
    ranked = sorted(
        members,
        key=lambda m: _kp_accuracy(profile, str(m.get("knowledge_point", ""))) or 0.5,
    )
    member = ranked[0]
    tags = [str(t) for t in (member.get("skill_tags") or [])]
    kp = str(member.get("knowledge_point", "grammar.general"))
    return kp, tags or ["grammar.general"]


def rotate_plan_if_mastered(plan: PaperPlan, profile: Any) -> PaperPlan:
    """When current cluster is mastered, switch primary KP to another grammar cluster."""
    cid = plan.knowledge_cluster_id or resolve_cluster_for_plan(
        plan.knowledge_point, plan.skill_tags
    )
    if not cid or not cluster_should_rotate(profile, cid):
        return plan
    alt = pick_alternate_cluster(profile, cid)
    if not alt or alt == cid:
        return plan
    kp, tags = primary_member_for_cluster(alt, profile)
    note = f" | rotated_cluster:{cid}->{alt}"
    return plan.model_copy(
        update={
            "knowledge_point": kp,
            "skill_tags": tags,
            "knowledge_cluster_id": alt,
            "related_knowledge_points": [],
            "rationale": (plan.rationale or "") + note,
        }
    )


def apply_knowledge_mix(plan: PaperPlan) -> PaperPlan:
    """Fill cluster id and related KPs when mixing is enabled."""
    if not kp_mix_enabled():
        return plan
    cluster_id = resolve_cluster_for_plan(plan.knowledge_point, plan.skill_tags)
    related = list(plan.related_knowledge_points)
    if not related:
        related = related_knowledge_points(plan.knowledge_point, plan.skill_tags, count=2)
    return plan.model_copy(
        update={
            "knowledge_cluster_id": cluster_id,
            "related_knowledge_points": related,
        }
    )


def question_kp_key(q: dict[str, Any]) -> str:
    kp = str(q.get("knowledge_point") or "")
    if kp:
        return normalize_kp_key(kp)
    tags = q.get("skill_tags") or []
    if tags:
        return normalize_kp_key(str(tags[0]))
    return normalize_kp_key(str(q.get("prompt", ""))[:40])


def check_knowledge_point_mix(
    questions: list[dict[str, Any]],
    plan: PaperPlan,
) -> tuple[list[str], dict[str, int]]:
    """Return (issues, kp_distribution)."""
    if not kp_mix_enabled():
        return [], {}

    issues: list[str] = []
    allowed = {normalize_kp_key(k) for k in allowed_knowledge_points(plan)}
    allowed_blobs = [_text_blob(k) for k in allowed_knowledge_points(plan)]

    dist: dict[str, int] = {}
    for q in questions:
        key = question_kp_key(q)
        dist[key] = dist.get(key, 0) + 1
        if allowed:
            kp_raw = str(q.get("knowledge_point") or "").lower()
            tag_blob = " ".join(q.get("skill_tags") or []).lower()
            ok = key in allowed
            if not ok:
                for ab in allowed_blobs:
                    if ab and (ab in kp_raw or ab in tag_blob or ab in key):
                        ok = True
                        break
            if not ok and key != "general":
                issues.append(f"kp_out_of_cluster:{key}")

    n = len(questions) or 1
    distinct = len(dist)
    min_d = min_distinct_kp()
    if distinct < min_d:
        issues.append(f"kp_homogeneous:distinct_{distinct}_lt_{min_d}")

    max_ratio = max_same_kp_ratio()
    max_allowed = max(1, int(n * max_ratio + 0.5))
    for kp, cnt in dist.items():
        if cnt > max_allowed:
            issues.append(f"kp_dominant:{kp}x{cnt}_max_{max_allowed}")

    return issues, dist
