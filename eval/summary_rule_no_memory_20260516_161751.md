# Swigar eval summary (2026-05-16T16:17:51.653087+00:00)
API: http://127.0.0.1:8001
Variant: rule_no_memory
Repeats per scenario: 3

## S1_session_start
- orchestrator_triggered: 1/3
- latency_ms mean=14531.2 p95~=14531.2
- action_types: assign_task
- memory_refs mean=0.00
- errors: 2

## S2_mistake_streak
- orchestrator_triggered: 0/3
- memory_refs mean=0.00
- errors: 3

## S3_task_done
- orchestrator_triggered: 0/3
- memory_refs mean=0.00
- errors: 3

## S4_low_engage
- orchestrator_triggered: 0/3
- memory_refs mean=0.00
- errors: 3

## S5_mixed_answers
- orchestrator_triggered: 0/3
- memory_refs mean=0.00
- errors: 3
