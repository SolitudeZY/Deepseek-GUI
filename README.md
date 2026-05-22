# QuickModel

A desktop AI assistant for Windows supporting multiple LLM vendors via OpenAI-compatible API. Built with pywebview (WebView2) + Python backend.

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

English | [涓枃](./README.zh.md)

## Features

### Core Agent
- **Multi-vendor LLM** 鈥?Works with any OpenAI-compatible API: DeepSeek (V3/R1/V4 Pro/V4 Flash), OpenAI, Qwen, Ollama, and more
- **Multiple models per provider** 鈥?Configure and switch between multiple model backends in settings
- **Reasoning intensity (off / high / max)** 鈥?Three-level thinking mode cycled via toolbar button; persisted across sessions
- **Auto-Compact** 鈥?Context auto-summarizes at 80k tokens (800k for V4 models); manual `/compact` command also available; prefix-cache-aware compression preserves DeepSeek cache hits
- **Image understanding** 鈥?Paste or drop images into chat; described via Qwen-VL or any vision API
- **Real-time cost tracking** 鈥?Per-round and per-session token usage with cache hit/miss breakdown displayed in the sidebar

### Tools Built into the Agent
| Tool | Description |
|------|-------------|
| `read_file` | Read local files (txt, md, py, json, csv, pdf, docx, xlsx, etc.) |
| `write_file` | Write or overwrite files on disk |
| `apply_patch` | Apply unified diff patches to precisely modify specific lines (safer than `write_file`) |
| `list_directory` | List directory contents |
| `run_command` | Execute PowerShell commands (with confirmation dialog) |
| `web_search` | Search the internet via multiple engines with auto-fallback |
| `web_read` | Fetch and read full webpage content (HTML 鈫?plain text) |
| `rlm_query` | Dispatch 1鈥?6 sub-tasks to a low-cost model (deepseek-v4-flash) in parallel |
| `compact` | Manually trigger context compression |
| `todo_write` | Maintain a structured task list for multi-step work tracking |
| `subagent` | Spawn a focused sub-agent with its own tool loop for deep exploration |

### Multi-Engine Web Search
- **6 search backends** 鈥?Tavily, Brave Search, Firecrawl, Google Custom Search, SearXNG, DuckDuckGo
- **Auto-fallback** 鈥?If the preferred engine fails, automatically tries the next available engine; DuckDuckGo (free, no key) as ultimate fallback
- **Auto-read** 鈥?Automatically fetches full page content for top search results, reducing the need for follow-up searches
- **Soft limit** 鈥?After 5 searches in one turn, the agent is nudged to consolidate results
- **Manual / Auto modes** 鈥?Auto lets the model decide; manual gives you a toolbar toggle

### Skills System
- **Built-in & custom skills** 鈥?Save and reuse prompt templates that change agent behavior
- **Import Claude-style skills** 鈥?Import from folder (auto-detects `SKILL.md` + companion files, batch import supported)
- **Full CRUD panel** 鈥?Create, edit, and delete skills from a management UI

### Memory System
- **Persistent key-value store** 鈥?Agent can save and recall facts across conversations (`memory_read`, `memory_write`)
- **Auto-injection** 鈥?Memory summary injected on `/new` conversation start

### Worktree Isolation
- **Git worktree integration** 鈥?Each conversation can operate in its own isolated worktree
- **Command safety** 鈥?Confirmation dialog with smart wildcard pattern suggestions (`git *`, `python *`)
- **Worktree panel** 鈥?Side panel showing active worktrees, branches, and bound tasks

### Team Collaboration
- **Multi-agent teams** 鈥?Spawn persistent team members running in independent threads
- **Message bus** 鈥?In-memory inbox/outbox for agent-to-agent communication
- **UI notifications** 鈥?Real-time callback when team members complete work

### Task Management
- **Persistent tasks** 鈥?Structured tasks that survive across conversations
- **Dependency graph** 鈥?Tasks can block each other (pending 鈫?in_progress 鈫?completed)
- **Worktree binding** 鈥?Tasks auto-complete when bound worktrees are removed

### RLM Parallel Processing
- **Batch sub-tasks** 鈥?Dispatch up to 16 independent prompts to deepseek-v4-flash in parallel
- **Use cases** 鈥?Bulk translation, code review, multi-file analysis, data extraction
- **Auto model selection** 鈥?Automatically picks the flash model from your configured model list

### UI
- **pywebview desktop app** 鈥?Native window with web-based chat interface
- **Conversation management** 鈥?Sidebar with drag-to-reorder, search, rename, delete, export to Markdown
- **Collapsible tool bubbles** 鈥?Tool calls and results in collapsible message bubbles
- **Chat navigation** 鈥?Previous/next message buttons with smooth scroll animation
- **Markdown & LaTeX** 鈥?Full rendering with marked.js and KaTeX (offline, no CDN)
- **Theme support** 鈥?Light and dark themes, adjustable font size
- **Cost & context display** 鈥?Real-time token usage, cache hit rate, and context utilization in sidebar

## Screenshots

> Coming soon

## Requirements

- Windows 10/11 with [WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) (usually pre-installed on Win11)
- Python 3.10+
- API key for at least one supported LLM provider

## Installation

### Run from source

```bash
git clone https://github.com/SolitudeZY/Deepseek-GUI.git
cd Deepseek-GUI

pip install openai pywebview tavily-python duckduckgo-search firecrawl-py

python main.py
```

### Download pre-built .exe

Download `QuickModel.exe` from [Releases](https://github.com/SolitudeZY/Deepseek-GUI/releases) and run directly. No installation needed.

## Build

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name QuickModel --icon=icon.ico --add-data "app/static;app/static" --add-data "icon.ico;." main.py
```

Output: `dist/QuickModel.exe`

## Configuration

On first launch, open **Settings** to configure. Config is stored in `%APPDATA%\AIDesktopAssistant\config.json`.

```json
{
  "model_configs": [
    {"name": "DeepSeek V4 Pro", "api_key": "sk-...", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-v4-pro"},
    {"name": "DeepSeek V4 Flash", "api_key": "sk-...", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-v4-flash"}
  ],
  "thinking": "high",
  "search_engine": "brave",
  "search_fallback": true,
  "tavily_api_key": "tvly-...",
  "brave_api_key": "BSAy_...",
  "firecrawl_api_key": "fc-...",
  "google_api_key": "",
  "google_cx": "",
  "searxng_url": "",
  "search_mode": "auto",
  "search_enabled": true,
  "vision_api_key": "sk-...",
  "vision_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "vision_model": "qwen-vl-max"
}
```

| Key | Description |
|-----|-------------|
| `model_configs` | Multiple model backends (switchable in settings) |
| `thinking` | Reasoning intensity: `"off"`, `"high"`, or `"max"` |
| `search_engine` | Preferred search engine: `tavily`, `brave`, `firecrawl`, `duckduckgo`, `google`, `searxng` |
| `search_fallback` | Auto-fallback to next available engine on failure |
| `tavily_api_key` | [app.tavily.com](https://app.tavily.com) 鈥?1000 free searches/month |
| `brave_api_key` | [brave.com/search/api](https://brave.com/search/api/) 鈥?2000 free searches/month |
| `firecrawl_api_key` | [firecrawl.dev](https://www.firecrawl.dev) 鈥?500 free searches/month, returns full Markdown |
| `google_api_key` / `google_cx` | Google Custom Search 鈥?100 free searches/day (limited to 50 domains since 2026) |
| `searxng_url` | Self-hosted SearXNG instance URL |
| `search_mode` | `"auto"` = model decides; `"manual"` = user toggles via toolbar |
| `vision_api_key` / `vision_base_url` / `vision_model` | Vision model for image description |

## Supported Providers

| Provider | Base URL |
|----------|----------|
| DeepSeek | `https://api.deepseek.com/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Ollama (local) | `http://localhost:11434/v1` |
| DashScope (Qwen) | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Any OpenAI-compatible API | Custom URL |

## Usage Tips

- **Skills**: Open the skills panel to create or import specializations before starting a task
- **Worktrees**: When the agent needs to modify code, ask it to create a worktree first for isolation
- **Memory**: Tell the agent "remember this..." and it will save to persistent memory
- **Thinking**: Cycle through off 鈫?high 鈫?max with the 馃挱 button; use off for fast responses, max for deep reasoning
- **Search**: Use auto mode for research tasks; switch to manual when you want to control search usage
- **RLM**: Ask the agent to batch-process tasks (e.g., "translate these 10 paragraphs") and it will use parallel sub-tasks
- **apply_patch**: For precise code edits, the agent can use unified diffs instead of rewriting entire files
- **Compact**: If the conversation gets too long, use `/compact` or wait for auto-compact
- **Cost**: Monitor token usage and cache hit rate in the sidebar to optimize API costs

## Project Structure

```
quick_model/
鈹溾攢鈹€ main.py              # Entry point
鈹溾攢鈹€ app/
鈹?  鈹溾攢鈹€ agent.py         # Core agent loop, tool dispatch, compact logic
鈹?  鈹溾攢鈹€ tools.py         # Built-in tool implementations (file, search, shell)
鈹?  鈹溾攢鈹€ advanced_tools.py # Sub-agent, task, background task, todo management
鈹?  鈹溾攢鈹€ skills.py        # Skill CRUD, import, memory persistence
鈹?  鈹溾攢鈹€ team.py          # Multi-agent team, message bus, worktree index
鈹?  鈹溾攢鈹€ webview_app.py   # pywebview API bridge (Python 鈫?JavaScript)
鈹?  鈹溾攢鈹€ config.py        # Configuration loading/saving with defaults
鈹?  鈹溾攢鈹€ conversation.py  # Conversation CRUD, export, sort ordering
鈹?  鈹溾攢鈹€ compact.py       # Context compression and summarization
鈹?  鈹溾攢鈹€ vision.py        # Image description via vision API
鈹?  鈹溾攢鈹€ command_safety.py # Command allow-list and pattern matching
鈹?  鈹溾攢鈹€ static/          # HTML/CSS/JS frontend
鈹?  鈹?  鈹溾攢鈹€ index.html   # Main UI layout
鈹?  鈹?  鈹溾攢鈹€ app.js       # Frontend logic and event handling
鈹?  鈹?  鈹斺攢鈹€ style.css    # Dark/light theme styles
鈹?  鈹斺攢鈹€ skills/          # Default skill definitions (.md files)
鈹斺攢鈹€ conversations/       # Conversation history (auto-created)
```

## Tech Stack

- **Frontend**: pywebview (WebView2), HTML/CSS/JS
- **Backend**: Python, OpenAI SDK
- **Rendering**: marked.js, KaTeX, highlight.js (all local, offline)
- **Packaging**: PyInstaller

## License

MIT
