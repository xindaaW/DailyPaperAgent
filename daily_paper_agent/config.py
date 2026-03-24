from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os
import re

import yaml

from .domain_presets import DOMAIN_PRESETS


@dataclass
class Config:
    raw: dict[str, Any]

    @property
    def llm(self) -> dict[str, Any]:
        return self.raw.setdefault("llm", {})

    @property
    def topics(self) -> dict[str, Any]:
        return self.raw.setdefault("topics", {})

    @property
    def arxiv(self) -> dict[str, Any]:
        return self.raw.setdefault("arxiv", {})

    @property
    def scheduler(self) -> dict[str, Any]:
        return self.raw.setdefault("scheduler", {})

    @property
    def storage(self) -> dict[str, Any]:
        return self.raw.setdefault("storage", {})

    @property
    def mail(self) -> dict[str, Any]:
        return self.raw.setdefault("mail", {})

    @property
    def report(self) -> dict[str, Any]:
        return self.raw.setdefault("report", {})


DEFAULTS = {
    "llm": {
        "api_key": "",
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "topics": {
        "categories": ["cs.CL", "cs.AI", "cs.LG"],
        "include_terms": [
            "reward model",
            "process reward model",
            "outcome reward model",
            "open-ended generation",
            "writing",
            "rubric",
            "preference optimization",
            "human preference alignment",
        ],
        "exclude_terms": ["survey"],
    },
    "arxiv": {
        "max_results": 320,
        "lookback_hours": 168,
        "sort_by": "submittedDate",
        "sort_order": "descending",
        "include_updated_window": True,
        "fallback_to_category_on_empty": True,
        "fallback_expand_lookback": True,
    },
    "scheduler": {
        "interval_hours": 24,
        "max_papers_per_run": 24,
        "min_papers_for_analysis": 18,
        "exploration_pool_size": 64,
        "target_analysis_pool_size": 48,
        "related_memory_limit": 20,
    },
    "report": {
        "max_agent_steps": 20,
        "max_editorial_rounds": 5,
        "analysis_rounds": 3,
        "review_rounds": 2,
        "enable_skill_context": True,
        "max_context_papers": 80,
        "context_char_limit": 180000,
        "skills_dir": "skills",
        "skill_files": [
            "skills/orchestrator/SKILL.md",
            "skills/subagents/paper_scout/SKILL.md",
            "skills/subagents/baseline_comparator/SKILL.md",
            "skills/subagents/insight_synthesizer/SKILL.md",
            "skills/subagents/idea_generator/SKILL.md",
            "skills/subagents/reviewer/SKILL.md",
            "skills/subagents/reviser/SKILL.md",
            "skills/subagents/final_editor/SKILL.md",
            "skills/pdf_designer/SKILL.md",
        ],
    },
    "storage": {
        "reports_dir": "reports",
        "state_file": "data/state.json",
        "runtime_logs_dir": "runtime_logs",
    },
    "mail": {
        "enabled": False,
        "smtp_host": "smtp.126.com",
        "smtp_port": 465,
        "use_ssl": True,
        "use_tls": False,
        "username": "",
        "password": "",
        "from_addr": "",
        "to_addrs": [],
        "subject_prefix": "[DailyPaperAgent]",
        "attach_pdf": True,
        "intro_message": "今天你读论文了嘛？",
    },
}


def _deep_merge(base: dict[str, Any], custom: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in custom.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_env_refs(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _resolve_env_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_refs(v) for v in value]
    if isinstance(value, str):
        m = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", value.strip())
        if m:
            return os.getenv(m.group(1), "")
    return value


def load_config(path: str) -> Config:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    merged = _resolve_paths(_resolve_env_refs(_deep_merge(DEFAULTS, raw)), base_dir=p.resolve().parent)
    return Config(raw=merged)


def _resolve_paths(raw: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    out = dict(raw)

    report = dict(out.get("report", {}))
    storage = dict(out.get("storage", {}))

    def _resolve_path(value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            return value
        p = Path(value)
        if p.is_absolute():
            return str(p)
        return str((base_dir / p).resolve())

    report["skills_dir"] = _resolve_path(report.get("skills_dir"))
    skill_files = report.get("skill_files", [])
    if isinstance(skill_files, list):
        report["skill_files"] = [_resolve_path(x) for x in skill_files]

    storage["reports_dir"] = _resolve_path(storage.get("reports_dir"))
    storage["state_file"] = _resolve_path(storage.get("state_file"))
    storage["runtime_logs_dir"] = _resolve_path(storage.get("runtime_logs_dir"))

    out["report"] = report
    out["storage"] = storage
    return out


def _split_csv(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [x.strip() for x in re.split(r"[，,]", raw) if x.strip()]


def apply_focus(cfg: Config, domain: str = "", focus_terms: str = "", focus_categories: str = "") -> str:
    summary: list[str] = []
    if domain:
        key = domain.strip().lower().replace(" ", "_").replace("-", "_")
        preset = DOMAIN_PRESETS.get(key)
        if preset:
            cfg.topics["categories"] = list(preset["categories"])
            cfg.topics["include_terms"] = list(preset["include_terms"])
            summary.append(f"preset={key}")
        else:
            terms = _split_csv(domain)
            if terms:
                cfg.topics["include_terms"] = terms
                summary.append("domain_as_terms")

    if focus_terms:
        terms = _split_csv(focus_terms)
        if terms:
            cfg.topics["include_terms"] = terms
            summary.append("custom_terms")

    if focus_categories:
        cats = _split_csv(focus_categories)
        if cats:
            cfg.topics["categories"] = cats
            summary.append("custom_categories")

    return ",".join(summary) if summary else "default_topics"
