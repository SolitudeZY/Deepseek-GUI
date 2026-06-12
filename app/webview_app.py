import json
import os
import threading
import webbrowser
import webview
from pathlib import Path
from typing import Optional

from app.config import (
    load_config, save_config, get_active_model_config,
    load_allowed_commands, save_allowed_commands, is_command_allowed, add_allowed_command,
    APP_VERSION, GITHUB_REPO, IS_WIN,
)
from app.conversation import (
    new_conversation, save_conversation, load_conversation,
    delete_conversation, rename_conversation, list_conversations,
    update_sort_orders, auto_title_from_message, export_conversation_md,
    import_conversation_from_file,
)
from app.sync import (
    upload_conversation, upload_all_conversations,
    detect_new_conversations, import_from_sync, get_sync_dir,
    upload_config, detect_config_updates, import_config,
    sync_all, import_all,
)
from app.tools import read_file as _read_file
from app.vision import is_image, describe_image
from app.skills import skill_list, skill_save, skill_delete, skill_read, memory_list, memory_read, memory_write, skill_import_from_path

# Lazy-loaded heavy modules (deferred to first use for faster startup)
_agent_module = None
_team_module = None
_advanced_tools_module = None


def _lazy_agent():
    global _agent_module
    if _agent_module is None:
        import app.agent as _m
        _agent_module = _m
    return _agent_module


def _lazy_team():
    global _team_module
    if _team_module is None:
        import app.team as _m
        _team_module = _m
    return _team_module


def _lazy_advanced_tools():
    global _advanced_tools_module
    if _advanced_tools_module is None:
        import app.advanced_tools as _m
        _advanced_tools_module = _m
    return _advanced_tools_module


def get_static_dir() -> Path:
    import sys, os
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS) / 'app'
    else:
        base = Path(os.path.dirname(os.path.abspath(__file__)))
    return base / 'static'


def get_html_path() -> str:
    return str(get_static_dir() / 'index.html')


class API:
    def __init__(self):
        self._window: Optional[webview.Window] = None
        self._config = load_config()
        self._agent = None
        self._running = False
        self._confirm_event = threading.Event()
        self._confirm_result = False
        self._ask_event = threading.Event()
        self._ask_answer = ""
        self._plan_event = threading.Event()
        self._plan_approved = False
        # Shared managers — lazy init on first send
        self._todo = None
        self._tasks = None
        self._bg = None
        # Persist thinking/search state from config
        thinking_val = self._config.get("thinking", "high")
        # Migrate old bool values
        if thinking_val is True:
            thinking_val = "high"
        elif thinking_val is False:
            thinking_val = "off"
        self._thinking = thinking_val  # "off" | "high" | "max"
        self._search_mode = self._config.get("search_mode", "auto")    # "auto" | "manual"
        self._search_enabled = bool(self._config.get("search_enabled", True))
        # Track command prefix approvals for wildcard suggestion
        self._cmd_prefix_counts: dict[str, int] = {}
        self._debate_stop = False
        self._team_initialized = False
        self._window_visible = True  # tracks page visibility from JS

    def _ensure_managers(self):
        """Lazily initialize heavy managers on first use."""
        if self._todo is None:
            at = _lazy_advanced_tools()
            self._todo = at.TodoManager()
            self._tasks = at.TaskManager()
            self._bg = at.BackgroundManager()
        if not self._team_initialized:
            self._team_initialized = True
            _lazy_team().TEAM.set_notification_cb(
                lambda msg: self._js(f'Chat.showTeamNotification({json.dumps(msg)})')
            )

    def set_window(self, window: webview.Window):
        self._window = window

    def _js(self, code: str):
        """Thread-safe evaluate_js."""
        if self._window:
            self._window.evaluate_js(code)

    def _is_window_focused(self) -> bool:
        """Check if the app window is currently visible/focused.
        Reads the flag set by JS visibilitychange event.
        """
        return self._window_visible

    def set_window_visible(self, visible: bool) -> None:
        """Called from JS when page visibility changes."""
        self._window_visible = visible

    def _notify_system(self, title: str, message: str):
        """Send OS-level notification if window is not focused."""
        if self._is_window_focused():
            return
        threading.Thread(target=self._do_notify, args=(title, message), daemon=True).start()

    @staticmethod
    def _do_notify(title: str, message: str):
        """Actually send the OS notification (runs in background thread)."""
        try:
            if IS_WIN:
                # Use WinRT Toast with PowerShell's registered AppID
                safe_title = title.replace("'", "''").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                safe_msg = message.replace("'", "''").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                ps_script = f'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] > $null
$template = @"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>{safe_title}</text>
      <text>{safe_msg}</text>
    </binding>
  </visual>
</toast>
"@
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$appId = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
'''
                import subprocess
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=0x08000000,  # CREATE_NO_WINDOW
                )
            else:
                # macOS: osascript notification
                import subprocess
                subprocess.Popen(
                    ["osascript", "-e",
                     f'display notification "{message}" with title "{title}"'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass  # notification is best-effort

    # ── Config ────────────────────────────────────────────────────
    def get_config(self) -> dict:
        return self._config

    def save_config(self, config: dict) -> None:
        self._config = config
        save_config(config)

    # ── Conversations ─────────────────────────────────────────────
    def list_conversations(self) -> list:
        return list_conversations()

    def new_conversation(self) -> dict:
        mc = get_active_model_config(self._config)
        conv = new_conversation(mc['name'] if mc else '')
        save_conversation(conv)
        return {'id': conv['id'], 'title': conv['title']}

    def open_conversation(self, conv_id: str) -> Optional[dict]:
        conv = load_conversation(conv_id)
        if not conv:
            return None
        return {
            'id': conv['id'],
            'title': conv.get('title', '对话'),
            'messages': conv.get('messages', []),
            'file_ops': conv.get('file_ops', []),
        }

    def delete_conversation(self, conv_id: str) -> None:
        delete_conversation(conv_id)

    def rename_conversation(self, conv_id: str, title: str) -> None:
        rename_conversation(conv_id, title)

    def reorder_conversations(self, ids: list) -> None:
        update_sort_orders(ids)

    def search_conversations(self, keyword: str) -> list:
        """Search conversations by title and message content. Returns matching conv summaries."""
        from app.conversation import get_conversations_dir
        kw = keyword.lower().strip()
        if not kw:
            return []
        results = []
        for p in get_conversations_dir().glob("conv_*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                title = data.get("title", "")
                if kw in title.lower():
                    results.append({"id": data["id"], "title": title, "match": "title"})
                    continue
                # Search in message content
                for msg in data.get("messages", []):
                    content = msg.get("content", "") or ""
                    if kw in content.lower():
                        # Extract a snippet around the match
                        idx = content.lower().index(kw)
                        start = max(0, idx - 20)
                        end = min(len(content), idx + len(kw) + 40)
                        snippet = content[start:end].replace("\n", " ")
                        if start > 0:
                            snippet = "…" + snippet
                        if end < len(content):
                            snippet = snippet + "…"
                        results.append({"id": data["id"], "title": title, "match": "content", "snippet": snippet})
                        break
            except Exception:
                continue
        return results

    def set_thinking(self, level: str) -> None:
        """level: 'off' | 'high' | 'max'"""
        if level not in ("off", "high", "max"):
            level = "high"
        self._thinking = level
        self._config["thinking"] = self._thinking
        save_config(self._config)

    def get_ui_state(self) -> dict:
        """Return persistent UI toggle states for frontend init."""
        return {
            "thinking": self._thinking,
            "search_mode": self._search_mode,
            "search_enabled": self._search_enabled,
        }

    def set_search_mode(self, mode: str) -> None:
        """mode: 'auto' | 'manual'"""
        self._search_mode = mode
        self._config["search_mode"] = mode
        save_config(self._config)

    def set_search_enabled(self, enabled: bool) -> None:
        """Manual mode: toggle whether web_search tool is available."""
        self._search_enabled = bool(enabled)
        self._config["search_enabled"] = self._search_enabled
        save_config(self._config)

    def open_url(self, url: str) -> None:
        webbrowser.open(url)

    def open_file_location(self, path: str) -> None:
        """Open file in system default app, or reveal in file manager."""
        import subprocess as _sp
        import platform as _plat
        p = Path(path)
        if _plat.system() == "Darwin":
            if p.exists():
                if p.is_dir():
                    _sp.Popen(['open', str(p)])
                else:
                    _sp.Popen(['open', '-R', str(p)])
            else:
                parent = p.parent
                if parent.exists():
                    _sp.Popen(['open', str(parent)])
        else:
            if p.exists():
                if p.is_dir():
                    _sp.Popen(['explorer', str(p)])
                else:
                    _sp.Popen(['explorer', '/select,', str(p)])
            else:
                parent = p.parent
                if parent.exists():
                    _sp.Popen(['explorer', str(parent)])

    def _build_search_config(self) -> dict:
        """Assemble search config dict from self._config for Agent."""
        return {
            "engine": self._config.get("search_engine", "tavily"),
            "fallback": self._config.get("search_fallback", True),
            "tavily_api_key": self._config.get("tavily_api_key", ""),
            "brave_api_key": self._config.get("brave_api_key", ""),
            "firecrawl_api_key": self._config.get("firecrawl_api_key", ""),
            "google_api_key": self._config.get("google_api_key", ""),
            "google_cx": self._config.get("google_cx", ""),
            "searxng_url": self._config.get("searxng_url", ""),
        }

    def _build_vision_config(self) -> dict:
        """Assemble vision config dict from self._config for the analyze_image tool."""
        return {
            "vision_api_key": self._config.get("vision_api_key", ""),
            "vision_base_url": self._config.get("vision_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            "vision_model": self._config.get("vision_model", "qwen-vl-max"),
        }

    # ── Skills ────────────────────────────────────────────────────
    def list_skills(self) -> list:
        return skill_list()

    def save_skill(self, name: str, description: str, content: str) -> str:
        return skill_save(name, description, content)

    def delete_skill(self, name: str) -> str:
        return skill_delete(name)

    def read_skill(self, name: str) -> str:
        return skill_read(name)

    def import_skill(self) -> list:
        """Open a folder picker and import Claude-style skill(s) from the selected path."""
        result = self._window.create_file_dialog(
            webview.FileDialog.FOLDER,
            directory='',
        )
        if not result:
            return []
        folder = result[0] if isinstance(result, (list, tuple)) else result
        return skill_import_from_path(folder)

    # ── Memory ────────────────────────────────────────────────────
    def list_memory(self) -> list:
        return memory_list()

    def read_memory(self, key: str) -> str:
        return memory_read(key)

    def write_memory(self, key: str, content: str) -> str:
        return memory_write(key, content)

    def get_memory_summary(self) -> str:
        """Return all memory content concatenated, for injection on /new."""
        items = memory_list()
        if not items:
            return ""
        parts = []
        for item in items:
            content = memory_read(item['key'])
            parts.append(f"## {item['key']}\n{content}")
        return "\n\n".join(parts)

    # ── Worktree ─────────────────────────────────────────────────
    def get_worktrees(self) -> list:
        """Return worktree list for frontend panel."""
        idx = _lazy_team().WORKTREES._load_index()
        return idx.get("worktrees", [])

    def export_conversation(self, conv_id: str) -> None:
        conv = load_conversation(conv_id)
        if not conv:
            return
        md = export_conversation_md(conv)
        save_path = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=f"{conv.get('title', 'conversation')}.md",
            file_types=('Markdown (*.md)', 'All files (*.*)')
        )
        if save_path:
            dest = save_path[0] if isinstance(save_path, (list, tuple)) else save_path
            Path(dest).write_text(md, encoding='utf-8')

    def import_conversation(self) -> Optional[dict]:
        """打开文件选择对话框，导入 .json 或 .md 对话文件。"""
        file_path = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=('对话文件 (*.json;*.md)', 'JSON (*.json)', 'Markdown (*.md)', 'All files (*.*)')
        )
        if not file_path:
            return None
        path = file_path[0] if isinstance(file_path, (list, tuple)) else file_path
        conv = import_conversation_from_file(path)
        if conv:
            return {"id": conv["id"], "title": conv["title"]}
        return None

    def get_context_usage(self, conv_id: str) -> dict:
        """计算指定对话的上下文 token 使用量。"""
        conv = load_conversation(conv_id)
        if not conv:
            return {"used": 0, "total": 600000}
        messages = conv.get("messages", [])
        used = _lazy_advanced_tools().estimate_tokens(messages)
        # 根据当前活跃模型的配置决定阈值
        active_mc = get_active_model_config(self._config)
        total = 600000
        if active_mc:
            total = active_mc.get("compact_threshold", 0) or _lazy_agent().AUTO_COMPACT_THRESHOLD
        return {"used": used, "total": total}

    # ── File helpers ──────────────────────────────────────────────
    def save_uploaded_file(self, filename: str, base64_content: str) -> str:
        """将 JS 传来的 base64 文件保存到本地 uploads 目录，返回本地路径。"""
        import base64
        import uuid
        from app.config import get_app_data_dir
        uploads_dir = get_app_data_dir() / 'uploads'
        uploads_dir.mkdir(exist_ok=True)
        p = Path(filename)
        unique_name = f"{p.stem}_{uuid.uuid4().hex[:8]}{p.suffix}"
        dest = uploads_dir / unique_name
        dest.write_bytes(base64.b64decode(base64_content))
        return str(dest)

    def get_image_data(self, filename: str) -> str:
        """Return base64 data URL for an uploaded image.

        Accepts either a bare filename (looked up in uploads dir) or an
        absolute path (as embedded in the message marker after 路径:).
        """
        import base64 as _b64
        from app.config import get_app_data_dir
        cand = Path(filename)
        if cand.is_absolute() and cand.exists():
            path = cand
        else:
            path = get_app_data_dir() / 'uploads' / Path(filename).name
        if not path.exists():
            return ''
        ext = path.suffix.lower().lstrip('.')
        mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
                'gif': 'image/gif', 'webp': 'image/webp', 'bmp': 'image/bmp'}.get(ext, 'image/png')
        return f'data:{mime};base64,{_b64.b64encode(path.read_bytes()).decode()}'

    def read_file_content(self, path: str) -> str:
        try:
            return _read_file(path)
        except Exception as e:
            return f'[读取失败: {e}]'

    def describe_image(self, path: str) -> str:
        return describe_image(
            path,
            prompt='请详细描述这张图片的内容，包括文字、图表、场景、数据、文字信息等所有细节。',
            api_key=self._config.get('vision_api_key', ''),
            base_url=self._config.get('vision_base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
            model=self._config.get('vision_model', 'qwen-vl-max'),
        )

    # ── Agent / send ──────────────────────────────────────────────
    def send_message(self, conv_id: str, text: str, files: list) -> None:
        if self._running:
            return
        self._current_conv_id = conv_id
        conv = load_conversation(conv_id)
        if not conv:
            return

        # /compact slash command — inject as tool call trigger
        if text == '__slash_compact__':
            conv['messages'].append({'role': 'user', 'content': '请立即压缩上下文（调用 compact 工具）。'})
            save_conversation(conv)
            self._start_agent(conv)
            return

        # Build user message content
        # Images: use vision model to get text description
        # Other files: inject content as text
        parts = [text] if text else []
        for f in files:
            name = f.get('name', '')
            path = f.get('path', '')
            content = f.get('content', '')
            ext = Path(name).suffix.lower().lstrip('.')
            is_img = ext in {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
            if is_img:
                # 不再发送时预生成"通用描述"，而是把图片路径告知主模型，
                # 由它用贴合当前问题的措辞按需调用 analyze_image 工具进行针对性分析。
                if path:
                    abs_path = str(Path(path).expanduser().resolve())
                    parts.append(f"[图片: {name} 路径: {abs_path}]\n（如需了解此图内容，请使用 analyze_image 工具，并根据我的问题撰写针对性的 question。）")
                elif content:
                    # 无路径（如纯 base64 来源）时回退到已有描述
                    parts.append(f"[图片: {name}]\n{content}")
            else:
                abs_path = str(Path(path).expanduser().resolve()) if path else ''
                marker = f"[附件: {name} 路径: {abs_path}]" if abs_path else f"[附件: {name}]"
                if content:
                    parts.append(f"{marker}\n{content}")
                elif path:
                    # Fallback: read file content if JS didn't finish loading
                    try:
                        fallback_content = _read_file(path)
                        if fallback_content:
                            parts.append(f"{marker}\n{fallback_content}")
                    except Exception:
                        parts.append(f"{marker}（读取失败）")

        full_text = '\n\n'.join(parts)

        user_msg = {'role': 'user', 'content': full_text}
        conv['messages'].append(user_msg)

        # Auto-title on first message
        if len(conv['messages']) == 1:
            auto_title_from_message(conv, full_text)

        mc = get_active_model_config(self._config)
        if not mc:
            self._js('Chat.showError("未配置模型，请在设置中添加模型配置")')
            return

        self._ensure_managers()
        self._agent = _lazy_agent().Agent(
            api_key=mc.get('api_key', ''),
            base_url=mc.get('base_url', ''),
            model=mc.get('model', ''),
            system_prompt=mc.get('system_prompt', 'You are a helpful assistant.'),
            search_config=self._build_search_config(),
            command_safety=self._config.get('command_safety', 'confirm'),
            command_timeout=self._config.get('command_timeout', 30),
            max_rounds=self._config.get('max_rounds', 50),
            todo_manager=self._todo,
            task_manager=self._tasks,
            bg_manager=self._bg,
            thinking=self._thinking,
            search_enabled=self._search_mode == "auto" or self._search_enabled,
            compact_threshold=mc.get('compact_threshold', 0),
            context_length=mc.get('context_length', 0),
            vision_config=self._build_vision_config(),
        )
        self._agent._model_configs = self._config.get('model_configs', [])
        self._running = True

        def run():
            self._agent.run(
                messages=conv['messages'],
                on_token=self._on_token,
                on_tool_start=self._on_tool_start,
                on_tool_result=self._on_tool_result,
                on_confirm=self._on_confirm,
                on_done=lambda msgs: self._on_done(conv, msgs),
                on_error=lambda err, msgs: self._on_error(conv, err, msgs),
                on_todo_update=self._on_todo_update,
                on_context_update=self._on_context_update,
                on_thinking=self._on_thinking,
                on_usage=self._on_usage,
                on_ask_user=self._on_ask_user,
            )

        threading.Thread(target=run, daemon=True).start()

    def _start_agent(self, conv: dict) -> None:
        """Start agent for an already-prepared conv (used by slash commands)."""
        mc = get_active_model_config(self._config)
        if not mc:
            self._js('Chat.showError("未配置模型，请在设置中添加模型配置")')
            return
        self._ensure_managers()
        self._agent = _lazy_agent().Agent(
            api_key=mc.get('api_key', ''),
            base_url=mc.get('base_url', ''),
            model=mc.get('model', ''),
            system_prompt=mc.get('system_prompt', 'You are a helpful assistant.'),
            search_config=self._build_search_config(),
            command_safety=self._config.get('command_safety', 'confirm'),
            command_timeout=self._config.get('command_timeout', 30),
            max_rounds=self._config.get('max_rounds', 50),
            todo_manager=self._todo,
            task_manager=self._tasks,
            bg_manager=self._bg,
            thinking=self._thinking,
            search_enabled=self._search_mode == "auto" or self._search_enabled,
            compact_threshold=mc.get('compact_threshold', 0),
            context_length=mc.get('context_length', 0),
            vision_config=self._build_vision_config(),
        )
        self._agent._model_configs = self._config.get('model_configs', [])
        self._running = True
        self._js('startAssistantStream(); setRunning(true);')

        def run():
            self._agent.run(
                messages=conv['messages'],
                on_token=self._on_token,
                on_tool_start=self._on_tool_start,
                on_tool_result=self._on_tool_result,
                on_confirm=self._on_confirm,
                on_done=lambda msgs: self._on_done(conv, msgs),
                on_error=lambda err, msgs: self._on_error(conv, err, msgs),
                on_todo_update=self._on_todo_update,
                on_context_update=self._on_context_update,
                on_thinking=self._on_thinking,
                on_usage=self._on_usage,
                on_ask_user=self._on_ask_user,
            )

        threading.Thread(target=run, daemon=True).start()

    def stop_generation(self) -> None:
        if self._agent:
            self._agent.stop()
        self._debate_stop = True

    def undo_last_message(self, conv_id: str) -> Optional[str]:
        """Remove the last user+assistant exchange, return the user's text."""
        if self._running:
            self._agent.stop()
            import time
            time.sleep(0.3)
        conv = load_conversation(conv_id)
        if not conv or not conv.get('messages'):
            return None
        messages = conv['messages']
        # Remove trailing assistant message(s) and tool messages
        while messages and messages[-1]['role'] in ('assistant', 'tool'):
            messages.pop()
        # Now remove the last user message and return its content
        if messages and messages[-1]['role'] == 'user':
            user_msg = messages.pop()
            save_conversation(conv)
            self._running = False
            return user_msg.get('content', '')
        save_conversation(conv)
        self._running = False
        return None

    def debate_review(self, conv_id: str, selected_indices: list, model_config_name: str, user_prompt: str = '') -> None:
        """Send selected messages to another model for objective review."""
        conv = load_conversation(conv_id)
        if not conv:
            return
        messages = conv.get('messages', [])
        # Gather selected messages
        selected = []
        for idx in selected_indices:
            if 0 <= idx < len(messages):
                m = messages[idx]
                if m.get('role') in ('user', 'assistant') and m.get('content'):
                    selected.append(m)
        if not selected:
            self._js('Chat.showError("未选择有效消息")')
            return
        # Find the target model config
        configs = self._config.get('model_configs', [])
        mc = None
        for c in configs:
            if c.get('name') == model_config_name:
                mc = c
                break
        if not mc:
            self._js('Chat.showError("未找到指定模型配置")')
            return

        # Build review prompt
        conv_text = '\n\n'.join(
            f"{'【用户】' if m['role'] == 'user' else '【AI助手】'}:\n{m['content']}"
            for m in selected
        )
        user_guidance = f"\n\n--- 用户补充要求 ---\n\n{user_prompt}" if user_prompt else ""
        review_prompt = (
            "你是一位客观公正的 AI 评审专家。请对以下对话内容进行评价，指出回答中的优点、不足、"
            "可能的错误或遗漏，并给出改进建议。请用中文回答。\n\n"
            f"--- 待评审内容 ---\n\n{conv_text}{user_guidance}\n\n--- 请给出你的评价 ---"
        )

        self._running = True
        self._debate_stop = False

        def run():
            from openai import OpenAI
            client = OpenAI(api_key=mc.get('api_key', ''), base_url=mc.get('base_url', ''))
            try:
                response = client.chat.completions.create(
                    model=mc.get('model', ''),
                    messages=[{"role": "user", "content": review_prompt}],
                    stream=True,
                )
                full_response = ''
                for chunk in response:
                    if self._debate_stop:
                        break
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        self._js(f'Chat.appendToken({json.dumps(delta.content)})')
                        full_response += delta.content
                # Save the debate result as a message in conversation
                debate_label = f"[模型辩论 - 评审模型: {mc.get('name', model_config_name)}]\n\n"
                conv['messages'].append({'role': 'assistant', 'content': debate_label + full_response})
                save_conversation(conv)
                self._js('Chat.finishMessage()')
            except Exception as e:
                self._js(f'Chat.showError({json.dumps(f"评审请求失败: {str(e)}")})')
            finally:
                self._running = False

        threading.Thread(target=run, daemon=True).start()

    # ── Agent callbacks ───────────────────────────────────────────
    def _on_todo_update(self, items: list):
        self._js(f'Chat.updateTodo({json.dumps(items)})')

    def _on_token(self, token: str):
        self._js(f'Chat.appendToken({json.dumps(token)})')

    def _on_context_update(self, used: int, total: int):
        self._js(f'Chat.updateContext({used}, {total})')

    def _on_thinking(self, token: str):
        self._js(f'Chat.appendThinking({json.dumps(token)})')

    def _on_usage(self, usage_data: dict):
        self._js(f'Chat.updateUsage({json.dumps(usage_data)})')

    def _on_tool_start(self, tool_name: str, args: dict):
        self._js(f'Chat.showToolCall({json.dumps(tool_name)}, {json.dumps(args)})')

    def _on_tool_result(self, tool_name: str, result: str):
        self._js(f'Chat.showToolResult({json.dumps(tool_name)}, {json.dumps(result)})')
        # Track file operations for persistence
        if tool_name in ('write_file', 'apply_patch') and '✅' in result:
            self._track_file_op(tool_name, result)

    def _track_file_op(self, tool_name: str, result: str):
        """Extract file paths from tool result and store in current conversation."""
        import re
        paths = []
        for line in result.split('\n'):
            if '✅' in line:
                matches = re.findall(r'[A-Z]:\\[^\n]+|/[^\n\s]+', line)
                paths.extend(matches)
        if not paths:
            return
        conv = load_conversation(self._current_conv_id) if hasattr(self, '_current_conv_id') and self._current_conv_id else None
        if not conv:
            return
        if 'file_ops' not in conv:
            conv['file_ops'] = []
        from datetime import datetime
        for fp in paths:
            entry = {'path': fp, 'tool': tool_name, 'time': datetime.now().isoformat()}
            conv['file_ops'].append(entry)
        # Keep last 50 entries
        conv['file_ops'] = conv['file_ops'][-50:]
        save_conversation(conv)
        self._js(f'Chat.updateFileOps({json.dumps(conv["file_ops"])})')

    def _on_confirm(self, tool_name: str, args: dict) -> bool:
        # Check allowlist for run_command
        if tool_name == "run_command":
            cmd = args.get("command", "").strip()
            if is_command_allowed(cmd):
                return True
        self._confirm_event.clear()
        # Check if we should suggest a wildcard pattern
        wildcard = ""
        if tool_name == "run_command":
            cmd = args.get("command", "").strip()
            prefix = cmd.split()[0] if cmd.split() else ""
            if prefix:
                self._cmd_prefix_counts[prefix] = self._cmd_prefix_counts.get(prefix, 0) + 1
                if self._cmd_prefix_counts[prefix] >= 3:
                    wildcard = f"{prefix} *"
        self._js(f'Chat.showConfirmDialog({json.dumps(tool_name)}, {json.dumps(args)}, {json.dumps(wildcard)})')
        # Notify user if window is in background
        cmd_preview = args.get("command", tool_name)[:50] if tool_name == "run_command" else tool_name
        self._notify_system("需要确认执行", f"工具: {cmd_preview}")
        if not self._confirm_event.wait(timeout=120):
            # Timeout — treat as rejection to avoid permanent deadlock
            return False
        return self._confirm_result

    def confirm_tool(self, approved: bool) -> None:
        self._confirm_result = approved
        self._confirm_event.set()

    def confirm_tool_always(self, command: str) -> None:
        add_allowed_command(command)
        # Reset prefix counter if it's a wildcard pattern
        prefix = command.replace(" *", "").replace("*", "").strip()
        self._cmd_prefix_counts.pop(prefix, None)
        self._confirm_result = True
        self._confirm_event.set()

    def _on_ask_user(self, args: dict) -> str:
        """Callback: agent wants to ask user a question. Block until user answers."""
        question = args.get("question", "") or args.get("content", "") or args.get("text", "")
        if not question.strip():
            return "错误：question 参数为空。请使用 ask_user_question 工具时必须提供 question 参数，格式：{\"question\": \"你的问题\", \"options\": [\"选项1\", \"选项2\"]}"
        options = args.get("options", [])
        if not isinstance(options, list):
            options = []
        multi_select = args.get("multi_select", False)
        self._ask_event.clear()
        self._js(f'showAskDialog({json.dumps(question)}, {json.dumps(options)}, {json.dumps(multi_select)})')
        # Notify user if window is in background
        self._notify_system("AI 需要你的输入", question[:60])
        if not self._ask_event.wait(timeout=120):
            return "用户未响应（超时）"
        return self._ask_answer

    def answer_question(self, answer: str) -> None:
        """JS calls this when user submits answer."""
        self._ask_answer = answer
        self._ask_event.set()

    def _on_plan_approve(self, plan_summary: str) -> bool:
        """Callback: agent exits plan mode, asks user to approve."""
        self._plan_event.clear()
        self._js(f'showPlanApproval({json.dumps(plan_summary)})')
        if not self._plan_event.wait(timeout=120):
            return False
        return self._plan_approved

    def approve_plan(self, approved: bool) -> None:
        """JS calls this when user approves/rejects plan."""
        self._plan_approved = approved
        self._plan_event.set()

    def get_allowed_commands(self) -> list:
        return load_allowed_commands()

    def save_allowed_commands_api(self, commands: list) -> None:
        save_allowed_commands(commands)

    def get_app_version(self) -> str:
        return APP_VERSION

    def check_for_updates(self) -> dict:
        """Fetch latest releases from GitHub. Returns {releases: [...], current_version: str}."""
        import urllib.request
        import urllib.error
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
        headers = {"User-Agent": "QuickModel-Updater"}
        # Use GitHub token if configured to avoid rate limiting
        gh_token = self._config.get("github_token", "")
        if gh_token:
            headers["Authorization"] = f"token {gh_token}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            releases = []
            for r in data[:10]:  # last 10 releases
                releases.append({
                    "tag": r.get("tag_name", ""),
                    "name": r.get("name", ""),
                    "body": r.get("body", ""),
                    "published": r.get("published_at", ""),
                    "assets": [
                        {"name": a["name"], "url": a["browser_download_url"], "size": a["size"]}
                        for a in r.get("assets", [])
                    ],
                    "html_url": r.get("html_url", ""),
                })
            return {"releases": releases, "current_version": APP_VERSION}
        except urllib.error.HTTPError as e:
            if e.code == 403:
                return {"error": "GitHub API 速率限制，请稍后重试或在设置中配置 GitHub Token", "rate_limited": True, "current_version": APP_VERSION}
            return {"error": f"HTTP {e.code}: {e.reason}", "current_version": APP_VERSION}
        except Exception as e:
            return {"error": str(e), "current_version": APP_VERSION}

    def download_update(self, download_url: str, filename: str) -> dict:
        """Download an update asset to a temp folder. Returns {path: str} or {error: str}."""
        import urllib.request
        import tempfile
        try:
            dest_dir = Path(tempfile.gettempdir()) / "QuickModel_Update"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / filename
            req = urllib.request.Request(download_url, headers={"User-Agent": "QuickModel-Updater"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                with open(dest, 'wb') as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
            return {"path": str(dest)}
        except Exception as e:
            return {"error": str(e)}

    def apply_update_and_restart(self, downloaded_path: str) -> dict:
        """Generate a script to replace current exe and restart. Returns {ok: bool} or {error: str}."""
        import sys
        import subprocess
        try:
            current_exe = sys.executable
            current_dir = Path(current_exe).parent
            dl_path = Path(downloaded_path)

            if IS_WIN:
                # Generate a bat script that waits, extracts/copies, and restarts
                script = current_dir / "_update.bat"
                script.write_text(
                    f'@echo off\n'
                    f'echo 正在更新 QuickModel，请稍候...\n'
                    f'timeout /t 2 /nobreak >nul\n'
                    f'taskkill /f /pid {os.getpid()} >nul 2>&1\n'
                    f'timeout /t 1 /nobreak >nul\n'
                    f'if /i "{dl_path.suffix}" == ".zip" (\n'
                    f'  powershell -Command "Expand-Archive -Force \'{dl_path}\' \'{current_dir}\'"\n'
                    f') else (\n'
                    f'  copy /y "{dl_path}" "{current_dir}\\{dl_path.name}"\n'
                    f')\n'
                    f'start "" "{current_exe}"\n'
                    f'del "%~f0"\n',
                    encoding='utf-8'
                )
                subprocess.Popen(['cmd', '/c', str(script)], creationflags=0x00000008)  # DETACHED_PROCESS
            else:
                # macOS: shell script
                script = current_dir / "_update.sh"
                script.write_text(
                    f'#!/bin/bash\n'
                    f'sleep 2\n'
                    f'kill {os.getpid()} 2>/dev/null\n'
                    f'sleep 1\n'
                    f'if [[ "{dl_path.suffix}" == ".zip" ]]; then\n'
                    f'  unzip -o "{dl_path}" -d "{current_dir}"\n'
                    f'else\n'
                    f'  cp -f "{dl_path}" "{current_dir}/{dl_path.name}"\n'
                    f'fi\n'
                    f'open "{current_exe}"\n'
                    f'rm -- "$0"\n',
                    encoding='utf-8'
                )
                os.chmod(script, 0o755)
                subprocess.Popen(['bash', str(script)])

            # Exit the app
            if self._window:
                self._window.destroy()
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}

    def _on_done(self, conv: dict, updated_messages: list):
        conv['messages'] = updated_messages
        save_conversation(conv)
        self._running = False
        self._js('Chat.finishMessage()')
        # Notify user if window is in background
        self._notify_system("AI 回答完成", "模型已完成回复，点击查看")
        # Auto-upload to sync folder
        if self._config.get("sync_auto_upload") and get_sync_dir():
            upload_conversation(conv["id"])
        # Only auto-title if still a placeholder
        title = conv.get('title', '新对话')
        if title == '新对话' or len(title) <= 30:
            threading.Thread(target=self._auto_title, args=(conv,), daemon=True).start()

    def _auto_title(self, conv: dict):
        """用 LLM 根据对话内容生成标题，完成后推送到前端。"""
        messages = conv.get('messages', [])
        # 只取前几条消息做摘要，避免浪费 token
        sample = []
        for m in messages[:6]:
            if m.get('role') in ('user', 'assistant') and m.get('content'):
                sample.append(m)
        if not sample:
            return
        mc = get_active_model_config(self._config)
        if not mc:
            return
        from openai import OpenAI
        client = OpenAI(api_key=mc.get('api_key', ''), base_url=mc.get('base_url', ''))
        try:
            conv_text = '\n'.join(
                f"{'用户' if m['role'] == 'user' else 'AI'}: {str(m['content'])[:300]}"
                for m in sample
            )
            resp = client.chat.completions.create(
                model=mc.get('model', ''),
                messages=[{"role": "user", "content":
                    f"请根据以下对话内容，用不超过20个字生成一个简洁的标题，只输出标题本身，不要加引号或其他内容：\n\n{conv_text}"}],
                max_tokens=60,
            )
            title = (resp.choices[0].message.content or '').strip().strip('"\'')
            if title:
                conv['title'] = title
                save_conversation(conv)
                self._js(f'Chat.updateConvTitle({json.dumps(conv["id"])}, {json.dumps(title)})')
        except Exception:
            pass

    def _on_error(self, conv: dict, error: str, messages: list):
        conv['messages'] = messages
        save_conversation(conv)
        self._running = False
        self._js(f'Chat.showError({json.dumps(error)})')

    # ── Cloud Sync ───────────────────────────────────────────────────

    def sync_upload_all(self) -> dict:
        """上传所有本地对话到同步文件夹。"""
        count = upload_all_conversations()
        return {"uploaded": count}

    def sync_upload_current(self, conv_id: str) -> bool:
        """上传当前对话到同步文件夹。"""
        return upload_conversation(conv_id)

    def sync_detect_new(self) -> list:
        """检测同步文件夹中的新对话或更新的对话。"""
        return detect_new_conversations()

    def sync_import_selected(self, filenames: list) -> dict:
        """从同步文件夹导入选中的对话。"""
        count = import_from_sync(filenames)
        return {"imported": count}

    def sync_get_status(self) -> dict:
        """获取同步状态信息。"""
        sync_dir = get_sync_dir()
        if not sync_dir:
            return {"configured": False, "folder": ""}
        return {
            "configured": True,
            "folder": str(sync_dir),
            "exists": sync_dir.exists(),
        }

    def sync_choose_folder(self) -> Optional[str]:
        """打开文件夹选择对话框，选择同步文件夹。"""
        result = self._window.create_file_dialog(
            webview.FileDialog.FOLDER
        )
        if result:
            folder = result[0] if isinstance(result, (list, tuple)) else result
            config = load_config()
            config["sync_folder"] = folder
            save_config(config)
            return folder
        return None

    def sync_upload_config(self) -> dict:
        """上传配置文件到同步文件夹。"""
        return upload_config()

    def sync_detect_config(self) -> dict:
        """检测同步文件夹中是否有更新的配置。"""
        return detect_config_updates()

    def sync_import_config(self, files: Optional[list] = None) -> dict:
        """从同步文件夹导入配置文件。"""
        return import_config(files)

    def sync_all(self) -> dict:
        """一键上传全部（对话 + 配置）。"""
        return sync_all()

    def sync_import_all(self) -> dict:
        """一键导入全部（新对话 + 配置）。"""
        return import_all()
