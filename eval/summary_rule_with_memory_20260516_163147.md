# Swigar eval summary (2026-05-16T16:31:47.825315+00:00)
API: http://127.0.0.1:8001
Variant: rule_with_memory
Repeats per scenario: 3

## S1_session_start
- orchestrator_triggered: 3/3
- latency_ms mean=33978.8 p95~=34697.2
- action_types: assign_task
- memory_refs mean=0.00

## S2_mistake_streak
- orchestrator_triggered: 3/3
- latency_ms mean=25204.9 p95~=25949.7
- action_types: npc_dialogue
- memory_refs mean=0.00

## S3_task_done
- orchestrator_triggered: 3/3
- latency_ms mean=37800.8 p95~=38969.8
- action_types: assign_task
- memory_refs mean=0.00

## S4_low_engage
- orchestrator_triggered: 3/3
- latency_ms mean=41900.0 p95~=42569.0
- action_types: assign_task
- memory_refs mean=0.00

## S5_mixed_answers
- orchestrator_triggered: 3/3
- latency_ms mean=44350.1 p95~=43489.4
- action_types: assign_task
- memory_refs mean=0.00
