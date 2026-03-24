from __future__ import annotations

import ast
import json
import re
import time
from typing import Any

import requests
from requests.exceptions import SSLError

from ..agent.models import LLMUsage, LLMStepResponse


class LLMClient:
    def __init__(
        self,
        api_key: str,
        api_base: str,
        model: str,
        retry_backoffs: list[int] | None = None,
        request_timeout: int = 120,
    ):
        self.api_key = api_key.strip()
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.retry_backoffs = retry_backoffs or [0, 1, 2, 4, 8]
        self.request_timeout = request_timeout

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _post_chat(self, payload: dict[str, Any], timeout: int | None = None) -> dict[str, Any]:
        timeout = timeout or self.request_timeout
        last_exc: Exception | None = None
        for backoff in self.retry_backoffs:
            if backoff:
                time.sleep(backoff)
            try:
                resp = requests.post(
                    f"{self.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "Connection": "close",
                    },
                    json=payload,
                    timeout=timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except SSLError as exc:
                last_exc = RuntimeError(
                    f"TLS connection interrupted (possible transient network/proxy/provider issue): {exc}"
                )
            except Exception as exc:
                last_exc = exc
        raise RuntimeError(f"LLM request failed after retries: {last_exc}")

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        timeout: int = 120,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        if not self.enabled:
            raise RuntimeError("LLM api_key is empty")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        data = self._post_chat(payload=payload, timeout=timeout)
        return data["choices"][0]["message"]["content"].strip()

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        timeout: int = 120,
    ) -> LLMStepResponse:
        if not self.enabled:
            raise RuntimeError("LLM api_key is empty")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        data = self._post_chat(payload=payload, timeout=timeout)
        choice = data["choices"][0]
        msg = choice.get("message", {})
        usage_raw = data.get("usage") or {}
        usage = LLMUsage(
            prompt_tokens=usage_raw.get("prompt_tokens"),
            completion_tokens=usage_raw.get("completion_tokens"),
            total_tokens=usage_raw.get("total_tokens"),
        )
        return LLMStepResponse(
            content=(msg.get("content") or "").strip() if isinstance(msg.get("content"), str) else "",
            tool_calls=msg.get("tool_calls") or [],
            finish_reason=choice.get("finish_reason"),
            usage=usage,
            raw_message=msg,
        )


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text


def _iter_brace_objects(text: str) -> list[str]:
    """Extract balanced {...} candidates while respecting quoted strings."""
    out: list[str] = []
    start = -1
    depth = 0
    in_str = False
    quote = ""
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
            continue

        if ch in ('"', "'"):
            in_str = True
            quote = ch
            continue

        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                out.append(text[start : i + 1])
                start = -1
    return out


def _parse_maybe_json(candidate: str) -> dict[str, Any] | None:
    candidate = candidate.strip()
    if not candidate:
        return None

    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Fallback for python-dict-like outputs (single quotes, True/False, etc.)
    try:
        obj = ast.literal_eval(candidate)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return None


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract first object-like payload from model output with robust fallbacks."""
    text = _strip_code_fence(text)

    obj = _parse_maybe_json(text)
    if obj is not None:
        return obj

    for cand in _iter_brace_objects(text):
        obj = _parse_maybe_json(cand)
        if obj is not None:
            return obj

    raise ValueError("No parseable JSON object found in model output")
