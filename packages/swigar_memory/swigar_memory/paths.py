"""Per-learner MemPalace storage paths."""

import os
from pathlib import Path

SWIGAR_HOME = Path(os.environ.get("SWIGAR_HOME", os.path.expanduser("~/.swigar")))


def learner_palace_path(learner_id: str) -> str:
    safe_id = learner_id.replace("/", "_").replace("\\", "_")
    path = SWIGAR_HOME / "palaces" / safe_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def learner_kg_path(learner_id: str) -> str:
    safe_id = learner_id.replace("/", "_").replace("\\", "_")
    path = SWIGAR_HOME / "palaces" / safe_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path / "knowledge_graph.sqlite3")
