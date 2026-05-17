# Swigar eval summary (2026-05-16T16:18:31.694671+00:00)
API: http://127.0.0.1:8001
Variant: rule_no_memory
Repeats per scenario: 5

## S1_session_start
- orchestrator_triggered: 5/5
- latency_ms mean=42.9 p95~=43.0
- action_types: assign_task
- memory_refs mean=0.00

## S2_mistake_streak
- orchestrator_triggered: 5/5
- latency_ms mean=41.3 p95~=41.2
- action_types: npc_dialogue
- memory_refs mean=0.00

## S3_task_done
- orchestrator_triggered: 5/5
- latency_ms mean=48.2 p95~=51.3
- action_types: assign_task
- memory_refs mean=0.00

## S4_low_engage
- orchestrator_triggered: 5/5
- latency_ms mean=41.3 p95~=41.1
- action_types: assign_task
- memory_refs mean=0.00

## S5_mixed_answers
- orchestrator_triggered: 5/5
- latency_ms mean=42.0 p95~=42.6
- action_types: assign_task
- memory_refs mean=0.00
