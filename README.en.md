# QuickModel

A desktop AI assistant for Windows supporting multiple LLM vendors via OpenAI-compatible API. Built with pywebview (WebView2) + Python backend.

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

[中文](./README.md) | English

## Features

### Core Agent

- **Multi-vendor LLM** — Works with any OpenAI-compatible API: DeepSeek (V3/R1/V4 Pro/V4 Flash), OpenAI, Qwen, Ollama, and more
- **Multiple models per provider** — Configure and switch between multiple model backends in settings
- **Reasoning intensity (off / high / max)** — Three-level thinking mode cycled via toolbar button; persisted across sessions
- **Auto-Compact** — Context auto-summarizes at 80k tokens (800k for V4 models); manual `/compact` command also available; prefix-cache-aware compression preserves DeepSeek cache hits
- **Image understanding** — Paste or drop images into chat; described via Qwen-VL or any vision API
- **Real-time cost tracking** — Per-round and per-session token usage with cache hit/miss breakdown displayed in the sidebar

### Built-in Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read local files (txt, md, py, json, csv, pdf, docx, xlsx, etc.) |
| `write_file` | Write or overwrite files on disk |
| `apply_patch` | Apply unified diff patches to precisely modify specific lines |
| `list_directory` | List directory contents |
| `run_command` | Execute PowerShell commands (with confirmation dialog) |
| `web_search` | Search the internet via multiple engines with auto-fallback |
| `web_read` | Fetch and read full webpage content (HTML to plain text) |
| `rlm_query` | Dispatch 1-16 sub-tasks to a low-cost model in parallel |
| `compact` | Manually trigger context compression |
| `todo_write` | Maintain a structured task list for multi-step work tracking |
| `subagent` | Spawn a focused sub-agent with its own tool loop |
| `glob_files` | Search files by glob pattern |
| `grep_files` | Search file contents by regex |

### Multi-Engine Web Search

- **6 search backends** — Tavily, Brave Search, Firecrawl, Google Custom Search, SearXNG, DuckDuckGo
- **Auto-fallback** — If the preferred engine fails, automatically tries the next available engine; DuckDuckGo (free, no key) as ultimate fallback
- **Auto-read** — Automatically fetches full page content for top search results
- **Soft limit** — After 5 searches in one turn, the agent is nudged to consolidate results
- **Manual / Auto modes** — Auto lets the model decide; manual gives you a toolbar toggle

### Cloud Sync & Import/Export

- **Cloud sync** — Automatically sync conversations to a local cloud folder (Nutstore/OneDrive/Google Drive) for seamless cross-device usage
- **Auto-upload** — Conversations are automatically copied to the sync folder after completion
- **Startup detection** — Automatically detects new conversations from cloud on launch
- **Selective import** — Checkbox interface to choose which conversations to import
- **Export to Markdown** — Exports only user and assistant content, excluding tool calls
- **Import conversations** — Import from .json (full backup) or .md (exported format) files

### Skills System

- **Built-in & custom skills** — Save and reuse prompt templates that change agent behavior
- **Import Claude-style skills** — Import from folder (auto-detects `SKILL.md` + companion files, batch import supported)
- **Full CRUD panel** — Create, edit, and delete skills from a management UI

### Memory System

- **Persistent key-value store** — Agent can save and recall facts across conversations (`memory_read`, `memory_write`)
- **Auto-injection** — Memory summary injected on new conversation start

### Worktree Isolation

- **Git worktree integration** — Each conversation can operate in its own isolated worktree
- **Command safety** — Confirmation dialog with smart wildcard pattern suggestions
- **Worktree panel** — Side panel showing active worktrees, branches, and bound tasks

### Team Collaboration

- **Multi-agent teams** — Spawn persistent team members running in independent threads
- **Message bus** — In-memory inbox/outbox for agent-to-agent communication
- **UI notifications** — Real-time callback when team members complete work

### Task Management

- **Persistent tasks** — Structured tasks that survive across conversations
- **Dependency graph** — Tasks can block each other (pending → in_progress → completed)
- **Worktree binding** — Tasks auto-complete when bound worktrees are removed

### RLM Parallel Processing

- **Batch sub-tasks** — Dispatch up to 16 independent prompts to deepseek-v4-flash in parallel
- **Use cases** — Bulk translation, code review, multi-file analysis, data extraction
- **Auto model selection** — Automatically picks the flash model from your configured model list

### UI

- **pywebview desktop app** — Native window with web-based chat interface
- **Conversation management** — Sidebar with drag-to-reorder, search (title + content), rename, delete
- **Collapsible tool bubbles** — Tool calls and results in collapsible message bubbles
- **Chat navigation** — Previous/next message buttons with smooth scroll animation
- **Markdown & LaTeX** — Full rendering with marked.js and KaTeX (offline, no CDN)
- **Theme support** — Light and dark themes, adjustable font size
- **Context progress bar** — Real-time token usage display, auto-refreshes on conversation switch
- **CSS animations** — Rich transition animations and interaction feedback, unaffected by system "reduce motion" settings
- **Random color borders** — Active conversation item gets a random accent color on each click

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

| Key | Description |
|-----|-------------|
| `model_configs` | Multiple model backends (switchable in settings) |
| `thinking` | Reasoning intensity: `"off"`, `"high"`, or `"max"` |
| `search_engine` | Preferred search engine: `tavily`, `brave`, `firecrawl`, `duckduckgo`, `google`, `searxng` |
| `search_fallback` | Auto-fallback to next available engine on failure |
| `sync_folder` | Cloud sync folder path (e.g., Nutstore/OneDrive sync directory) |
| `sync_auto_upload` | Auto-upload conversations to sync folder after completion |
| `vision_api_key` / `vision_model` | Vision model configuration for image understanding |

## Supported Providers

| Provider | Base URL |
|----------|----------|
| DeepSeek | `https://api.deepseek.com/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Ollama (local) | `http://localhost:11434/v1` |
| DashScope (Qwen) | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Any OpenAI-compatible API | Custom URL |

## Usage Tips

- **Cloud Sync**: Configure a sync folder in settings; conversations auto-upload. On another PC, click "Detect new conversations" to import
- **Skills**: Open the skills panel to create or import specializations before starting a task
- **Worktrees**: When the agent needs to modify code, ask it to create a worktree first for isolation
- **Memory**: Tell the agent "remember this..." and it will save to persistent memory
- **Thinking**: Cycle through off → high → max with the 💭 button; use off for fast responses, max for deep reasoning
- **Search**: Use auto mode for research tasks; switch to manual when you want to control search usage
- **RLM**: Ask the agent to batch-process tasks (e.g., "translate these 10 paragraphs") and it will use parallel sub-tasks
- **Compact**: If the conversation gets too long, use `/compact` or wait for auto-compact

## Project Structure

```
quick_model/
├── main.py              # Entry point
├── app/
│   ├── agent.py         # Core agent loop, tool dispatch, compact logic
│   ├── tools.py         # Built-in tool implementations (file, search, shell)
│   ├── advanced_tools.py # Sub-agent, task, background task, todo management
│   ├── skills.py        # Skill CRUD, import, memory persistence
│   ├── team.py          # Multi-agent team, message bus, worktree index
│   ├── sync.py          # Cloud sync module (upload/detect/import)
│   ├── webview_app.py   # pywebview API bridge (Python ↔ JavaScript)
│   ├── config.py        # Configuration loading/saving with defaults
│   ├── conversation.py  # Conversation CRUD, import/export, sort ordering
│   ├── compact.py       # Context compression and summarization
│   ├── vision.py        # Image description via vision API
│   ├── command_safety.py # Command allow-list and pattern matching
│   ├── static/          # HTML/CSS/JS frontend
│   │   ├── index.html   # Main UI layout
│   │   ├── app.js       # Frontend logic and event handling
│   │   ├── style.css    # Dark/light theme styles
│   │   └── animations.css # Animation and transition effects
│   └── skills/          # Default skill definitions (.md files)
└── conversations/       # Conversation history (auto-created)
```

## Tech Stack

- **Frontend**: pywebview (WebView2), HTML/CSS/JS
- **Backend**: Python, OpenAI SDK
- **Rendering**: marked.js, KaTeX, highlight.js (all local, offline)
- **Packaging**: PyInstaller

## License

MIT
