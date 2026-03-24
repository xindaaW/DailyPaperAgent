from __future__ import annotations

from pathlib import Path


def load_skill_context(skill_files: list[str], max_chars_per_skill: int = 3500) -> str:
    chunks: list[str] = []
    for fp in skill_files:
        p = Path(fp)
        if not p.exists() or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if not text:
            continue
        snippet = text[:max_chars_per_skill]
        chunks.append(f"[SKILL:{p.name}]\n{snippet}")

    return "\n\n".join(chunks)
