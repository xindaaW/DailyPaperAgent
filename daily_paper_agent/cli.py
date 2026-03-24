from __future__ import annotations

import argparse

from .config import apply_focus, load_config
from .runner import run_scheduler


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DailyPaperAgent - standalone daily paper tracker")
    p.add_argument("--config", type=str, default="DailyPaperAgent/config.yaml")
    p.add_argument("--once", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--domain", type=str, default="")
    p.add_argument("--focus-terms", type=str, default="")
    p.add_argument("--focus-categories", type=str, default="")
    return p


def main() -> None:
    args = build_parser().parse_args()
    cfg = load_config(args.config)
    summary = apply_focus(
        cfg,
        domain=args.domain,
        focus_terms=args.focus_terms,
        focus_categories=args.focus_categories,
    )
    print(
        f"[INFO] focus={summary} categories={cfg.topics.get('categories', [])} "
        f"terms={cfg.topics.get('include_terms', [])}"
    )
    run_scheduler(cfg, once=args.once, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
