"""Plan next exam paper: knowledge point and difficulty band."""

from __future__ import annotations

import json
from typing import Any, Callable

from swigar_core.models import LearnerProfile, PaperPlan, RelatedKnowledgeEntry
from swigar_tools.knowledge_clusters import apply_knowledge_mix, rotate_plan_if_mastered
from swigar_tools.llm_prompts import PAPER_PLAN_SYSTEM


class PaperPlanSkill:
    def __init__(self, tools):
        self.tools = tools

    async def run(
        self,
        profile: LearnerProfile,
        last_accuracy: float | None = None,
        trace: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> tuple[PaperPlan, dict[str, Any]]:
        if self.tools.llm.is_configured:
            data = await self._run_llm(profile, last_accuracy, trace)
            if data:
                plan = rotate_plan_if_mastered(
                    apply_knowledge_mix(self._from_llm(data)), profile
                )
                return plan, {"source": "llm"}
        plan = rotate_plan_if_mastered(
            apply_knowledge_mix(self._run_rules(profile, last_accuracy)), profile
        )
        return plan, {"source": "rules"}

    async def _run_llm(self, profile, last_accuracy, trace):
        payload = {
            "profile": profile.model_dump(mode="json"),
            "last_paper_accuracy": last_accuracy,
        }

        def _t(step: str, d: dict) -> None:
            if trace:
                trace(step, {**d, "skill": "paper_plan"})

        return await self.tools.llm.complete_json_async(
            system=PAPER_PLAN_SYSTEM,
            user=json.dumps(payload, ensure_ascii=False, default=str),
            trace=_t,
        )

    def _parse_related(self, raw: Any) -> list[RelatedKnowledgeEntry]:
        if not raw:
            return []
        items = raw if isinstance(raw, list) else []
        out: list[RelatedKnowledgeEntry] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            tags = item.get("skill_tags") or []
            if isinstance(tags, str):
                tags = [tags]
            out.append(
                RelatedKnowledgeEntry(
                    knowledge_point=str(item.get("knowledge_point", "")),
                    skill_tags=[str(t) for t in tags],
                    quota=max(1, int(item.get("quota", 1))),
                )
            )
        return [r for r in out if r.knowledge_point]

    def _from_llm(self, data: dict[str, Any]) -> PaperPlan:
        tags = data.get("skill_tags") or []
        if isinstance(tags, str):
            tags = [tags]
        kp = str(
            data.get("primary_knowledge_point")
            or data.get("knowledge_point", "grammar.general")
        )
        cluster_id = data.get("knowledge_cluster_id")
        if cluster_id is not None:
            cluster_id = str(cluster_id)
        return PaperPlan(
            knowledge_point=kp,
            skill_tags=[str(t) for t in tags],
            target_level_min=max(1, min(5, int(data.get("target_level_min", 1)))),
            target_level_max=max(1, min(5, int(data.get("target_level_max", 3)))),
            strategy=str(data.get("strategy", "practice")),
            rationale=str(data.get("rationale", "")),
            next_focus=str(data.get("next_focus", "")),
            related_knowledge_points=self._parse_related(data.get("related_knowledge_points")),
            knowledge_cluster_id=cluster_id,
        )

    def _run_rules(self, profile: LearnerProfile, last_accuracy: float | None) -> PaperPlan:
        acc = last_accuracy if last_accuracy is not None else profile.recent_accuracy
        weak = profile.weak_points[0] if profile.weak_points else "grammar.present_perfect"
        kp = weak.replace("grammar.", "").replace("_", " ")
        if acc >= 0.8:
            lvl_min, lvl_max, strategy = 2, 4, "advance"
        elif acc >= 0.5:
            lvl_min, lvl_max, strategy = profile.difficulty_preference, profile.difficulty_preference + 1, "consolidate"
        else:
            lvl_min, lvl_max, strategy = 1, 2, "remediate"
        return PaperPlan(
            knowledge_point=kp,
            skill_tags=[weak] if weak.startswith("grammar.") else [f"grammar.{weak}"],
            target_level_min=lvl_min,
            target_level_max=min(5, lvl_max),
            strategy=strategy,
            rationale=f"Rule plan from accuracy={acc:.0%}",
        )
