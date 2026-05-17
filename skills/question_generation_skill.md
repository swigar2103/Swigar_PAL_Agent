# Question Generation Skill

## Purpose
Generate high-quality English practice questions that are **pedagogically equivalent** to verified database questions but **lexically and structurally different** from them.

Same learning objective does not mean the same sentence.

## Input
- `target_knowledge_point`
- `learner_level`
- `learner_recent_errors` (wrong answer strings from `AnswerStore`)
- `inferred_error_pattern` (from `error_pattern.infer_error_pattern`)
- 4 verified database questions (seeds)
- `target_number = 6`
- `difficulty_range = 1..5`

## Workflow (`QuestionGenerateSkill`)

1. **Analyse source questions** — pattern, distractor logic, common error (not copied stem).
2. **Transformation plan** — map G1–G6 slots to operators T1–T6.
3. **Over-generate** — 18–24 candidates (`SWIGAR_GENERATE_CANDIDATE_COUNT`).
4. **Filter** — lexical + structural + semantic similarity vs seeds; trace `step5b_structural_reject`.
5. **Score** — weighted formula including `learner_error_targeting`; 70–84 → one `revise_candidate_once`.
6. **Intra select** — `select_diverse_candidates` greedy with G1–G6 slot coverage; `step5c_intra_reject` on conflicts.
7. **Difficulty gradient** on final 6.

## Variation slots (G) and KP slots
| Slot | Goal | Typical KP slot |
|------|------|-----------------|
| G1 | basic recognition | primary |
| G2 | short daily context | primary |
| G3 | regular vs irregular contrast | related_1 |
| G4 | short dialogue | related_1 |
| G5 | two-clause sentence | related_2 |
| G6 | mixed review / inference | related_2 |

When `SWIGAR_PAPER_KP_MIX=true`, `kp_slot_plan` assigns each G slot a `knowledge_point` from primary + related list.

## Operators T1–T6
T1 Lexical substitution · T2 Context shift · T3 Syntax shift · T4 Error-pattern preservation · T5 Distractor redesign · T6 Difficulty scaling

## Forbidden
- Only replace names/pronouns (same frame + verb slot)
- Identical stems within the generated batch or full paper
- Surface-clue answers; `goed`/`eated` as correct without teaching contrast

## Output
`QuestionItem` with `generation_meta`: `variation_slot`, `variation_strategy`, `validation_score`, `generated_from`.
