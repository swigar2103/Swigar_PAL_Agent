"""Adapt learner profile after paper completion."""

from __future__ import annotations

from swigar_core.models import ExamPaper, LearnerProfile


class NextPaperAdaptSkill:
    def update_profile_from_paper(self, profile: LearnerProfile, paper: ExamPaper, records: list[dict]) -> LearnerProfile:
        correct = sum(1 for r in records if r.get("is_correct"))
        total = len(records) or 1
        acc = correct / total
        kp = paper.knowledge_point or "general"

        kp_buckets: dict[str, list[bool]] = {}
        for r in records:
            idx = int(r.get("question_index", -1))
            q_kp = kp
            if 0 <= idx < len(paper.questions):
                q_kp = paper.questions[idx].knowledge_point or kp
            kp_buckets.setdefault(q_kp, []).append(bool(r.get("is_correct")))
        for q_kp, outcomes in kp_buckets.items():
            if not outcomes:
                continue
            profile.accuracy_by_kp[q_kp] = sum(outcomes) / len(outcomes)

        profile.accuracy_by_kp[kp] = acc
        if acc < 0.5 and kp not in profile.weak_points:
            profile.weak_points = (profile.weak_points + [kp])[-10:]
        elif acc >= 0.8 and kp in profile.weak_points:
            profile.weak_points = [w for w in profile.weak_points if w != kp]
        for q_kp, outcomes in kp_buckets.items():
            sub_acc = sum(outcomes) / len(outcomes)
            if sub_acc < 0.5 and q_kp not in profile.weak_points:
                profile.weak_points = (profile.weak_points + [q_kp])[-10:]
            elif sub_acc >= 0.8 and q_kp in profile.weak_points:
                profile.weak_points = [w for w in profile.weak_points if w != q_kp]
        times = [r.get("time_spent_ms", 0) for r in records if r.get("time_spent_ms")]
        if times:
            profile.avg_response_ms = sum(times) / len(times)
        profile.papers_completed += 1
        profile.last_paper_summary = (
            f"卷 {paper.paper_id[:8]}… 知识点「{kp}」正确率 {acc:.0%}，策略 {paper.strategy}"
        )
        if acc >= 0.8:
            profile.difficulty_preference = min(5, profile.difficulty_preference + 1)
            profile.current_level = min(5, profile.current_level + 1)
        elif acc < 0.4:
            profile.difficulty_preference = max(1, profile.difficulty_preference - 1)
        return profile
