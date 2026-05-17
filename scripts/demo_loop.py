#!/usr/bin/env python3
"""Simulate one learning loop via HTTP API."""

import json
import urllib.request

API = "http://127.0.0.1:8000"


def post(path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def main():
    event = {
        "type": "onMistake",
        "learner_id": "u_demo",
        "session_id": "s_demo",
        "game_context": {"map_id": "castle", "npc_id": "mentor", "quest_id": "grammar_dungeon_1"},
        "payload": {
            "skill_tags": ["grammar.present_perfect"],
            "is_correct": False,
            "user_answer": "I have went",
            "correct_answer": "gone",
        },
    }
    print("POST /v1/events (x2)...")
    post("/v1/events", event)
    post("/v1/events", event)

    print("GET pending decisions...")
    req = urllib.request.Request(f"{API}/v1/decisions/u_demo/pending")
    with urllib.request.urlopen(req) as resp:
        decisions = json.loads(resp.read().decode())
    print(json.dumps(decisions, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
