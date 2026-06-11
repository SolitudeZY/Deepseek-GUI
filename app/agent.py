import json
import threading
from typing import Callable, Optional

# Lazy imports — these are heavy and slow down startup
OpenAI = None  # will be imported on first use

from app.tools import TOOLS_SCHEMA, CONFIRM_REQUIRED, dispatch
from app.advanced_tools import (
    ADVANCED_TOOLS_SCHEMA, TodoManager, TaskManager, BackgroundManager,
    microcompact, auto_compact, estimate_tokens, run_subagent, run_rlm,
)
from app.team import TEAM, WORKTREES, BUS
from app.skills import skill_list, skill_list_str, skill_read, memory_read, memory_write


def _get_openai():
    global OpenAI
    if OpenAI is None:
        from openai import OpenAI as _OpenAI
        OpenAI = _OpenAI
    return OpenAI

# Token threshold for auto-compact (approx)
AUTO_COMPACT_THRESHOLD = 600_000
# Legacy V4 threshold (kept for reference, now overridden by per-model config)
AUTO_COMPACT_THRESHOLD_V4 = 800_000

V4_MODELS = {"deepseek-v4-pro", "deepseek-v4-flash"}



class _Callbacks:
    """Simple namespace to bundle callbacks."""
    __slots__ = ('on_token', 'on_tool_start', 'on_tool_result', 'on_confirm',
                 'on_done', 'on_error', 'on_todo_update', 'on_context_update',
                 'on_thinking', 'on_usage', 'on_ask_user')

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _StreamResult:
    """Result of streaming and parsing one LLM round."""
    __slots__ = ('assistant_msg', 'tool_calls', 'provider')

    def __init__(self, assistant_msg, tool_calls, provider):
        self.assistant_msg = assistant_msg
        self.tool_calls = tool_calls
        self.provider = provider


class Agent:
    """
    封装 OpenAI 兼容 API 的工具调用循环。
    集成 TodoWrite、TaskManager、BackgroundManager、上下文压缩。
    """

    CONTEXT_WINDOW = 40

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        system_prompt: str = "You are a helpful assistant.",
        search_config: dict = None,
        command_safety: str = "confirm",
        command_timeout: int = 30,
        todo_manager: Optional[TodoManager] = None,
        task_manager: Optional[TaskManager] = None,
        bg_manager: Optional[BackgroundManager] = None,
        thinking: str = "off",
        max_rounds: int = 50,
        search_enabled: bool = True,
        compact_threshold: int = 0,
        context_length: int = 0,
        vision_config: dict = None,
    ):
        self.model = model
        self.search_config = search_config or {}
        self.vision_config = vision_config or {}
        self.command_safety = command_safety
        self.command_timeout = command_timeout
        self.thinking = thinking  # "off" | "high" | "max"
        self.max_rounds = max_rounds
        self.search_enabled = search_enabled
        # Per-model context config (0 = use defaults)
        self.context_length = context_length or (1_000_000 if model in V4_MODELS else 1_000_000)
        self.compact_threshold = compact_threshold or AUTO_COMPACT_THRESHOLD
        self.search_enabled = search_enabled
        self._model_configs: list = []
        self._client = _get_openai()(api_key=api_key, base_url=base_url)
        self._base_url = (base_url or "").rstrip("/")
        self._stop_flag = threading.Event()
        self._todo = todo_manager or TodoManager()
        self._tasks = task_manager or TaskManager()
        self._bg = bg_manager or BackgroundManager()
        self._rounds_without_todo = 0

        # Build stable system prompt with skill index (appended once, never changes
        # per-round, so the prefix stays cache-friendly).
        self.system_prompt = self._build_system_prompt(system_prompt)

        # Tool dispatch registry (replaces if-elif chain)
        self._tool_handlers = self._build_tool_handlers()

    @staticmethod
    def _build_system_prompt(base_prompt: str) -> str:
        """Append environment info and skill index to system prompt.

        The index is built once at agent creation. Because it's part of the system
        message (always the first message), it forms a stable prefix that DeepSeek
        can cache across rounds.
        """
        import platform
        # Inject environment context so the model knows tools run on user's machine
        env_block = (
            "\n\n<environment>\n"
            f"操作系统：{platform.system()} {platform.release()}\n"
            "你拥有的工具（如 run_command、read_file、write_file 等）直接在用户的本地电脑上执行，"
            "而非沙箱或远程环境。你可以直接操作用户的文件系统和运行命令。\n"
            "</environment>"
        )
        prompt = base_prompt + env_block

        skills = skill_list()
        if not skills:
            return prompt
        lines = [f"- {s['name']}: {s['description']}" for s in skills]
        skill_block = (
            "\n\n<available_skills>\n"
            "你有以下技能可用。当用户的请求明确匹配某个技能的描述时，"
            "请先调用 skill_read 获取该技能的完整指令，然后严格按照指令执行。\n"
            + "\n".join(lines)
            + "\n</available_skills>"
        )
        return prompt + skill_block

    def _provider(self) -> str:
        """Detect provider from base_url."""
        url = self._base_url.lower()
        if "deepseek" in url:
            return "deepseek"
        if "anthropic" in url or "claude" in url:
            return "anthropic"
        return "openai"

    def _is_reasoner(self) -> bool:
        """True when this call should use extended thinking / reasoning."""
        if self.thinking == "off":
            return False
        p = self._provider()
        if p == "deepseek":
            return True
        if p in ("openai", "anthropic"):
            return True
        return False

    def _build_stream(self, messages: list) -> tuple:
        """Return (stream, provider). Handles provider-specific params.
        If the request is blocked (content filter), retries without tools.
        """
        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        provider = self._provider()

        if self._is_reasoner():
            effort = "high" if self.thinking == "high" else "high"
            if provider == "deepseek":
                kwargs["reasoning_effort"] = effort
                kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
                kwargs["tools"] = self._all_tools()
                kwargs["tool_choice"] = "auto"
            elif provider == "openai":
                kwargs["extra_body"] = {"reasoning_effort": effort}
                kwargs["tools"] = self._all_tools()
                kwargs["tool_choice"] = "auto"
            elif provider == "anthropic":
                budget = 32000 if self.thinking == "max" else 8000
                kwargs["extra_body"] = {"thinking": {"type": "enabled", "budget_tokens": budget}}
                kwargs["tools"] = self._all_tools()
                kwargs["tool_choice"] = "auto"
        else:
            kwargs["tools"] = self._all_tools()
            kwargs["tool_choice"] = "auto"

        try:
            return self._client.chat.completions.create(**kwargs), provider
        except Exception as e:
            err_msg = str(e).lower()
            # If blocked by content filter or tools not supported, retry without tools
            if any(kw in err_msg for kw in ("blocked", "content_filter", "invalid_tool", "not support")):
                kwargs.pop("tools", None)
                kwargs.pop("tool_choice", None)
                # Strip tool_calls and tool messages from history for compatibility
                kwargs["messages"] = self._strip_tool_messages(kwargs["messages"])
                return self._client.chat.completions.create(**kwargs), provider
            raise

    @staticmethod
    def _strip_tool_messages(messages: list[dict]) -> list[dict]:
        """Remove tool-related content from messages for providers that don't support tools."""
        cleaned = []
        for m in messages:
            if m.get("role") == "tool":
                continue
            if m.get("role") == "assistant" and m.get("tool_calls"):
                # Keep the message but remove tool_calls, keep content only
                cleaned_msg = {"role": "assistant", "content": m.get("content") or ""}
                cleaned.append(cleaned_msg)
            else:
                cleaned.append(m)
        return cleaned

    def stop(self):
        self._stop_flag.set()

    def reset_stop(self):
        self._stop_flag.clear()

    @property
    def todo(self) -> TodoManager:
        return self._todo

    def _all_tools(self) -> list:
        """Return tool schemas. Cached for prefix stability — never changes mid-session."""
        if not hasattr(self, '_cached_tools'):
            tools = TOOLS_SCHEMA + ADVANCED_TOOLS_SCHEMA
            if not self.search_enabled:
                tools = [t for t in tools if t.get("function", {}).get("name") not in ("web_search", "web_read")]
            # Sort deterministically so JSON serialization is byte-stable across turns
            tools = sorted(tools, key=lambda t: t.get("function", {}).get("name", ""))
            self._cached_tools = tools
        return self._cached_tools

    def _dispatch_advanced(self, tool_name: str, args: dict) -> Optional[str]:
        """Handle advanced tools via registry. Returns None if not an advanced tool."""
        handler = self._tool_handlers.get(tool_name)
        if handler is None:
            return None
        return handler(args)

    def _build_tool_handlers(self) -> dict:
        """Build tool name -> handler mapping."""
        return {
            "todo_write": self._handle_todo_write,
            "task_create": lambda a: self._tasks.create(a.get("subject", ""), a.get("description", "")),
            "task_get": lambda a: self._tasks.get(int(a.get("task_id", 0))),
            "task_update": lambda a: self._tasks.update(
                int(a.get("task_id", 0)), a.get("status"),
                a.get("add_blocked_by"), a.get("remove_blocked_by")),
            "task_list": lambda a: self._tasks.list_all(),
            "background_run": lambda a: self._bg.run(a.get("command", ""), int(a.get("timeout", 120))),
            "background_check": lambda a: self._bg.check(a.get("task_id")),
            "subagent": lambda a: run_subagent(
                prompt=a.get("prompt", ""),
                api_key=self._client.api_key,
                base_url=str(self._client.base_url),
                model=self.model,
                agent_type=a.get("agent_type", "Explore")),
            "rlm_query": self._handle_rlm_query,
            "team_spawn": self._handle_team_spawn,
            "team_list": lambda a: TEAM.list_all(),
            "team_send": lambda a: BUS.send("lead", a.get("to", ""), a.get("content", ""), a.get("msg_type", "message")),
            "team_read_inbox": self._handle_team_read_inbox,
            "team_broadcast": lambda a: BUS.broadcast("lead", a.get("content", ""), TEAM.member_names()),
            "team_approve_plan": lambda a: TEAM.approve_plan(a.get("request_id", ""), bool(a.get("approve", False))),
            "team_shutdown": lambda a: TEAM.shutdown(a.get("name", "")),
            "worktree_create": lambda a: WORKTREES.create(a.get("name", ""), a.get("task_id"), a.get("base_ref", "HEAD")),
            "worktree_list": lambda a: WORKTREES.list_all(),
            "worktree_run": lambda a: WORKTREES.run(a.get("name", ""), a.get("command", "")),
            "worktree_status": lambda a: WORKTREES.status(a.get("name", "")),
            "worktree_keep": lambda a: WORKTREES.keep(a.get("name", "")),
            "worktree_remove": lambda a: WORKTREES.remove(a.get("name", ""), bool(a.get("force", False)), bool(a.get("complete_task", False))),
            "worktree_events": lambda a: WORKTREES.events(a.get("limit", 20)),
            "skill_list": lambda a: skill_list_str(),
            "skill_read": lambda a: skill_read(a.get("name", "")),
            "memory_read": lambda a: memory_read(a.get("key", "")),
            "memory_write": lambda a: memory_write(a.get("key", ""), a.get("content", "")),
        }

    def _handle_todo_write(self, args: dict) -> str:
        try:
            return self._todo.update(args.get("items", []))
        except ValueError as e:
            return f"TodoWrite 错误：{e}"

    def _handle_rlm_query(self, args: dict) -> str:
        flash_model = "deepseek-v4-flash"
        rlm_api_key = self._client.api_key
        rlm_base_url = str(self._client.base_url)
        if self._model_configs:
            flash_mc = next((c for c in self._model_configs if "flash" in c.get("model", "").lower()), None)
            if flash_mc:
                rlm_api_key = flash_mc.get("api_key") or rlm_api_key
                rlm_base_url = flash_mc.get("base_url") or rlm_base_url
                flash_model = flash_mc.get("model") or flash_model
        return run_rlm(
            prompts=args.get("prompts", []),
            api_key=rlm_api_key,
            base_url=rlm_base_url,
            model=flash_model,
            system_prompt=args.get("system_prompt", ""),
        )

    def _handle_team_spawn(self, args: dict) -> str:
        mc_name = args.get("model_config", "")
        if mc_name and self._model_configs:
            mc = next((c for c in self._model_configs if c.get("name") == mc_name), None)
        else:
            mc = None
        api_key = mc["api_key"] if mc else self._client.api_key
        base_url = mc["base_url"] if mc else str(self._client.base_url)
        model = mc["model"] if mc else self.model
        return TEAM.spawn(
            name=args.get("name", ""),
            role=args.get("role", ""),
            prompt=args.get("prompt", ""),
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    def _handle_team_read_inbox(self, args: dict) -> str:
        msgs = BUS.read_inbox("lead")
        return json.dumps(msgs, ensure_ascii=False, indent=2) if msgs else "收件箱为空。"

    def _apply_window(self, messages: list[dict]) -> list[dict]:
        system = [m for m in messages if m.get("role") == "system"]
        rest = [m for m in messages if m.get("role") != "system"]
        if len(rest) <= self.CONTEXT_WINDOW:
            return messages
        window = rest[-self.CONTEXT_WINDOW:]
        # Drop leading tool results (orphaned from truncated tool_calls)
        while window and window[0].get("role") == "tool":
            window = window[1:]
        # Drop leading assistant messages that have tool_calls but no preceding tool results
        # (their tool results were cut off by the window)
        while window and window[0].get("role") == "assistant" and window[0].get("tool_calls"):
            window = window[1:]
        # After dropping, there may again be orphaned tool results at the front
        while window and window[0].get("role") == "tool":
            window = window[1:]
        return system + window

    def run(
        self,
        messages: list[dict],
        on_token: Callable[[str], None],
        on_tool_start: Callable[[str, dict], None],
        on_tool_result: Callable[[str, str], None],
        on_confirm: Callable[[str, dict], bool],
        on_done: Callable[[list[dict]], None],
        on_error: Callable[[str, list], None],
        on_todo_update: Optional[Callable[[list[dict]], None]] = None,
        on_context_update: Optional[Callable[[int, int], None]] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_usage: Optional[Callable[[dict], None]] = None,
        on_ask_user: Optional[Callable[[dict], str]] = None,
    ):
        """在调用线程中同步运行（应在后台线程调用）。"""
        self._stop_flag.clear()
        self._rounds_without_todo = 0
        all_messages = [{"role": "system", "content": self.system_prompt}] + messages

        cb = _Callbacks(
            on_token=on_token, on_tool_start=on_tool_start,
            on_tool_result=on_tool_result, on_confirm=on_confirm,
            on_done=on_done, on_error=on_error,
            on_todo_update=on_todo_update, on_context_update=on_context_update,
            on_thinking=on_thinking, on_usage=on_usage, on_ask_user=on_ask_user,
        )

        session_usage = {
            "prompt_tokens": 0, "completion_tokens": 0,
            "cache_hit_tokens": 0, "cache_miss_tokens": 0,
        }

        try:
            round_count = 0
            search_count = 0
            SEARCH_SOFT_LIMIT = 5
            threshold = self.compact_threshold

            while not self._stop_flag.is_set() and round_count < self.max_rounds:
                all_messages = self._inject_context(all_messages)
                all_messages = self._manage_context(all_messages, threshold, cb)
                full_messages = self._prepare_messages(all_messages)

                result = self._stream_and_parse(full_messages, cb, session_usage)
                round_count += 1

                all_messages.append(result.assistant_msg)

                if not result.tool_calls:
                    break

                search_count = self._execute_tools(
                    result.tool_calls, all_messages, cb,
                    search_count, SEARCH_SOFT_LIMIT, on_ask_user,
                )

                self._check_todo_nag(all_messages)

            # If stopped mid-tool-call, append stub tool results to keep history valid
            if all_messages and all_messages[-1].get("role") == "assistant" and all_messages[-1].get("tool_calls"):
                for tc in all_messages[-1]["tool_calls"]:
                    all_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": "用户已停止",
                    })

            cb.on_done(all_messages[1:])

        except Exception as e:
            on_error(str(e), all_messages[1:])

    def _inject_context(self, all_messages: list[dict]) -> list[dict]:
        """Inject background notifications and team inbox messages."""
        notes = self._bg.drain_notifications()
        for note in notes:
            all_messages.append({
                "role": "user",
                "content": f"<bg_notification>后台任务 {note['task_id']} 已完成：{note['result']}</bg_notification>",
            })

        from app.team import BUS as _BUS
        inbox_msgs = _BUS.read_inbox("lead")
        for im in inbox_msgs:
            all_messages.append({
                "role": "user",
                "content": f"<team_inbox>来自 {im.get('from','?')} 的消息：{im.get('content','')}</team_inbox>",
            })
        return all_messages

    def _manage_context(self, all_messages: list[dict], threshold: int, cb) -> list[dict]:
        """Apply microcompact and auto_compact, push context usage."""
        microcompact(all_messages, self.CONTEXT_WINDOW)
        if estimate_tokens(all_messages) > threshold:
            all_messages = auto_compact(all_messages, self._client, self.model)
        if cb.on_context_update:
            cb.on_context_update(estimate_tokens(all_messages), threshold)
        return all_messages

    def _prepare_messages(self, all_messages: list[dict]) -> list[dict]:
        """Apply window and provider-specific patches."""
        # Sanitize: if last assistant msg has tool_calls without matching tool results, add stubs
        if all_messages and all_messages[-1].get("role") == "assistant" and all_messages[-1].get("tool_calls"):
            tc_ids = {tc.get("id") for tc in all_messages[-1]["tool_calls"]}
            # Check if tool results follow
            has_results = False
            for m in all_messages[all_messages.index(all_messages[-1]) + 1:]:
                if m.get("role") == "tool" and m.get("tool_call_id") in tc_ids:
                    has_results = True
                    break
            if not has_results:
                for tc in all_messages[-1]["tool_calls"]:
                    all_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": "用户已停止",
                    })
        full_messages = self._apply_window(all_messages)
        if self._is_reasoner() and self._provider() == "deepseek":
            full_messages = [
                {**msg, "reasoning_content": msg.get("reasoning_content") or ""}
                if msg.get("role") == "assistant" else msg
                for msg in full_messages
            ]
        elif not self._is_reasoner() and self._provider() == "deepseek":
            full_messages = [
                {k: v for k, v in msg.items() if k != "reasoning_content"}
                if msg.get("role") == "assistant" else msg
                for msg in full_messages
            ]
        return full_messages

    def _stream_and_parse(self, full_messages: list[dict], cb, session_usage: dict) -> _StreamResult:
        """Stream LLM response and parse into content + tool calls."""
        assistant_content = ""
        thinking_content = ""
        round_usage = None

        stream, provider = self._build_stream(full_messages)
        current_tool_calls: dict[int, dict] = {}

        for chunk in stream:
            if self._stop_flag.is_set():
                break
            if hasattr(chunk, 'usage') and chunk.usage:
                round_usage = chunk.usage
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                thinking_content += rc
                if cb.on_thinking:
                    cb.on_thinking(rc)
            if delta.content:
                assistant_content += delta.content
                cb.on_token(delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in current_tool_calls:
                        current_tool_calls[idx] = {
                            "id": "", "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    if tc.id:
                        current_tool_calls[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            current_tool_calls[idx]["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            current_tool_calls[idx]["function"]["arguments"] += tc.function.arguments

        # Push usage stats
        if round_usage and cb.on_usage:
            pt = getattr(round_usage, 'prompt_tokens', 0) or 0
            ct = getattr(round_usage, 'completion_tokens', 0) or 0
            ch = getattr(round_usage, 'prompt_cache_hit_tokens', 0) or 0
            cm = getattr(round_usage, 'prompt_cache_miss_tokens', 0) or 0
            session_usage["prompt_tokens"] += pt
            session_usage["completion_tokens"] += ct
            session_usage["cache_hit_tokens"] += ch
            session_usage["cache_miss_tokens"] += cm
            cb.on_usage({
                "round": {"prompt": pt, "completion": ct, "cache_hit": ch, "cache_miss": cm},
                "session": dict(session_usage),
            })

        tool_calls_accumulated = list(current_tool_calls.values())

        assistant_msg: dict = {"role": "assistant", "content": assistant_content}
        if self._is_reasoner() and provider == "deepseek":
            assistant_msg["reasoning_content"] = thinking_content
        if tool_calls_accumulated:
            assistant_msg["tool_calls"] = tool_calls_accumulated

        return _StreamResult(
            assistant_msg=assistant_msg,
            tool_calls=tool_calls_accumulated,
            provider=provider,
        )

    def _execute_tools(
        self, tool_calls: list[dict], all_messages: list[dict],
        cb, search_count: int, search_soft_limit: int, on_ask_user,
    ) -> int:
        """Execute tool calls and append results to messages. Returns updated search_count."""
        used_todo = False
        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}

            if self._stop_flag.is_set():
                all_messages.append({
                    "role": "tool", "tool_call_id": tc["id"],
                    "content": "用户已停止",
                })
                continue

            cb.on_tool_start(tool_name, args)

            # Manual compact
            if tool_name == "compact":
                all_messages.append({
                    "role": "tool", "tool_call_id": tc["id"],
                    "content": "正在压缩上下文…",
                })
                compact_result = auto_compact(all_messages, self._client, self.model)
                all_messages.clear()
                all_messages.extend(compact_result)
                cb.on_tool_result(tool_name, "上下文已压缩")
                continue

            # ask_user_question
            if tool_name == "ask_user_question" and on_ask_user:
                answer = on_ask_user(args)
                result = answer or "用户未回答"
                cb.on_tool_result(tool_name, result)
                all_messages.append({
                    "role": "tool", "tool_call_id": tc["id"], "content": result,
                })
                continue

            # enter_plan_mode
            if tool_name == "enter_plan_mode":
                result = "已进入计划模式。请逐步输出你的实现计划，每个关键决策点使用 ask_user_question 工具询问用户意见，确认后再继续下一步。所有步骤确认完毕后调用 exit_plan_mode 表示计划完成。"
                cb.on_tool_result(tool_name, result)
                all_messages.append({
                    "role": "tool", "tool_call_id": tc["id"], "content": result,
                })
                continue

            # exit_plan_mode
            if tool_name == "exit_plan_mode":
                result = "计划已完成，所有步骤已经用户确认。开始执行。"
                cb.on_tool_result(tool_name, result)
                all_messages.append({
                    "role": "tool", "tool_call_id": tc["id"], "content": result,
                })
                continue

            # Try advanced tools (registry)
            result = self._dispatch_advanced(tool_name, args)
            if result is None:
                # Basic tools — may need confirmation
                from app.config import is_command_allowed
                if tool_name in CONFIRM_REQUIRED:
                    if self.command_safety == "disabled":
                        result = f"命令执行已禁用（disabled 模式），拒绝执行：{tool_name}"
                    elif self.command_safety in ("confirm", "auto_countdown"):
                        if not is_command_allowed(args.get("command", "")):
                            allowed = cb.on_confirm(tool_name, args)
                            result = (dispatch(tool_name, args, self.search_config, self.command_timeout, self._stop_flag, vision_config=self.vision_config)
                                      if allowed else f"用户拒绝执行工具：{tool_name}")
                        else:
                            result = dispatch(tool_name, args, self.search_config, self.command_timeout, self._stop_flag, vision_config=self.vision_config)
                    else:
                        # auto mode — execute directly
                        result = dispatch(tool_name, args, self.search_config, self.command_timeout, self._stop_flag, vision_config=self.vision_config)
                else:
                    result = dispatch(tool_name, args, self.search_config, self.command_timeout, self._stop_flag, vision_config=self.vision_config)

            if tool_name == "todo_write":
                used_todo = True
                if cb.on_todo_update:
                    cb.on_todo_update(self._todo.get_items())

            # Search soft limit
            if tool_name == "web_search":
                search_count += 1
                if search_count >= search_soft_limit:
                    result += f"\n\n⚠ 你已经搜索了 {search_count} 次。请根据已有结果整理回答，检查是否需要继续搜索，如无必要，请整理现有内容并作出回答。"

            cb.on_tool_result(tool_name, result)
            all_messages.append({
                "role": "tool", "tool_call_id": tc["id"], "content": result,
            })

        self._rounds_without_todo = 0 if used_todo else self._rounds_without_todo + 1
        return search_count

    def _check_todo_nag(self, all_messages: list[dict]):
        """Remind model to update todos if it has open items."""
        if self._todo.has_open_items() and self._rounds_without_todo >= 3:
            all_messages.append({
                "role": "user",
                "content": "<reminder>请更新你的 todo_write 清单。</reminder>",
            })
            self._rounds_without_todo = 0
