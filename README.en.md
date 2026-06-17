# QuickModel

A desktop AI assistant for Windows and macOS supporting multiple LLM vendors via OpenAI-compatible API. Built with pywebview (WebView2 / WebKit) + Python backend.

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

[中文](./README.md) | English

## Features

### Core Agent

- **Multi-vendor LLM** — Works with any OpenAI-compatible API: DeepSeek (V3/R1/V4 Pro/V4 Flash), OpenAI, Qwen, Ollama, and more
- **Multiple model configs** — Configure and switch between multiple model backends; each model has independent context length and compact threshold settings
- **Reasoning intensity (off / high / max)** — Three-level thinking mode cycled via toolbar button; persisted across sessions
- **Auto-Compact** — Context auto-summarizes when exceeding threshold (default 600K, customizable); manual `/compact` command; prefix-cache-aware compression preserves DeepSeek cache hits
- **Image understanding (targeted analysis)** — Paste or drop images into chat. Only the image path is attached on send; the main model calls the `analyze_image` tool with a question tailored to the current conversation (rather than a pre-generated generic description). Built-in anti-hallucination constraints make the vision model report only what is actually visible and distinguish observation from speculation. Uses Qwen-VL or any vision API by default
- **Image generation** — When asked to generate/draw an image, the main model calls the `generate_image` tool via an OpenAI-compatible endpoint (supports relays like New API / sub2api), saves it locally, and shows a thumbnail inline (click to enlarge)
- **Real-time cost tracking** — Per-round and per-session token usage with cache hit/miss breakdown

### Built-in Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read local files (txt, md, py, json, csv, pdf, docx, xlsx, etc.) |
| `write_file` | Write or overwrite files on disk |
| `apply_patch` | Edit files via exact string replacement (old snippet → new content); supports multiple edits/files; errors out instead of corrupting the file when no/ambiguous match |
| `list_directory` | List directory contents |
| `run_command` | Execute shell commands (PowerShell on Windows, bash on macOS/Linux) with confirmation dialog and an allow-list to auto-run remembered commands |
| `analyze_image` | Analyze a local image with the vision model for a specific question |
| `generate_image` | Generate an image with an image model and save it locally |
| `web_search` | Search the internet via multiple engines with auto-fallback |
| `web_read` | Fetch and read full webpage content (HTML to plain text) |
| `rlm_query` | Dispatch 1-16 sub-tasks to a low-cost model in parallel |
| `compact` | Manually trigger context compression |
| `todo_write` | Maintain a structured task list for multi-step work tracking |
| `subagent` | Spawn a focused sub-agent with its own tool loop |
| `glob_files` | Search files by glob pattern |
| `grep_files` | Search file contents by regex |
| `ask_user_question` | Ask the user a question and wait for response |
| `enter_plan_mode` / `exit_plan_mode` | Enter/exit planning mode |

### Multi-Engine Web Search

- **6 search backends** — Tavily, Brave Search, Firecrawl, Google Custom Search, SearXNG, DuckDuckGo
- **Auto-fallback** — If the preferred engine fails, automatically tries the next; DuckDuckGo (free) as ultimate fallback
- **Parallel fetching** — Search result pages fetched concurrently (up to 5 threads), significantly reducing wait time
- **Soft limit** — After 5 searches in one turn, the agent is nudged to consolidate results
- **Manual / Auto modes** — Auto lets the model decide; manual gives you a toolbar toggle

### Image Tools

- **Targeted image analysis** — Only the absolute path is attached on send; the main model writes a context-aware `question` and calls `analyze_image` to get focused results (facial expressions, chart values, text in code screenshots, specific regions) instead of a generic full-scene description
- **Anti-hallucination constraints** — The vision model is forced to report only what is actually visible, distinguish observation from speculation, read text/numbers verbatim, and say so when something is unclear — reducing wrong conclusions
- **Image generation** — `generate_image` calls an OpenAI-compatible `/v1/images/generations` endpoint (supports relays like New API / sub2api), saves locally, and renders a thumbnail card inline
- **Fetch model list** — One click in settings pulls the available model list from your vision/image-gen provider; click to fill it in
- **Separate config** — Independent `api_key` / `base_url` / `model` for vision and image-gen, configured under the "Image Tools" tab in settings

### Command Execution & Safety

- **Cross-platform shell** — PowerShell on Windows, bash on macOS/Linux; output encoding auto-detected (GBK-tolerant on Windows)
- **Confirmation & allow-list** — Confirmation dialog before running commands; commands can be added to an allow-list for subsequent auto-execution; smart wildcard pattern suggestions
- **Timeout & interrupt** — Commands run with timeout protection and can be stopped anytime

### Project Grouping & Working Directory

- **Conversation-bound project dir** — Each conversation can bind a project folder; tool relative paths resolve against it, fixing the model writing files to the wrong directory
- **Sidebar grouping by project** — Conversation list grouped into collapsible project sections; supports cross-group drag-to-reclassify and drag-to-reorder (with placeholder visual feedback)
- **Project picker home** — When starting a new conversation, choose a recent project, add a new one, or start with no project
- **Stale path warning** — When a project dir doesn't exist on this machine after cross-device sync, a banner offers one-click reset

### Cloud Sync & Import/Export

- **One-click full sync** — Upload all conversations + config files to a cloud folder (Nutstore/OneDrive/Google Drive)
- **One-click full import** — Import all conversations and config on a new machine with a single click
- **Auto-upload** — Conversations automatically copied to sync folder after completion
- **Startup detection** — Automatically detects new conversations from cloud on launch
- **Selective import** — Checkbox interface to choose which conversations to import
- **Config sync** — API keys, model configs, allowed commands all synced (local sync path is preserved)
- **Export to Markdown** — Exports only user and assistant content, excluding tool calls
- **Import conversations** — Import from .json (full backup) or .md (exported format) files

### Skills System

- **Built-in & custom skills** — Save and reuse prompt templates
- **Import Claude-style skills** — Import from folder (auto-detects `SKILL.md` + companion files, batch import)
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
- **Message bus** — Thread-safe inbox/outbox for agent-to-agent communication
- **UI notifications** — Real-time callback when team members complete work
- **Auto-claim** — Idle members automatically claim unclaimed tasks from the task board

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

> <img width="1238" height="748" alt="QQ20260524-122750-HD" src="https://github.com/user-attachments/assets/f334c249-8b9c-4176-bb22-6e3b364bb37e" />

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  pywebview (WebView2)                                   │
│  ┌───────────────┐    JS ↔ Python API    ┌───────────┐ │
│  │  Frontend     │◄─────────────────────►│  Backend  │ │
│  │  HTML/CSS/JS  │                       │  Python   │ │
│  └───────────────┘                       └─────┬─────┘ │
└────────────────────────────────────────────────┼────────┘
                                                 │
         ┌───────────────────────────────────────┼──────┐
         │              Agent Loop               │      │
         │  ┌─────────┐  ┌──────────┐  ┌───────┴───┐  │
         │  │ Stream & │  │ Tool     │  │ Context   │  │
         │  │ Parse    │  │ Registry │  │ Manager   │  │
         │  └─────────┘  └──────────┘  └───────────┘  │
         └──────────────────────────────────────────────┘
                          │
         ┌────────────────┼────────────────────────┐
         │                ▼                        │
         │  ┌──────┐ ┌────────┐ ┌──────┐ ┌─────┐ │
         │  │ File │ │ Search │ │ Team │ │ ... │ │
         │  │ I/O  │ │ (6 eng)│ │ Bus  │ │     │ │
         │  └──────┘ └────────┘ └──────┘ └─────┘ │
         └─────────────────────────────────────────┘
```

## Requirements

- Windows 10/11 with [WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) (pre-installed on Win11); or macOS (uses the built-in WebKit, no extra runtime)
- Python 3.10+
- At least one LLM provider API key

## Installation

### Run from source

```bash
git clone https://github.com/SolitudeZY/Deepseek-GUI.git
cd Deepseek-GUI

# Windows
pip install openai pywebview tavily-python duckduckgo-search firecrawl-py

# macOS (also needs pyobjc for the cocoa/WebKit backend)
pip install -r requirements.txt

python main.py
```

### Build

```bash
pip install pyinstaller

# Windows
pyinstaller --onefile --windowed --name QuickModel --icon=icon.ico --add-data "app/static;app/static" --add-data "icon.ico;." main.py

# macOS (note the : separator in --add-data, produces a .app)
pyinstaller --windowed --name QuickModel --icon=icon.icns --add-data "app/static:app/static" --add-data "icon.png:." main.py
```

On Windows the generated `dist/QuickModel/` folder (or single exe) is ready to distribute; on macOS it produces `dist/QuickModel.app`.

## Quick Start

> See [Usage Guide (Chinese)](./使用说明.md) | [LLM API Base URL Reference](./主流%20LLM%20模型的%20API%20Base%20URL%20汇总.md)

1. Launch the app and click **Settings** in the top-right
2. Under "Model Config", enter your API Key and Base URL
3. Optional: configure search engine keys (Tavily/Brave etc.)
4. Optional: set up a cloud sync folder for cross-device sync
5. Close settings and start chatting

## Tips

- **Thinking mode**: Use high/max for complex reasoning; off for simple Q&A to save tokens
- **Web search**: Use auto mode for research tasks; switch to manual to control search usage
- **RLM**: Ask the agent to batch-process tasks (e.g., "translate these 10 paragraphs") and it will use parallel sub-tasks
- **Compact**: If the conversation gets too long, use `/compact` or wait for auto-compact
- **Cloud sync**: After setting the sync folder, click "Upload All" to backup; on a new PC click "Import All" to restore
- **Skills**: Save frequently-used prompts as skills for quick reuse

## Project Structure

```
quick_model/
├── main.py              # Entry point
├── app/
│   ├── agent.py         # Core agent loop (split into stream/parse, tool exec, context mgmt)
│   ├── tools.py         # Built-in tool implementations (file, search, shell)
│   ├── advanced_tools.py # Sub-agent, task, background task, todo management
│   ├── skills.py        # Skill CRUD, import, memory persistence
│   ├── team.py          # Multi-agent team, message bus (thread-safe), worktree
│   ├── sync.py          # Cloud sync module (conversations + config upload/detect/import)
│   ├── webview_app.py   # pywebview API bridge (Python ↔ JavaScript)
│   ├── config.py        # Configuration loading/saving with defaults
│   ├── conversation.py  # Conversation CRUD, import/export, sort ordering
│   ├── compact.py       # Context compression and summarization
│   ├── vision.py        # Image description & image generation via vision API
│   └── static/          # HTML/CSS/JS frontend
│       ├── index.html   # Main UI layout
│       ├── app.js       # Frontend logic and event handling
│       ├── style.css    # Dark/light theme styles
│       └── animations.css # Animation and transition effects
└── conversations/       # Conversation history (auto-created in %APPDATA%)
```

## Tech Stack

- **Frontend**: pywebview (WebView2 on Windows / WebKit on macOS), HTML/CSS/JS
- **Backend**: Python 3.10+, OpenAI SDK
- **Rendering**: marked.js, KaTeX, highlight.js (all local, offline)
- **Concurrency**: threading + ThreadPoolExecutor (parallel search fetching, multi-agent teams)
- **Packaging**: PyInstaller

## License

MIT
