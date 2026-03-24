from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import xml.etree.ElementTree as ET
import re

import requests

from ..agent.models import Paper

# Prefer HTTPS for stability in this environment.
ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _quote(term: str) -> str:
    return '"' + term.replace('"', '\\"').strip() + '"'


def _tokenize_term(term: str) -> list[str]:
    tokens = re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", term.strip())
    return [t for t in tokens if len(t) >= 2]


def _term_clause(term: str) -> str:
    t = term.strip()
    if not t:
        return ""
    tokens = _tokenize_term(t)
    if len(tokens) >= 2:
        and_clause = " AND ".join(f"all:{_quote(w)}" for w in tokens[:8])
        return f'(all:{_quote(t)} OR ({and_clause}))'
    if tokens:
        return f'all:{_quote(tokens[0])}'
    return f'all:{_quote(t)}'


def build_query(topics: dict) -> str:
    clauses: list[str] = []

    categories = topics.get("categories", [])
    if categories:
        clauses.append("(" + " OR ".join(f"cat:{c}" for c in categories) + ")")

    include_terms = topics.get("include_terms", [])
    if include_terms:
        term_clauses = [_term_clause(str(t)) for t in include_terms if str(t).strip()]
        term_clauses = [c for c in term_clauses if c]
        if term_clauses:
            clauses.append("(" + " OR ".join(term_clauses) + ")")

    query = " AND ".join(clauses) if clauses else 'abs:"large language model"'
    for t in topics.get("exclude_terms", []):
        query += f" ANDNOT all:{_quote(t)}"
    return query


def build_category_only_query(topics: dict) -> str:
    categories = topics.get("categories", [])
    if categories:
        return "(" + " OR ".join(f"cat:{c}" for c in categories) + ")"
    return 'abs:"large language model"'


def build_relaxed_query(topics: dict) -> str:
    categories = topics.get("categories", [])
    include_terms = topics.get("include_terms", [])
    token_pool: list[str] = []
    for t in include_terms:
        token_pool.extend(_tokenize_term(str(t)))
    token_pool = list(dict.fromkeys(token_pool))[:16]

    clauses: list[str] = []
    if categories:
        clauses.append("(" + " OR ".join(f"cat:{c}" for c in categories) + ")")
    if token_pool:
        clauses.append("(" + " OR ".join(f"all:{_quote(tok)}" for tok in token_pool) + ")")
    return " AND ".join(clauses) if clauses else build_category_only_query(topics)


def _parse_time(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def parse_feed(xml_text: str) -> list[Paper]:
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        entry_id = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
        title = entry.findtext("atom:title", default="", namespaces=ATOM_NS).replace("\n", " ").strip()
        summary = entry.findtext("atom:summary", default="", namespaces=ATOM_NS).replace("\n", " ").strip()
        published = _parse_time(entry.findtext("atom:published", default="", namespaces=ATOM_NS))
        updated = _parse_time(entry.findtext("atom:updated", default="", namespaces=ATOM_NS))
        authors = [a.findtext("atom:name", default="", namespaces=ATOM_NS).strip() for a in entry.findall("atom:author", ATOM_NS)]
        cats = [c.attrib.get("term", "") for c in entry.findall("atom:category", ATOM_NS)]

        link = ""
        for ln in entry.findall("atom:link", ATOM_NS):
            if ln.attrib.get("rel") == "alternate":
                link = ln.attrib.get("href", "")
                break
        if not link:
            link = entry_id

        pid = entry_id.rsplit("/", 1)[-1] if entry_id else "unknown"
        papers.append(Paper(pid, title, summary, [x for x in authors if x], published, updated, link, [x for x in cats if x]))
    return papers


def fetch_papers(topics: dict, arxiv_cfg: dict) -> list[Paper]:
    def _request(query: str) -> list[Paper]:
        params = {
            "search_query": query,
            "start": 0,
            "max_results": int(arxiv_cfg.get("max_results", 120)),
            "sortBy": arxiv_cfg.get("sort_by", "submittedDate"),
            "sortOrder": arxiv_cfg.get("sort_order", "descending"),
        }
        url = f"{ARXIV_API_URL}?{urlencode(params)}"

        resp = None
        err = None
        for timeout in (8, 12, 20):
            try:
                resp = requests.get(
                    url,
                    timeout=timeout,
                    headers={
                        "User-Agent": "DailyPaperAgent/1.0 (+https://github.com/xindaaW/llm-radar-agent)",
                        "Connection": "close",
                    },
                )
                resp.raise_for_status()
                break
            except Exception as exc:
                err = exc
                resp = None
        if resp is None:
            raise RuntimeError(f"arXiv request failed for query={query!r}: {err}")
        return parse_feed(resp.text)

    primary_query = build_query(topics)
    papers = _request(primary_query)
    if not papers and topics.get("include_terms"):
        # Stage-2 fallback: relax phrase matching to token-level matching.
        papers = _request(build_relaxed_query(topics))
    allow_category_fallback = bool(arxiv_cfg.get("fallback_to_category_on_empty", True))
    if not papers and topics.get("include_terms") and allow_category_fallback:
        # Stage-3 fallback: retain only category constraints.
        papers = _request(build_category_only_query(topics))

    cutoff = datetime.now(timezone.utc) - timedelta(hours=int(arxiv_cfg.get("lookback_hours", 168)))
    include_updated = bool(arxiv_cfg.get("include_updated_window", True))
    if include_updated:
        papers = [p for p in papers if p.published_at >= cutoff or p.updated_at >= cutoff]
    else:
        papers = [p for p in papers if p.published_at >= cutoff]

    allow_expand_lookback = bool(arxiv_cfg.get("fallback_expand_lookback", True))
    if not papers and allow_expand_lookback and int(arxiv_cfg.get("lookback_hours", 168)) < 24 * 30:
        # Second fallback: widen time window to reduce empty-run probability.
        widened_cfg = dict(arxiv_cfg)
        widened_cfg["lookback_hours"] = max(24 * 30, int(arxiv_cfg.get("lookback_hours", 168)) * 2)
        return fetch_papers({"categories": topics.get("categories", []), "include_terms": [], "exclude_terms": []}, widened_cfg)

    papers.sort(key=lambda x: x.published_at, reverse=True)
    return papers
