from __future__ import annotations

from datetime import datetime
from pathlib import Path


def write_markdown(report: str, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"daily_paper_{ts}.md"
    path.write_text(report, encoding="utf-8")
    return path


def quality_check(report: str) -> dict:
    import re

    non_empty = [l.strip() for l in report.splitlines() if l.strip()]
    bullet = [l for l in non_empty if re.match(r"^(- |\d+\.\s+)", l)]
    long_lines = [l for l in non_empty if len(l) >= 80 and not l.startswith("#") and not re.match(r"^(- |\d+\.\s+)", l)]
    links = len(re.findall(r"https?://arxiv\.org/abs/\S+", report))

    return {
        "chars": len(report),
        "bullet_density": round(len(bullet) / len(non_empty), 3) if non_empty else 1.0,
        "long_lines": len(long_lines),
        "arxiv_links": links,
    }
