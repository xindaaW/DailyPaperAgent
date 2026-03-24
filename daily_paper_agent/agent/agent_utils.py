from __future__ import annotations

import json
import re
from typing import Any


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_CYAN = "\033[96m"


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", text)


def short_json(data: Any, max_chars: int = 5000) -> str:
    text = json.dumps(data, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def strip_think_blocks(text: str) -> str:
    if not text:
        return text
    out = text
    out = re.sub(r"<think>[\s\S]*?</think>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<thinking>[\s\S]*?</thinking>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"```think[\s\S]*?```", "", out, flags=re.IGNORECASE)
    out = re.sub(r"^\s*🧠\s*Thinking:.*$", "", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*Thinking:\s*$", "", out, flags=re.MULTILINE)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
