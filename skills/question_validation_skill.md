# Question Validation Skill

## Purpose
Validate generated items before assembly: knowledge alignment, multi-level non-duplication, answer leakage, option homogeneity, level fit, learner error targeting.

## Scoring (0–100)
```
final_score =
  knowledge_alignment * 0.22
+ non_duplication * 0.20
+ distractor_quality * 0.18
+ learner_error_targeting * 0.15
+ difficulty_fit * 0.12
+ explanation_quality * 0.08
+ game_context_fit * 0.05
```

- **≥85**: accept  
- **70–84**: revise at generation stage; validate accepts if ≥78 after meta check  
- **&lt;70**: reject  

`non_duplication` uses lexical + structural overlap from `similarity_report`.

## Rules (`question_validation_rules.py`)
- Answer leakage: correct form appears in stem
- Option category: verb forms homogeneous (-ed/-ing outliers flagged)
- Level fit: A1–B1 sentence length vs `learner_level`
- Duplicate vs seed: structural frame + verb family

## Implementation
`QuestionValidateSkill` in `packages/swigar_skills/swigar_skills/question_validate.py`.
