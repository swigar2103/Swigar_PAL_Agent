# Paper Assembly and Validation Skill

## Purpose
Ensure each 10-question exam paper is pedagogically coherent, diverse, difficulty-graded, and playable in the dungeon RPG — not merely a bag of individually acceptable items.

## Input
- `ExamPaper` (10 questions)
- `PaperPlan` (knowledge point, levels, strategy)
- `inferred_error_pattern` from recent wrong answers

## Structure (default interleave)
| Slot | Source | Target level |
|------|--------|--------------|
| Q1 | DB | L1 |
| Q2 | Generated | L1 |
| Q3 | DB | L2 |
| Q4 | Generated | L2 |
| Q5 | Generated | L3 |
| Q6 | DB or mistake review | L3 |
| Q7–Q8 | Generated | L4 |
| Q9 | DB | L5 |
| Q10 | Generated | L5 |

Mistake review items replace DB slots only (max 2).

## Validation criteria
1. Exactly 10 questions; ≥6 generated; ≥4 DB anchors (mistakes count as DB slots).
2. **Knowledge point mix** (when `SWIGAR_PAPER_KP_MIX=true`): ≥2 distinct KPs within the same grammar cluster; no single KP &gt;60% of items; all items in allowed cluster set.
3. Difficulty path: no jump &gt;2 levels between adjacent questions.
4. Intra-paper diversity: no duplicate stems; sentence frame ≤1; same verb stem ≤2; same context ≤2.
5. Error targeting: when pattern is irregular -ed overgeneralisation, ≥3 generated items score high on learner_error_targeting.
6. Game fit: stem ≤220 chars; explanation not excessively long.

## Output (JSON shape)
```json
{
  "paper_score": 88.0,
  "issues": [],
  "difficulty_path": [1, 1, 2, 2, 3, 3, 4, 4, 5, 5],
  "recommendation": "accept",
  "error_targeted_generated": 4,
  "kp_distribution": {"past simple": 4, "past perfect": 3}
}
```

- **accept**: paper ready  
- **revise**: dedupe / light reorder (`try_fix_paper_conflicts`)  
- **reject**: downgrade with `validation_warnings` on trace (do not block learner)

## Implementation
`validate_paper_assembly` in `packages/swigar_skills/swigar_skills/paper_assembly_validate.py`; called from `PaperOrchestrator` after `build_exam_paper`.
