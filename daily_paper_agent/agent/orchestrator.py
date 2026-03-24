from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from .agent_utils import Colors, short_json as _short_json, strip_ansi as _strip_ansi, strip_think_blocks as _strip_think_blocks
from ..adapters.llm_client import LLMClient
from .logger import AgentLogger
from .models import Paper, ToolCall, ToolResult
from ..skillbook import load_skill_context
from ..tooling.skill_loader import SkillLoader
from ..tooling.toolbox import Toolbox, serialize_papers
from ..tooling.tool_registry import ToolRegistry


class AutonomousResearchAgent:
    def __init__(
        self,
        llm: LLMClient,
        cfg: dict[str, Any],
        toolbox: Toolbox,
        memory_state: dict[str, Any],
    ):
        self.llm = llm
        self.cfg = cfg
        self.toolbox = toolbox
        self.memory_state = memory_state
        self.max_steps = int(cfg.get("report", {}).get("max_agent_steps", 10))
        self.max_editorial_rounds = int(cfg.get("report", {}).get("max_editorial_rounds", 3))
        report_cfg = cfg.get("report", {})
        if bool(report_cfg.get("enable_skill_context", True)):
            self.skill_context = load_skill_context(report_cfg.get("skill_files", []))
        else:
            self.skill_context = ""
        self._log_file: Path | None = None
        self._context_papers_for_subagent: list[dict[str, Any]] = []
        self._tool_history_for_subagent: list[dict[str, Any]] = []
        self.logger = AgentLogger(log_dir=str(self.cfg.get("storage", {}).get("runtime_logs_dir", "./DailyPaperAgent/runtime_logs")))
        self.context_char_limit = int(cfg.get("report", {}).get("context_char_limit", 120000))
        self.api_total_tokens = 0
        self.enable_tool_review_gate = bool(report_cfg.get("enable_tool_review_gate", True))
        self.skill_loader = SkillLoader(str(report_cfg.get("skills_dir", "DailyPaperAgent/skills")))
        self.skill_loader.discover_skills()
        self.skill_metadata = self.skill_loader.metadata_prompt()
        self.tool_registry = self._build_tool_registry()

    def _track(self, text: str) -> None:
        if self._log_file is not None:
            try:
                self._log_file.parent.mkdir(parents=True, exist_ok=True)
                with self._log_file.open("a", encoding="utf-8") as f:
                    f.write(_strip_ansi(text) + "\n")
            except Exception:
                pass

    def _ui(self, text: str) -> None:
        print(text)
        self._track(text)

    def run(self, papers: list[Paper]) -> str:
        if not self.llm.enabled:
            return self._fallback_report(papers)

        self._log_file = self.logger.start_new_run()
        self._ui(f"{Colors.DIM}📝 Log file: {self._log_file}{Colors.RESET}")

        max_context_papers = int(self.cfg.get("report", {}).get("max_context_papers", 80))
        context_papers = serialize_papers(papers, max_items=max_context_papers)
        tool_history: list[dict[str, Any]] = []
        self._context_papers_for_subagent = context_papers
        self._tool_history_for_subagent = tool_history
        draft = ""
        self._ui(f"{Colors.DIM}[TRACK] agent_loop | running | autonomous loop started{Colors.RESET}")
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "你是一个自主科研Agent，必须通过工具调用与分析完成高质量中文日报。"
                    "你可以自由决定何时搜索、何时停止。停止标准是内容质量充分，而不是步数。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请生成一份详细中文日报。必须覆盖：\n"
                    "1) 今日更新论文（标题+arXiv链接）\n"
                    "2) 创新点与同主题baseline差异\n"
                    "3) 对领域启发\n"
                    "4) 结合历史脉络的后续idea\n\n"
                    "要求：段落化、可读性强、少短句堆砌。必要时主动调用工具。\n"
                    "你可以自由调用以下子agent工具：paper_scout, baseline_comparator, insight_synthesizer, "
                    "idea_generator, reviewer, reviser, final_editor。"
                    "调用顺序与次数由你自主决定。\n"
                    "如果需要详细技能说明，请先调用 get_skill(skill_name)。\n"
                    f"{self.skill_metadata}\n"
                    f"skills_context={self.skill_context[:12000]}\n"
                    f"papers={_short_json(context_papers, 12000)}\n"
                    f"memory={_short_json(self.memory_state, 8000)}"
                ),
            },
        ]

        run_start = perf_counter()
        try:
            for step in range(1, self.max_steps + 1):
                step_start = perf_counter()
                self._maybe_summarize_messages(messages)
                box_width = 58
                step_text = f"{Colors.BOLD}{Colors.BRIGHT_CYAN}💭 Step {step}{Colors.RESET}"
                padding = max(0, box_width - 2 - len(f"💭 Step {step}"))
                self._ui(f"\n{Colors.DIM}╭{'─' * box_width}╮{Colors.RESET}")
                self._ui(f"{Colors.DIM}│{Colors.RESET} {step_text}{' ' * padding}{Colors.DIM}│{Colors.RESET}")
                self._ui(f"{Colors.DIM}╰{'─' * box_width}╯{Colors.RESET}")

                tools = self._tool_schemas()
                self.logger.log_request(messages=messages, tools=tools)
                resp = self.llm.complete(messages=messages, tools=tools, temperature=0.1)
                if resp.usage and resp.usage.total_tokens:
                    self.api_total_tokens = resp.usage.total_tokens
                content = _strip_think_blocks(resp.content.strip())
                tool_calls = list(resp.tool_calls or [])
                self.logger.log_response(
                    content=content,
                    tool_calls=tool_calls,
                    finish_reason=resp.finish_reason,
                    usage={
                        "prompt_tokens": resp.usage.prompt_tokens if resp.usage else None,
                        "completion_tokens": resp.usage.completion_tokens if resp.usage else None,
                        "total_tokens": resp.usage.total_tokens if resp.usage else None,
                    },
                )
                self._ui(f"{Colors.DIM}[TRACK] agent_loop | step={step} | tool_calls={len(tool_calls)} finish={resp.finish_reason} tokens={self.api_total_tokens}{Colors.RESET}")
                if content:
                    think_match = re.search(r"<think>([\s\S]*?)</think>", content)
                    if think_match:
                        thinking = think_match.group(1).strip()
                        if thinking:
                            preview = thinking if len(thinking) <= 900 else thinking[:900] + "..."
                            self._ui(f"\n{Colors.BOLD}{Colors.MAGENTA}🧠 Thinking:{Colors.RESET}")
                            self._ui(f"{Colors.DIM}{preview}{Colors.RESET}")
                        content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
                    if content:
                        preview = content if len(content) <= 1200 else content[:1200] + "..."
                        self._ui(f"\n{Colors.BOLD}{Colors.BRIGHT_BLUE}🤖 Assistant:{Colors.RESET}")
                        self._ui(preview)

                assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                messages.append(assistant_msg)

                if not tool_calls:
                    if content:
                        draft = content
                        passed, feedback = self._judge_report_ready(
                            draft=draft,
                            papers=context_papers,
                            tool_history=tool_history,
                        )
                        if passed:
                            self._ui(f"{Colors.BRIGHT_GREEN}[TRACK] finalized at step={step} by model judge{Colors.RESET}")
                            step_elapsed = perf_counter() - step_start
                            total_elapsed = perf_counter() - run_start
                            self._ui(f"{Colors.DIM}⏱️  Step {step} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){Colors.RESET}")
                            break
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "当前草稿未达标，请继续完善并补齐证据。\n"
                                    f"评审反馈：{feedback}\n"
                                    "重点补论文标题+链接、baseline对比、跨论文洞察、可执行idea。"
                                ),
                            }
                        )
                    else:
                        messages.append({"role": "user", "content": "请给出完整中文报告，不要只给计划。"})
                    continue

                for tc in tool_calls:
                    fn = ((tc.get("function") or {}).get("name") or "").strip()
                    raw_args = ((tc.get("function") or {}).get("arguments") or "").strip()
                    call_id = (tc.get("id") or "").strip()
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                        if not isinstance(args, dict):
                            args = {}
                    except Exception:
                        args = {}

                    self._ui(f"\n{Colors.BRIGHT_YELLOW}🔧 Tool Call:{Colors.RESET} {Colors.BOLD}{Colors.CYAN}{fn}{Colors.RESET}")
                    self._ui(f"{Colors.DIM}   Arguments:{Colors.RESET}")
                    args_json = json.dumps(args, indent=2, ensure_ascii=False)
                    for line in args_json.splitlines():
                        self._ui(f"   {Colors.DIM}{line}{Colors.RESET}")
                    result = self._execute_tool_safe(ToolCall(tool=fn, args=args))
                    n = len(result.content) if isinstance(result.content, list) else 1
                    if result.success:
                        self._ui(f"{Colors.BRIGHT_GREEN}✓ Result:{Colors.RESET} returned={n}")
                    else:
                        self._ui(f"{Colors.RED}✗ Tool Error:{Colors.RESET} returned=1")
                    out_preview = _short_json(result.content if result.success else {"error": result.error}, 1200)
                    self._ui(f"{Colors.DIM}{out_preview}{Colors.RESET}")
                    self.logger.log_tool_result(
                        tool_name=fn,
                        arguments=args,
                        success=result.success,
                        result=result.content if result.success else None,
                        error=result.error if not result.success else None,
                    )
                    tool_history.append({"tool": fn, "args": args, "result": result.content if result.success else {"error": result.error}})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": fn,
                            "content": _short_json(result.content if result.success else {"error": result.error}, 16000),
                        }
                    )
                    if self.enable_tool_review_gate and fn != "reviewer":
                        ok, feedback, bad_case, improvement = self._review_subagent_output(fn=fn, args=args, result=result)
                        if not ok:
                            self._ui(f"{Colors.BRIGHT_YELLOW}[TRACK] quality_gate | {fn} needs refinement{Colors.RESET}")
                            messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        f"质量闸门判定：工具 `{fn}` 输出还不够好。\n"
                                        f"问题总结：{feedback}\n"
                                        f"Bad case（具体问题片段）：{bad_case}\n"
                                        f"改进方向：{improvement}\n"
                                        f"请优先重新调用 `{fn}`，并在下一次输出中明确修复上述 bad case。"
                                    ),
                                }
                            )
                step_elapsed = perf_counter() - step_start
                total_elapsed = perf_counter() - run_start
                self._ui(f"\n{Colors.DIM}⏱️  Step {step} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){Colors.RESET}")
        except KeyboardInterrupt:
            self._cleanup_incomplete_messages(messages)
            self._ui(f"\n{Colors.BRIGHT_YELLOW}⚠️  Task cancelled by user.{Colors.RESET}")
            if draft.strip():
                return draft

        if not draft.strip():
            # Emergency fallback only; normal path should be fully agentic via tool-calling loop.
            draft = self._compose_report(papers=context_papers, tool_history=tool_history, current_draft="")

        report = self._editorial_refine(draft=draft, papers=context_papers, tool_history=tool_history)
        self._ui(f"{Colors.BRIGHT_GREEN}[TRACK] agent_loop | completed | final report ready{Colors.RESET}")
        return report

    def _estimate_chars(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for m in messages:
            total += len(str(m.get("content", "")))
            tc = m.get("tool_calls")
            if tc:
                total += len(str(tc))
        return total

    def _maybe_summarize_messages(self, messages: list[dict[str, Any]]) -> None:
        if self._estimate_chars(messages) <= self.context_char_limit:
            return
        self._ui(f"{Colors.BRIGHT_YELLOW}📊 Context too large, summarizing history...{Colors.RESET}")
        # Keep system + first user + last 12 messages, compress middle section.
        if len(messages) <= 16:
            return
        head = messages[:2]
        tail = messages[-12:]
        middle = messages[2:-12]
        summary_src = "\n".join(f"{m.get('role')}: {str(m.get('content',''))[:600]}" for m in middle[-40:])
        summary = _strip_think_blocks(
            self.llm.chat(
                system_prompt="Summarize agent execution process faithfully.",
                user_prompt=f"请总结以下执行历史，保留关键结论、工具调用结果、未解决问题。\n{summary_src}",
                temperature=0.1,
            )
        )
        messages[:] = head + [{"role": "user", "content": f"[Execution Summary]\n{summary}"}] + tail

    def _cleanup_incomplete_messages(self, messages: list[dict[str, Any]]) -> None:
        last_assistant = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                last_assistant = i
                break
        if last_assistant >= 0:
            del messages[last_assistant:]

    def _execute_tool_safe(self, call: ToolCall) -> ToolResult:
        try:
            out = self._execute_tool(call)
            return ToolResult(success=True, content=out)
        except Exception as exc:
            return ToolResult(success=False, content="", error=f"{type(exc).__name__}: {exc}")

    def _tool_schemas(self) -> list[dict[str, Any]]:
        return self.tool_registry.schemas()

    def _execute_tool(self, call: ToolCall) -> Any:
        return self.tool_registry.execute(call.tool, call.args)

    def _build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(
            name="get_skill",
            description="Load full SKILL.md content for a given skill name.",
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                },
                "required": ["skill_name"],
            },
            handler=self._tool_get_skill,
        )
        registry.register(
            name="search_arxiv",
            description="Search arXiv papers by include terms and categories.",
            parameters={
                "type": "object",
                    "properties": {
                        "include_terms": {"type": "array", "items": {"type": "string"}},
                        "categories": {"type": "array", "items": {"type": "string"}},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                "required": ["include_terms"],
            },
            handler=self._tool_search_arxiv,
        )
        registry.register(
            name="get_related_memory",
            description="Fetch related historical papers from local memory by keywords.",
            parameters={
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30},
                },
                "required": ["keywords"],
            },
            handler=self._tool_get_related_memory,
        )

        subagent_tools = {
            "paper_scout": "Subagent: cluster themes and select representative papers.",
            "baseline_comparator": "Subagent: compare target papers against same-topic baselines.",
            "insight_synthesizer": "Subagent: synthesize cross-paper insights with evidence.",
            "idea_generator": "Subagent: generate testable follow-up research ideas.",
            "reviewer": "Subagent: critique current draft and list concrete issues.",
            "reviser": "Subagent: revise draft according to critique.",
            "final_editor": "Subagent: turn draft into publication-quality Chinese final report.",
        }
        for role, desc in subagent_tools.items():
            registry.register(
                name=role,
                description=desc,
                parameters={
                    "type": "object",
                    "properties": {"focus": {"type": "string"}, "draft": {"type": "string"}, "critique": {"type": "string"}},
                },
                handler=lambda args, r=role: self._invoke_subagent(r, args),
            )

        return registry

    def _tool_get_skill(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("skill_name", "")).strip()
        if not name:
            return {"error": "skill_name is required", "available_skills": self.skill_loader.list_skills()}
        skill = self.skill_loader.get_skill(name)
        if skill is None:
            return {"error": f"skill not found: {name}", "available_skills": self.skill_loader.list_skills()}
        return {
            "skill_name": skill.name,
            "skill_path": str(skill.skill_path),
            "content": skill.to_prompt(),
        }

    def _tool_search_arxiv(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        terms = args.get("include_terms", [])
        categories = args.get("categories")
        max_results = int(args.get("max_results", 20))
        if not isinstance(terms, list):
            terms = []
        return self.toolbox.search_arxiv(
            include_terms=[str(x) for x in terms if str(x).strip()],
            categories=categories,
            max_results=max_results,
        )

    def _tool_get_related_memory(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        keywords = args.get("keywords", [])
        limit = int(args.get("limit", 12))
        if not isinstance(keywords, list):
            keywords = []
        return self.toolbox.get_related_memory([str(x) for x in keywords if str(x).strip()], limit=limit)

    def _invoke_subagent(self, role: str, args: dict[str, Any]) -> dict[str, Any]:
        role_instruction = {
            "paper_scout": "你是 paper_scout：给出主题地图与代表论文。",
            "baseline_comparator": "你是 baseline_comparator：必须给出同主题baseline差异和边界条件。",
            "insight_synthesizer": "你是 insight_synthesizer：跨论文归纳高价值洞察并附证据。",
            "idea_generator": "你是 idea_generator：给出可验证研究idea（问题/假设/实验/指标/风险）。",
            "reviewer": "你是 reviewer：严格指出草稿问题，要求具体且可执行。",
            "reviser": "你是 reviser：根据审稿意见改稿，增强证据链与可读性。",
            "final_editor": "你是 final_editor：把内容改成公众号级可读中文终稿。",
        }.get(role, "你是研究分析子agent。")

        user_prompt = (
            f"role={role}\n"
            f"args={json.dumps(args, ensure_ascii=False)}\n"
            f"papers={_short_json(self._context_papers_for_subagent, 12000)}\n"
            f"tool_history={_short_json(self._tool_history_for_subagent[-20:], 12000)}\n"
            "请输出结构化中文内容，强调证据链。"
        )
        text = _strip_think_blocks(self.llm.chat(system_prompt=role_instruction, user_prompt=user_prompt, temperature=0.2))
        return {"role": role, "content": text}

    def _review_subagent_output(self, fn: str, args: dict[str, Any], result: ToolResult) -> tuple[bool, str, str, str]:
        if not result.success:
            return False, f"tool failed: {result.error or 'unknown error'}", "tool execution failed", "fix tool args and rerun"
        prompt = (
            "你是主Agent的质量闸门。请只输出JSON："
            '{"ok": true/false, "reason": "...", "bad_case": "...", "improvement": "..."}。\n'
            "判定标准：证据充分、可读性好、不是短句堆砌、可支持最终科研日报。\n"
            f"tool={fn}\n"
            f"args={_short_json(args, 2000)}\n"
            f"result={_short_json(result.content, 5000)}"
        )
        raw = _strip_think_blocks(
            self.llm.chat(
                system_prompt="Return strict JSON only.",
                user_prompt=prompt,
                temperature=0.0,
            )
        ).strip()
        try:
            obj = json.loads(raw)
            ok = bool(obj.get("ok"))
            reason = str(obj.get("reason") or "").strip() or "no reason"
            bad_case = str(obj.get("bad_case") or "").strip() or "未提供具体片段"
            improvement = str(obj.get("improvement") or "").strip() or "请补充证据并强化结构化表达"
            return ok, reason, bad_case, improvement
        except Exception:
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                try:
                    obj = json.loads(match.group(0))
                    ok = bool(obj.get("ok"))
                    reason = str(obj.get("reason") or "").strip() or "no reason"
                    bad_case = str(obj.get("bad_case") or "").strip() or "未提供具体片段"
                    improvement = str(obj.get("improvement") or "").strip() or "请补充证据并强化结构化表达"
                    return ok, reason, bad_case, improvement
                except Exception:
                    pass
            return True, "gate parse failed; pass-through", "N/A", "N/A"

    def _compose_report(self, papers: list[dict[str, Any]], tool_history: list[dict[str, Any]], current_draft: str) -> str:
        system_prompt = "你是顶级AI研究日报编辑，请输出详细、可读、证据清晰的中文报告。"
        user_prompt = (
            "请生成最终日报。结构自由，但必须覆盖四类内容：\n"
            "1) 今天更新论文（标题+arXiv链接）\n"
            "2) 创新点与baseline差异\n"
            "3) 对领域启发\n"
            "4) 结合历史脉络的后续idea\n\n"
            "要求：段落化，少碎短句；关键结论尽量带 [paper_id]。\n"
            f"skills_context={self.skill_context[:12000]}\n"
            f"papers={_short_json(papers, 10000)}\n"
            f"tool_history={_short_json(tool_history[-12:], 10000)}\n"
            f"draft={current_draft[:4000]}"
        )
        return _strip_think_blocks(self.llm.chat(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.2))

    def _editorial_refine(self, draft: str, papers: list[dict[str, Any]], tool_history: list[dict[str, Any]]) -> str:
        current = draft
        for _ in range(max(1, self.max_editorial_rounds)):
            passed, _ = self._judge_report_ready(
                draft=current,
                papers=papers,
                tool_history=tool_history,
            )
            if passed:
                break
            system_prompt = "你是科研日报审稿改写器。"
            user_prompt = (
                "请把下面草稿改写得更详细、更好读，减少短句堆砌。\n"
                "结构可以自由，但必须覆盖四类核心内容，并保留标题+链接。\n"
                f"skills_context={self.skill_context[:8000]}\n"
                f"papers={_short_json(papers, 6000)}\n"
                f"tool_history={_short_json(tool_history[-8:], 6000)}\n"
                f"draft={current[:7000]}"
            )
            current = _strip_think_blocks(self.llm.chat(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.2))
        return current

    def _judge_report_ready(
        self,
        draft: str,
        papers: list[dict[str, Any]],
        tool_history: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        """Model-based quality gate: decide if report is ready to finalize."""
        judge_prompt = (
            "你是严格审稿人。判断这份报告是否可以作为最终版本发布。\n"
            "必须检查四项是否充分：\n"
            "1) 今日更新论文（标题+链接）\n"
            "2) 创新点与同主题baseline差异\n"
            "3) 对领域启发\n"
            "4) 后续可研究idea（有依据）\n\n"
            "输出JSON：{\"pass\": true/false, \"feedback\": \"简洁改进建议\"}\n"
            f"papers={_short_json(papers, 8000)}\n"
            f"tool_history={_short_json(tool_history[-10:], 8000)}\n"
            f"draft={draft[:15000]}"
        )
        raw = self.llm.chat(
            system_prompt="You are a strict review judge. Return JSON only.",
            user_prompt=judge_prompt,
            temperature=0.0,
        )
        # tolerant parse
        try:
            obj = json.loads(raw.strip())
        except Exception:
            m = re.search(r"\{[\s\S]*\}", raw)
            if not m:
                return False, "评审输出解析失败，请补充关键内容并重写。"
            try:
                obj = json.loads(m.group(0))
            except Exception:
                return False, "评审输出解析失败，请补充关键内容并重写。"
        passed = bool(obj.get("pass", False))
        feedback = str(obj.get("feedback", "")).strip() or ("可发布" if passed else "内容尚不充分")
        return passed, feedback

    def _fallback_report(self, papers: list[Paper]) -> str:
        lines = [
            "# Daily Paper Agent Report",
            f"生成时间：{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
            "",
            "## 今天更新了哪些论文",
            "| 标题 | arXiv链接 | 一句话贡献 |",
            "|---|---|---|",
        ]
        for p in papers[:20]:
            lines.append(f"| {p.title} | {p.link} | {p.summary[:100]}... |")

        lines += [
            "",
            "## 创新点与baseline差异",
            "未配置 LLM，当前仅输出论文列表。",
            "",
            "## 对领域启发",
            "未配置 LLM，当前仅输出论文列表。",
            "",
            "## 后续可做的研究idea（结合历史脉络）",
            "未配置 LLM，当前仅输出论文列表。",
        ]
        return "\n".join(lines)
