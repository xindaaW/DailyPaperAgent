from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import time
from typing import Any

from .adapters.arxiv_client import fetch_papers
from .adapters.llm_client import LLMClient
from .adapters.mailer import send_report_mail
from .adapters.pdf_renderer import render_pdf
from .agent.models import Paper
from .agent.orchestrator import AutonomousResearchAgent
from .config import Config
from .repository.storage import load_state, save_state
from .reporting import write_markdown
from .tooling.toolbox import Toolbox, select_related_memory_papers


def _sanitize_report_output(text: str) -> str:
    out = text
    out = re.sub(r"<think>[\s\S]*?</think>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<thinking>[\s\S]*?</thinking>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"```think[\s\S]*?```", "", out, flags=re.IGNORECASE)
    out = re.sub(r"^\s*🧠\s*Thinking:.*$", "", out, flags=re.MULTILINE)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _paper_from_record(rec: dict[str, Any]) -> Paper | None:
    try:
        pid = str(rec.get("id") or "").strip()
        title = str(rec.get("title") or "").strip()
        if not pid or not title:
            return None
        summary = str(rec.get("summary") or "")
        authors = [str(x) for x in (rec.get("authors") or []) if str(x).strip()]
        pub_raw = str(rec.get("published_at") or "")
        upd_raw = str(rec.get("updated_at") or pub_raw or datetime.now(timezone.utc).isoformat())
        pub = datetime.fromisoformat(pub_raw.replace("Z", "+00:00")) if pub_raw else datetime.now(timezone.utc)
        upd = datetime.fromisoformat(upd_raw.replace("Z", "+00:00")) if upd_raw else pub
        url = str(rec.get("url") or rec.get("link") or "")
        cats = [str(x) for x in (rec.get("categories") or []) if str(x).strip()]
        return Paper(pid, title, summary, authors, pub, upd, url, cats)
    except Exception:
        return None


def run_once(cfg: Config, dry_run: bool = False) -> Path:
    print("[TRACK] cycle | running | cycle started")
    reports_dir = Path(cfg.storage.get("reports_dir", "reports"))
    state_file = Path(cfg.storage.get("state_file", "data/state.json"))

    state = load_state(state_file)
    print("[TRACK] state | running | loaded state")
    seen_ids = set(state.get("seen_ids", []))

    print("[TRACK] fetch | running | fetching papers from arXiv")
    try:
        papers = fetch_papers(cfg.topics, cfg.arxiv)
    except Exception as exc:
        print(f"[WARN] fetch | arXiv unavailable, fallback to paper_memory: {exc}")
        memory_records = state.get("paper_memory", [])[-300:]
        papers = [p for p in (_paper_from_record(x) for x in memory_records) if p is not None]
        papers.sort(key=lambda x: x.published_at, reverse=True)
        if not papers:
            raise
    print(f"[TRACK] fetch | running | fetched papers={len(papers)}")
    max_per_run = int(cfg.scheduler.get("max_papers_per_run", 24))
    min_for_analysis = int(cfg.scheduler.get("min_papers_for_analysis", 18))
    exploration_pool_size = int(cfg.scheduler.get("exploration_pool_size", max(max_per_run * 2, 48)))
    target_analysis_pool_size = int(cfg.scheduler.get("target_analysis_pool_size", max(min_for_analysis, 40)))
    related_memory_limit = int(cfg.scheduler.get("related_memory_limit", 20))

    fresh_all = [p for p in papers if p.paper_id not in seen_ids]
    exploration_pool = fresh_all[:exploration_pool_size] if exploration_pool_size > 0 else list(fresh_all)
    if not exploration_pool:
        exploration_pool = papers[:target_analysis_pool_size]

    analysis_pool: list[Paper] = []
    selected_ids: set[str] = set()

    def _add_candidates(candidates: list[Paper], limit: int | None = None) -> None:
        added = 0
        for paper in candidates:
            if paper.paper_id in selected_ids:
                continue
            analysis_pool.append(paper)
            selected_ids.add(paper.paper_id)
            added += 1
            if limit is not None and added >= limit:
                break

    # Keep a dedicated fresh slice for bookkeeping while allowing a larger exploration pool.
    fresh = exploration_pool[:max_per_run] if max_per_run > 0 else list(exploration_pool)
    _add_candidates(exploration_pool)

    if len(analysis_pool) < target_analysis_pool_size:
        need = target_analysis_pool_size - len(analysis_pool)
        seen_context = [p for p in papers if p.paper_id in seen_ids]
        _add_candidates(seen_context, limit=need)

    related = select_related_memory_papers(exploration_pool, state.get("paper_memory", []), limit=related_memory_limit)
    memory_context = [p for p in (_paper_from_record(x) for x in related) if p is not None]
    if len(analysis_pool) < target_analysis_pool_size:
        need = target_analysis_pool_size - len(analysis_pool)
        _add_candidates(memory_context, limit=need)

    if len(analysis_pool) < min_for_analysis:
        _add_candidates(papers, limit=min_for_analysis - len(analysis_pool))

    print(
        "[TRACK] selection | running | "
        f"fresh_total={len(fresh_all)} exploration_pool={len(exploration_pool)} "
        f"fresh_marked={len(fresh)} analysis_pool={len(analysis_pool)} memory_context={len(memory_context)}"
    )

    llm = LLMClient(
        api_key=str(cfg.llm.get("api_key", "")),
        api_base=str(cfg.llm.get("api_base", "https://api.openai.com/v1")),
        model=str(cfg.llm.get("model", "gpt-4o-mini")),
    )
    print(f"[TRACK] llm | running | enabled={llm.enabled} model={cfg.llm.get('model', '')}")

    toolbox = Toolbox(cfg.topics, cfg.arxiv, state.get("paper_memory", []))
    agent = AutonomousResearchAgent(llm=llm, cfg=cfg.raw, toolbox=toolbox, memory_state=state)
    report = _sanitize_report_output(agent.run(analysis_pool))

    print("[TRACK] report | running | writing markdown")
    md_path = write_markdown(report, reports_dir)
    print(f"[TRACK] report | running | markdown saved: {md_path}")

    pdf_path = None
    try:
        print("[TRACK] report | running | rendering pdf")
        pdf_path = render_pdf(report, reports_dir / f"{md_path.stem}.pdf")
        print(f"[TRACK] report | running | pdf saved: {pdf_path}")
    except Exception as exc:
        print(f"[WARN] PDF generation failed: {exc}")

    if not dry_run:
        try:
            print("[TRACK] mail | running | sending email")
            send_report_mail(cfg.mail, pdf_path)
            print("[TRACK] mail | completed | email sent")
        except Exception as exc:
            print(f"[WARN] Email failed: {exc}")

    seen_ids.update([p.paper_id for p in fresh])
    new_paper_memory = state.get("paper_memory", []) + [p.to_dict() for p in fresh]

    trend_lines = [ln[2:].strip() for ln in report.splitlines() if ln.startswith("- ")][:80]
    state.update(
        {
            "seen_ids": list(seen_ids)[-10000:],
            "paper_memory": new_paper_memory[-2500:],
            "trend_memory": (state.get("trend_memory", []) + trend_lines)[-500:],
            "idea_backlog": (state.get("idea_backlog", []) + [x for x in trend_lines if "idea" in x.lower() or "假设" in x])[-500:],
            "last_report": str(md_path),
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "last_selected_count": len(fresh),
            "last_fresh_total_count": len(fresh_all),
            "last_exploration_pool_count": len(exploration_pool),
            "last_analysis_pool_count": len(analysis_pool),
        }
    )
    save_state(state_file, state)
    print("[TRACK] state | completed | persisted state")

    print(
        f"[INFO] cycle done | fresh={len(fresh)} analysis_pool={len(analysis_pool)} "
        f"report={md_path}"
    )
    print("[TRACK] cycle | completed | cycle completed")
    return md_path


def run_scheduler(cfg: Config, once: bool = False, dry_run: bool = False) -> None:
    interval_hours = int(cfg.scheduler.get("interval_hours", 24))
    while True:
        start = time.time()
        try:
            run_once(cfg, dry_run=dry_run)
        except Exception as exc:
            print(f"[ERROR] cycle failed: {exc}")

        if once:
            return

        elapsed = int(time.time() - start)
        sleep_seconds = max(1, interval_hours * 3600 - elapsed)
        next_run = datetime.now().astimezone() + timedelta(seconds=sleep_seconds)
        print(f"[INFO] sleeping {sleep_seconds}s, next run at {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        time.sleep(sleep_seconds)
