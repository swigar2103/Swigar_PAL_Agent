"""MemPalace adapter for per-learner English learning memory."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

MEMORY_DISABLED = os.environ.get("SWIGAR_MEMORY_DISABLED", "").lower() in ("1", "true", "yes")

from mempalace.knowledge_graph import KnowledgeGraph
from mempalace.layers import MemoryStack
from mempalace.miner import add_drawer
from mempalace.palace import build_closet_lines, get_closets_collection, get_collection
from mempalace.searcher import search_memories

from swigar_core.models import LearningEvent
from swigar_memory.paths import learner_kg_path, learner_palace_path


def _wing_for_domain(skill_tags: list[str]) -> str:
    if not skill_tags:
        return "general"
    tag = skill_tags[0]
    if tag.startswith("grammar."):
        return "grammar"
    if tag.startswith("vocab."):
        return "vocabulary"
    if tag.startswith("dungeon."):
        return "dungeon"
    if tag.startswith("dialogue."):
        return "dialogue"
    return "learner"


def _room_for_event(event: LearningEvent) -> str:
    ctx = event.game_context
    if ctx.quest_id:
        return f"quest_{ctx.quest_id}"
    if ctx.room_id:
        return f"room_{ctx.room_id}"
    return f"session_{event.session_id}"


class LearnerMemoryStore:
    """Read/write learner memory via MemPalace."""

    def __init__(self, learner_id: str):
        self.learner_id = learner_id
        self.palace_path = learner_palace_path(learner_id)
        self._drawers = None
        self._closets = None
        self._kg = None
        self._stack = None

    @property
    def drawers(self):
        if self._drawers is None:
            self._drawers = get_collection(self.palace_path, "mempalace_drawers")
        return self._drawers

    @property
    def closets(self):
        if self._closets is None:
            self._closets = get_closets_collection(self.palace_path)
        return self._closets

    @property
    def kg(self) -> KnowledgeGraph:
        if self._kg is None:
            self._kg = KnowledgeGraph(db_path=learner_kg_path(self.learner_id))
        return self._kg

    @property
    def stack(self) -> MemoryStack:
        if self._stack is None:
            self._stack = MemoryStack(palace_path=self.palace_path)
        return self._stack

    def write_event_verbatim(self, event: LearningEvent) -> str:
        """Write learning event as drawer; return drawer id."""
        if MEMORY_DISABLED:
            return f"drawer_disabled_{event.event_id[:12]}"
        try:
            return self._write_event_verbatim(event)
        except Exception as exc:
            logger.warning("Memory write failed: %s", exc)
            return f"drawer_error_{event.event_id[:12]}"

    def _write_event_verbatim(self, event: LearningEvent) -> str:
        skill_tags = event.payload.get("skill_tags", [])
        wing = _wing_for_domain(skill_tags if isinstance(skill_tags, list) else [])
        room = _room_for_event(event)
        content = json.dumps(
            {
                "event_id": event.event_id,
                "type": event.type.value,
                "learner_id": event.learner_id,
                "session_id": event.session_id,
                "game_context": event.game_context.model_dump(),
                "payload": event.payload,
                "timestamp": event.timestamp.isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        source_file = f"swigar://events/{event.event_id}"
        drawer_id = (
            f"drawer_{wing}_{room}_"
            f"{hashlib.sha256((source_file + '0').encode()).hexdigest()[:24]}"
        )
        add_drawer(
            self.drawers,
            wing=wing,
            room=room,
            content=content,
            source_file=source_file,
            chunk_index=0,
            agent="swigar",
        )
        self._update_closet(wing, room, source_file, [drawer_id], content, skill_tags)
        if not event.payload.get("is_correct", True) and skill_tags:
            tag = skill_tags[0] if isinstance(skill_tags, list) else str(skill_tags)
            self.kg.add_triple(
                self.learner_id,
                "struggles_with",
                tag.replace("grammar.", "").replace("vocab.", ""),
                valid_from=date.today().isoformat(),
                source_drawer_id=drawer_id,
            )
        elif event.payload.get("is_correct") and skill_tags:
            tag = skill_tags[0] if isinstance(skill_tags, list) else str(skill_tags)
            self.kg.add_triple(
                self.learner_id,
                "mastered",
                tag.replace("grammar.", "").replace("vocab.", ""),
                valid_from=date.today().isoformat(),
                source_drawer_id=drawer_id,
            )
        return drawer_id

    def _update_closet(
        self,
        wing: str,
        room: str,
        source_file: str,
        drawer_ids: list[str],
        content: str,
        skill_tags: list | None,
    ) -> None:
        lines = build_closet_lines(source_file, drawer_ids, content, wing, room)
        if skill_tags and lines:
            topic = skill_tags[0] if isinstance(skill_tags, list) else str(skill_tags)
            lines[0] = f"{topic}|weak|→{drawer_ids[0]}"
        closet_id = f"closet_{wing}_{room}_{hashlib.sha256(source_file.encode()).hexdigest()[:16]}"
        if lines:
            self.closets.upsert(
                documents=["\n".join(lines)],
                ids=[closet_id],
                metadatas=[{"wing": wing, "room": room, "source_file": source_file}],
            )

    def wake_up(self, wing: str | None = None) -> str:
        if MEMORY_DISABLED:
            return ""
        try:
            return self.stack.wake_up(wing=wing)
        except Exception as exc:
            logger.warning("wake_up failed: %s", exc)
            return ""

    def recall(self, wing: str | None = None, room: str | None = None, n: int = 10) -> str:
        if MEMORY_DISABLED:
            return ""
        try:
            return self.stack.recall(wing=wing, room=room, n_results=n)
        except Exception as exc:
            logger.warning("recall failed: %s", exc)
            return ""

    def search(self, query: str, wing: str | None = None, room: str | None = None, n: int = 5) -> list[dict[str, Any]]:
        if MEMORY_DISABLED:
            return []
        try:
            results = search_memories(
                query,
                palace_path=self.palace_path,
                wing=wing,
                room=room,
                n_results=n,
            )
            if isinstance(results, dict):
                hits = results.get("results") or results.get("memories") or []
                return hits if isinstance(hits, list) else []
            if isinstance(results, list):
                return results
            return []
        except Exception as exc:
            logger.warning("search failed: %s", exc)
            return []

    def query_weaknesses(self, as_of: str | None = None) -> list[dict]:
        if MEMORY_DISABLED:
            return []
        try:
            rows = self.kg.query_entity(self.learner_id, direction="outgoing")
        except Exception as exc:
            logger.warning("kg query failed: %s", exc)
            return []
        out = []
        for row in rows if isinstance(rows, list) else []:
            pred = row.get("predicate") if isinstance(row, dict) else getattr(row, "predicate", None)
            if pred == "struggles_with":
                out.append(row if isinstance(row, dict) else {"predicate": pred, "object": row})
        return out

    def write_plan_summary(self, summary: str, skill_tags: list[str]) -> None:
        if MEMORY_DISABLED:
            return
        try:
            self._write_plan_summary(summary, skill_tags)
        except Exception as exc:
            logger.warning("plan summary write failed: %s", exc)

    def _write_plan_summary(self, summary: str, skill_tags: list[str]) -> None:
        wing = _wing_for_domain(skill_tags) if skill_tags else "learner"
        room = "orchestrator"
        source_file = f"swigar://plans/{hashlib.sha256(summary.encode()).hexdigest()[:16]}"
        add_drawer(
            self.drawers,
            wing=wing,
            room=room,
            content=summary,
            source_file=source_file,
            chunk_index=0,
            agent="swigar-orchestrator",
        )
