from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Paper:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    published_at: datetime
    updated_at: datetime
    link: str
    categories: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.paper_id,
            "title": self.title,
            "summary": self.summary,
            "authors": self.authors,
            "published_at": self.published_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "url": self.link,
            "categories": self.categories,
        }


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]


@dataclass
class ToolResult:
    success: bool
    content: Any
    error: str | None = None


@dataclass
class AgentMessage:
    role: str
    content: str
    thinking: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class LLMUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class LLMStepResponse:
    content: str
    tool_calls: list[dict[str, Any]]
    finish_reason: str | None = None
    usage: LLMUsage | None = None
    raw_message: dict[str, Any] | None = None
