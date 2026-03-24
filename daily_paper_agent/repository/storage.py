from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "seen_ids": [],
            "paper_memory": [],
            "trend_memory": [],
            "idea_backlog": [],
            "last_report": None,
            "last_run_at": None,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "seen_ids": [],
            "paper_memory": [],
            "trend_memory": [],
            "idea_backlog": [],
            "last_report": None,
            "last_run_at": None,
        }
    data.setdefault("seen_ids", [])
    data.setdefault("paper_memory", [])
    data.setdefault("trend_memory", [])
    data.setdefault("idea_backlog", [])
    data.setdefault("last_report", None)
    data.setdefault("last_run_at", None)
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
