from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class AgentLogger:
    def __init__(self, log_dir: str = "./DailyPaperAgent/runtime_logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file: Path | None = None
        self.log_index = 0

    def start_new_run(self) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"agent_run_{ts}.log"
        self.log_index = 0
        with self.log_file.open("w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"DailyPaperAgent Run Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
        return self.log_file

    def _write(self, typ: str, payload: dict[str, Any]) -> None:
        if self.log_file is None:
            return
        self.log_index += 1
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write("\n" + "-" * 80 + "\n")
            f.write(f"[{self.log_index}] {typ}\n")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
            f.write("-" * 80 + "\n")
            f.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def log_request(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> None:
        self._write("REQUEST", {"messages": messages, "tools": tools or []})

    def log_response(self, content: str, tool_calls: list[dict[str, Any]] | None, finish_reason: str | None, usage: dict[str, Any] | None) -> None:
        self._write(
            "RESPONSE",
            {
                "content": content,
                "tool_calls": tool_calls or [],
                "finish_reason": finish_reason,
                "usage": usage or {},
            },
        )

    def log_tool_result(self, tool_name: str, arguments: dict[str, Any], success: bool, result: Any = None, error: str | None = None) -> None:
        self._write(
            "TOOL_RESULT",
            {
                "tool_name": tool_name,
                "arguments": arguments,
                "success": success,
                "result": result if success else None,
                "error": error if not success else None,
            },
        )
