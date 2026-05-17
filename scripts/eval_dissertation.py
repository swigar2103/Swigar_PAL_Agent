#!/usr/bin/env python3
"""
Dissertation evaluation harness for Swigar PAL agent.
Runs scripted scenarios against a running API (or starts requests in-process style via httpx).

Usage:
  uvicorn swigar_api.main:app --port 8000   # terminal 1
  python scripts/eval_dissertation.py         # terminal 2

Outputs CSV + PNG under eval/
"""

from __future__ import annotations

import csv
import json
import os
import statistics
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

_REPO = Path(__file__).resolve().parents[1]
_EVAL_DB = _REPO / "eval" / "eval_swigar.db"
# Force eval SQLite: repository .env may point at remote Postgres and hang init_db.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_EVAL_DB.as_posix()}"
os.environ["SWIGAR_QUESTION_BANK_SOURCE"] = "builtin"


def _apply_eval_env() -> None:
    """Re-assert eval DB after swigar_api.config loads .env overrides."""
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_EVAL_DB.as_posix()}"
    try:
        from swigar_api.config import settings

        settings.database_url = os.environ["DATABASE_URL"]
    except ImportError:
        pass

API_BASE = os.environ.get("SWIGAR_EVAL_API", "http://127.0.0.1:8000").rstrip("/")
EVAL_MODE = os.environ.get("SWIGAR_EVAL_MODE", "local")  # local | http
REPEATS = int(os.environ.get("SWIGAR_EVAL_REPEATS", "5"))
OUT_DIR = _REPO / "eval"
VALID_ACTIONS = {
    "assign_task",
    "npc_dialogue",
    "dungeon_quiz",
    "feedback_reward",
    "hint",
    "difficulty_adjust",
}


@dataclass
class RunRow:
    scenario: str
    variant: str
    repeat: int
    orchestrator_triggered: bool
    action_type: str
    latency_ms: float
    memory_refs_count: int
    narrative_len: int
    error: str = ""


class EventClient:
    def post_event(self, event: dict) -> dict:
        raise NotImplementedError


class HttpxEventClient(EventClient):
    def __init__(self) -> None:
        self._client = httpx.Client(trust_env=False, timeout=180.0)

    def post_event(self, event: dict) -> dict:
        t0 = time.perf_counter()
        r = self._client.post(f"{API_BASE}/v1/events", json=event)
        latency_ms = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        body = r.json()
        result = body.get("results", [{}])[0]
        decision = result.get("decision") or {}
        return {
            "latency_ms": latency_ms,
            "orchestrator_triggered": bool(result.get("orchestrator_triggered")),
            "decision": decision,
        }

    def health(self) -> dict:
        r = self._client.get(f"{API_BASE}/health")
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._client.close()


class LocalEventClient(EventClient):
    """In-process async ASGI client (uses eval SQLite DB)."""

    def __init__(self) -> None:
        import asyncio

        from httpx import ASGITransport, AsyncClient

        _apply_eval_env()
        from swigar_api.db import init_db
        from swigar_api.main import app

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(init_db())
        transport = ASGITransport(app=app)
        self._client = AsyncClient(transport=transport, base_url="http://eval.local", timeout=180.0)
        self._loop.run_until_complete(self._client.__aenter__())

    def post_event(self, event: dict) -> dict:
        t0 = time.perf_counter()
        r = self._loop.run_until_complete(self._client.post("/v1/events", json=event))
        latency_ms = (time.perf_counter() - t0) * 1000
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
        body = r.json()
        result = body.get("results", [{}])[0]
        decision = result.get("decision") or {}
        return {
            "latency_ms": latency_ms,
            "orchestrator_triggered": bool(result.get("orchestrator_triggered")),
            "decision": decision,
        }

    def health(self) -> dict:
        r = self._loop.run_until_complete(self._client.get("/health"))
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._loop.run_until_complete(self._client.__aexit__(None, None, None))
        self._loop.close()


def _learner_id(scenario: str, variant: str, repeat: int) -> str:
    return f"eval_{scenario}_{variant}_{repeat}_{uuid.uuid4().hex[:8]}"


def _base_event(learner_id: str, session_id: str, event_type: str, payload: dict | None = None) -> dict:
    return {
        "type": event_type,
        "learner_id": learner_id,
        "session_id": session_id,
        "game_context": {
            "map_id": "tactical_duel",
            "room_id": "eval_lab",
            "npc_id": "mentor",
            "quest_id": "dissertation_eval",
        },
        "payload": payload or {},
    }


def scenario_s1_session_start(client: EventClient, variant: str, repeat: int) -> RunRow:
    lid = _learner_id("S1", variant, repeat)
    sid = f"s_{uuid.uuid4().hex[:8]}"
    try:
        out = client.post_event(_base_event(lid, sid, "onSessionStart"))
        d = out["decision"]
        return RunRow(
            scenario="S1_session_start",
            variant=variant,
            repeat=repeat,
            orchestrator_triggered=out["orchestrator_triggered"],
            action_type=d.get("action_type", ""),
            latency_ms=out["latency_ms"],
            memory_refs_count=len(d.get("memory_refs") or []),
            narrative_len=len(d.get("narrative_hook") or ""),
        )
    except Exception as e:
        return RunRow("S1_session_start", variant, repeat, False, "", 0, 0, 0, str(e))


def scenario_s2_mistakes(client: EventClient, variant: str, repeat: int) -> RunRow:
    lid = _learner_id("S2", variant, repeat)
    sid = f"s_{uuid.uuid4().hex[:8]}"
    payload = {
        "question_id": "q_pp_001",
        "skill_tags": ["grammar.present_perfect"],
        "user_answer": "I have went",
        "correct_answer": "I have gone",
        "is_correct": False,
        "time_spent_ms": 9000,
    }
    try:
        client.post_event(_base_event(lid, sid, "onMistake", payload))
        out = client.post_event(_base_event(lid, sid, "onMistake", payload))
        d = out["decision"]
        return RunRow(
            scenario="S2_mistake_streak",
            variant=variant,
            repeat=repeat,
            orchestrator_triggered=out["orchestrator_triggered"],
            action_type=d.get("action_type", ""),
            latency_ms=out["latency_ms"],
            memory_refs_count=len(d.get("memory_refs") or []),
            narrative_len=len(d.get("narrative_hook") or ""),
        )
    except Exception as e:
        return RunRow("S2_mistake_streak", variant, repeat, False, "", 0, 0, 0, str(e))


def scenario_s3_task_done(client: EventClient, variant: str, repeat: int) -> RunRow:
    lid = _learner_id("S3", variant, repeat)
    sid = f"s_{uuid.uuid4().hex[:8]}"
    try:
        out = client.post_event(
            _base_event(
                lid,
                sid,
                "onTaskDone",
                {"outcome": "player", "correct_rate": 72.0, "total_questions": 10},
            ),
        )
        d = out["decision"]
        return RunRow(
            scenario="S3_task_done",
            variant=variant,
            repeat=repeat,
            orchestrator_triggered=out["orchestrator_triggered"],
            action_type=d.get("action_type", ""),
            latency_ms=out["latency_ms"],
            memory_refs_count=len(d.get("memory_refs") or []),
            narrative_len=len(d.get("narrative_hook") or ""),
        )
    except Exception as e:
        return RunRow("S3_task_done", variant, repeat, False, "", 0, 0, 0, str(e))


def scenario_s4_low_engage(client: EventClient, variant: str, repeat: int) -> RunRow:
    lid = _learner_id("S4", variant, repeat)
    sid = f"s_{uuid.uuid4().hex[:8]}"
    try:
        out = client.post_event(
            _base_event(lid, sid, "onLowEngage", {"idle_seconds": 120, "engagement_score": 0.2}),
        )
        d = out["decision"]
        return RunRow(
            scenario="S4_low_engage",
            variant=variant,
            repeat=repeat,
            orchestrator_triggered=out["orchestrator_triggered"],
            action_type=d.get("action_type", ""),
            latency_ms=out["latency_ms"],
            memory_refs_count=len(d.get("memory_refs") or []),
            narrative_len=len(d.get("narrative_hook") or ""),
        )
    except Exception as e:
        return RunRow("S4_low_engage", variant, repeat, False, "", 0, 0, 0, str(e))


def scenario_s5_memory_writes(client: EventClient, variant: str, repeat: int) -> RunRow:
    lid = _learner_id("S5", variant, repeat)
    sid = f"s_{uuid.uuid4().hex[:8]}"
    try:
        for i in range(6):
            correct = i % 2 == 0
            client.post_event(
                _base_event(
                    lid,
                    sid,
                    "onAnswer" if correct else "onMistake",
                    {
                        "question_id": f"q_{i}",
                        "skill_tags": ["grammar.present_perfect"],
                        "user_answer": "A" if correct else "wrong",
                        "correct_answer": "A",
                        "is_correct": correct,
                        "time_spent_ms": 5000 + i * 200,
                    },
                ),
            )
        out = client.post_event(_base_event(lid, sid, "onSessionStart"))
        d = out["decision"]
        return RunRow(
            scenario="S5_mixed_answers",
            variant=variant,
            repeat=repeat,
            orchestrator_triggered=out["orchestrator_triggered"],
            action_type=d.get("action_type", ""),
            latency_ms=out["latency_ms"],
            memory_refs_count=len(d.get("memory_refs") or []),
            narrative_len=len(d.get("narrative_hook") or ""),
        )
    except Exception as e:
        return RunRow("S5_mixed_answers", variant, repeat, False, "", 0, 0, 0, str(e))


SCENARIOS = [
    scenario_s1_session_start,
    scenario_s2_mistakes,
    scenario_s3_task_done,
    scenario_s4_low_engage,
    scenario_s5_memory_writes,
]

VARIANTS = ["full", "memory_off", "llm_off"]


def _headers_for_variant(variant: str) -> dict:
    """Per-request env not supported; variants documented in report — use separate API runs."""
    return {}


def _make_client() -> EventClient:
    if EVAL_MODE == "http":
        return HttpxEventClient()
    return LocalEventClient()


def run_all() -> list[RunRow]:
    rows: list[RunRow] = []
    variant = os.environ.get("SWIGAR_EVAL_VARIANT", "full")
    client = _make_client()
    try:
        meta = client.health()
        print("Health:", json.dumps(meta, indent=2))
        print(f"Eval mode: {EVAL_MODE}, variant: {variant}")
        for fn in SCENARIOS:
            for rep in range(1, REPEATS + 1):
                row = fn(client, variant, rep)
                rows.append(row)
                print(
                    f"{row.scenario} #{rep} triggered={row.orchestrator_triggered} "
                    f"action={row.action_type} latency={row.latency_ms:.0f}ms"
                    + (f" ERR={row.error[:80]}" if row.error else "")
                )
    finally:
        client.close()
    return rows


def write_csv(rows: list[RunRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(RunRow.__dataclass_fields__.keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r.__dict__)


def write_summary(rows: list[RunRow], path: Path) -> None:
    by_scenario: dict[str, list[RunRow]] = {}
    for r in rows:
        by_scenario.setdefault(r.scenario, []).append(r)

    lines = [
        f"# Swigar eval summary ({datetime.now(timezone.utc).isoformat()})",
        f"API: {API_BASE}",
        f"Variant: {os.environ.get('SWIGAR_EVAL_VARIANT', 'full')}",
        f"Repeats per scenario: {REPEATS}",
        "",
    ]
    for scenario, grp in sorted(by_scenario.items()):
        latencies = [r.latency_ms for r in grp if r.latency_ms > 0]
        triggered = sum(1 for r in grp if r.orchestrator_triggered)
        actions = [r.action_type for r in grp if r.action_type]
        mem_refs = [r.memory_refs_count for r in grp]
        lines.append(f"## {scenario}")
        lines.append(f"- orchestrator_triggered: {triggered}/{len(grp)}")
        if latencies:
            lines.append(
                f"- latency_ms mean={statistics.mean(latencies):.1f} "
                f"p95~={sorted(latencies)[int(0.95 * len(latencies)) - 1]:.1f}"
            )
        if actions:
            lines.append(f"- action_types: {', '.join(sorted(set(actions)))}")
        if mem_refs:
            lines.append(f"- memory_refs mean={statistics.mean(mem_refs):.2f}")
        errors = [r.error for r in grp if r.error]
        if errors:
            lines.append(f"- errors: {len(errors)}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def plot_charts(rows: list[RunRow], out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skip charts")
        return

    by_scenario: dict[str, list[float]] = {}
    for r in rows:
        if r.latency_ms > 0:
            by_scenario.setdefault(r.scenario, []).append(r.latency_ms)

    if by_scenario:
        fig, ax = plt.subplots(figsize=(10, 5))
        labels = list(by_scenario.keys())
        means = [statistics.mean(by_scenario[k]) for k in labels]
        ax.bar(labels, means, color="#d97706")
        ax.set_ylabel("Mean latency (ms)")
        ax.set_title("Orchestration latency by scenario")
        plt.xticks(rotation=20, ha="right")
        fig.tight_layout()
        fig.savefig(out_dir / "fig_latency_by_scenario.png", dpi=150)
        plt.close(fig)

    action_counts: dict[str, int] = {}
    for r in rows:
        if r.action_type:
            action_counts[r.action_type] = action_counts.get(r.action_type, 0) + 1
    if action_counts:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(list(action_counts.keys()), list(action_counts.values()), color="#1e40af")
        ax.set_ylabel("Count")
        ax.set_title("LearningDecision action_type distribution")
        plt.xticks(rotation=15, ha="right")
        fig.tight_layout()
        fig.savefig(out_dir / "fig_action_distribution.png", dpi=150)
        plt.close(fig)


@dataclass
class PaperRunRow:
    scenario: str
    paper_questions: int
    db_count: int
    generated_count: int
    generate_ms: float
    answer_ok: bool
    queue_ready: bool
    error: str = ""


def run_paper_eval(client: EventClient) -> list[PaperRunRow]:
    """Paper-based agent: session start, 10-question paper, answer, queue."""
    rows: list[PaperRunRow] = []
    lid = f"paper_eval_{uuid.uuid4().hex[:8]}"

    def _request(method: str, path: str, json_body: dict | None = None) -> tuple[dict, float]:
        t0 = time.perf_counter()
        if isinstance(client, LocalEventClient):
            import asyncio

            async def _go():
                if method == "POST":
                    return await client._client.post(path, json=json_body)
                return await client._client.get(path)

            r = client._loop.run_until_complete(_go())
        else:
            hc = getattr(client, "_client", None)
            if not hc:
                raise RuntimeError("Paper eval requires LocalEventClient or HttpxEventClient")
            if method == "POST":
                r = hc.post(f"{API_BASE}{path}", json=json_body)
            else:
                r = hc.get(f"{API_BASE}{path}")
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json(), ms

    try:
        body, gen_ms = _request("POST", f"/v1/sessions/{lid}/start")
        assembly_mode = body.get("assembly_mode") or "unknown"
        paper = body.get("paper") or {}
        meta = paper.get("questions_meta") or []
        db_n = sum(1 for q in meta if q.get("source") == "database")
        gen_n = sum(1 for q in meta if q.get("source") == "generated")
        rows.append(
            PaperRunRow(
                scenario=f"P1_generate_paper_{assembly_mode}",
                paper_questions=len(meta),
                db_count=db_n,
                generated_count=gen_n,
                generate_ms=gen_ms,
                answer_ok=False,
                queue_ready=False,
            )
        )
        _request("GET", f"/v1/learners/{lid}/reserve")
        pid = paper.get("paper_id")
        if pid and meta:
            q0, _ = _request("GET", f"/v1/papers/{pid}/questions/0")
            choices = q0.get("choices") or []
            ans = choices[0] if choices else "gone"
            ar, _ = _request(
                "POST",
                f"/v1/papers/{pid}/answers",
                {"user_answer": ans, "question_index": 0, "time_spent_ms": 2000},
            )
            rows[-1].answer_ok = "is_correct" in ar
        queue, _ = _request("GET", f"/v1/papers/queue?learner_id={lid}")
        rows[-1].queue_ready = bool(queue.get("ready"))
    except Exception as e:
        rows.append(
            PaperRunRow("P1_generate_paper", 0, 0, 0, 0, False, False, str(e))
        )
    return rows


def write_paper_csv(rows: list[PaperRunRow], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "scenario",
                "paper_questions",
                "db_count",
                "generated_count",
                "generate_ms",
                "answer_ok",
                "queue_ready",
                "error",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.scenario,
                    r.paper_questions,
                    r.db_count,
                    r.generated_count,
                    f"{r.generate_ms:.1f}",
                    r.answer_ok,
                    r.queue_ready,
                    r.error,
                ]
            )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if os.environ.get("SWIGAR_LLM_ENABLED", "").lower() in ("0", "false", "no"):
        os.environ["SWIGAR_LLM_ENABLED"] = "false"
    if os.environ.get("SWIGAR_MEMORY_DISABLED", "").lower() in ("1", "true", "yes"):
        os.environ["SWIGAR_MEMORY_DISABLED"] = "true"
    _apply_eval_env()
    rows = run_all()
    variant = os.environ.get("SWIGAR_EVAL_VARIANT", "full")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_path = OUT_DIR / f"results_{variant}_{stamp}.csv"
    write_csv(rows, csv_path)
    write_summary(rows, OUT_DIR / f"summary_{variant}_{stamp}.md")
    plot_charts(rows, OUT_DIR)
    print(f"Wrote {csv_path}")

    mode = EVAL_MODE
    paper_client: EventClient
    if mode == "local":
        paper_client = LocalEventClient()
    else:
        paper_client = HttpxEventClient()
    try:
        paper_rows = run_paper_eval(paper_client)
        paper_csv = OUT_DIR / f"paper_results_{stamp}.csv"
        write_paper_csv(paper_rows, paper_csv)
        print(f"Wrote {paper_csv}")
        for pr in paper_rows:
            print(
                f"  {pr.scenario}: questions={pr.paper_questions} "
                f"(db={pr.db_count}, gen={pr.generated_count}) "
                f"latency={pr.generate_ms:.0f}ms queue={pr.queue_ready}"
            )
    finally:
        paper_client.close()


if __name__ == "__main__":
    main()
