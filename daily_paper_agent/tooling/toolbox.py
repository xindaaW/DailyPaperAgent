from __future__ import annotations

from typing import Any

from ..adapters.arxiv_client import fetch_papers
from ..agent.models import Paper


def keyword_set(text: str) -> set[str]:
    import re

    tokens = re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", text.lower())
    return {t for t in tokens if len(t) >= 2}


def select_related_memory_papers(fresh: list[Paper], paper_memory: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    if not fresh or not paper_memory or limit <= 0:
        return []

    fresh_kw = set()
    for p in fresh:
        fresh_kw |= keyword_set(p.title + " " + p.summary)

    scored: list[tuple[int, dict[str, Any]]] = []
    for rec in paper_memory:
        rec_kw = keyword_set(str(rec.get("title", "")) + " " + str(rec.get("summary", "")))
        overlap = len(fresh_kw & rec_kw)
        if overlap > 0:
            scored.append((overlap, rec))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def serialize_papers(papers: list[Paper], max_items: int = 40) -> list[dict[str, Any]]:
    out = []
    for p in papers[:max_items]:
        out.append(
            {
                "id": p.paper_id,
                "title": p.title,
                "url": p.link,
                "categories": p.categories,
                "published_at": p.published_at.isoformat(),
                "summary": p.summary[:1400],
            }
        )
    return out


class Toolbox:
    def __init__(self, base_topics: dict[str, Any], arxiv_cfg: dict[str, Any], paper_memory: list[dict[str, Any]]):
        self.base_topics = base_topics
        self.arxiv_cfg = arxiv_cfg
        self.paper_memory = paper_memory

    def search_arxiv(self, include_terms: list[str], categories: list[str] | None = None, max_results: int = 30) -> list[dict[str, Any]]:
        use_categories = categories if categories is not None else self.base_topics.get("categories", [])
        topics = {
            "categories": use_categories,
            "include_terms": include_terms,
            "exclude_terms": self.base_topics.get("exclude_terms", []),
        }
        cfg = dict(self.arxiv_cfg)
        cfg["max_results"] = max_results
        cfg["fallback_to_category_on_empty"] = True
        cfg["fallback_expand_lookback"] = False
        try:
            papers = fetch_papers(topics, cfg)
            return [p.to_dict() for p in papers[:max_results]]
        except Exception:
            # Network fallback: use local paper memory retrieval so agent loop can continue.
            fallback = self.get_related_memory(include_terms, limit=max_results)
            for rec in fallback:
                rec.setdefault("_source", "memory_fallback")
            return fallback

    def get_related_memory(self, keywords: list[str], limit: int = 12) -> list[dict[str, Any]]:
        kw = set()
        for k in keywords:
            kw |= keyword_set(k)
        scored: list[tuple[int, dict[str, Any]]] = []
        for rec in self.paper_memory:
            rec_kw = keyword_set(str(rec.get("title", "")) + " " + str(rec.get("summary", "")))
            overlap = len(kw & rec_kw)
            if overlap > 0:
                scored.append((overlap, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]
