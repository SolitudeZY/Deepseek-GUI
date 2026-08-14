# QuickModel

A desktop AI agent for Windows and macOS with native support for OpenAI Chat Completions, OpenAI Responses, Anthropic Messages, and OpenAI-compatible providers. Built with pywebview (WebView2 / WebKit) and a Python backend, with file and shell tools, web retrieval, MCP, browser control, SSH, multi-agent workflows, vision, and image generation.

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

[中文](./README.md) | English

> See the [Usage Guide (Chinese)](./使用说明.md) | [MCP Guide (Chinese)](./MCP使用指南.md) | [LLM API Base URL Reference](./主流%20LLM%20模型的%20API%20Base%20URL%20汇总.md)

## Recent Updates

- **Expanded conversation workflows** — Temporary conversations, archive view, project-level archive, and bulk archive/restore/delete; long project groups collapse automatically and search covers titles and visible message content
- **Usage analytics** — Monthly heatmap, weekly bar chart, and model distribution chart with output/input/total token views, cache metrics, and estimated-usage tracking
- **Native model protocols** — OpenAI Chat Completions, OpenAI Responses, and Anthropic Messages, plus provider-specific handling for DeepSeek, Qwen, GLM, and Codex; import local Claude/Codex model and MCP configs
- **Controlled browser** — The agent can launch an isolated Edge/Chrome session, inspect pages, click, type, and scroll; interactive actions use the existing confirmation policy and secrets stay user-entered
- **Immersive weather backgrounds** — Time-aware city scenes driven by Open-Meteo weather, with clouds, rain, snow, fog, thunderstorms, light motes, and star trails; includes manual previews and effect controls
- **More reliable sub-agents** — Sub-agents inherit the current project directory and use dedicated round/time budgets, repeated-call detection, and forced summarization to avoid stalling the main task

## Features

### Core Agent

- **Multiple protocols and providers** — OpenAI Chat Completions, OpenAI Responses, and Anthropic Messages, with support for DeepSeek, OpenAI, Claude, Qwen, GLM, Ollama, and common API relays
- **Multiple model configs** — Configure and switch between multiple model backends; each model has independent context length and compact threshold settings
- **Config migration** — Discover and selectively import local Claude Code and Codex model/MCP Server configurations
- **Prompt presets** — General, research, document organization, coding, and code review templates; prompts change only when explicitly applied
- **Reasoning intensity (off / high / max)** — Three-level thinking mode cycled via toolbar button; persisted across sessions
- **Auto-Compact** — Context auto-summarizes when exceeding threshold (default 600K, customizable); manual `/compact` command; prefix-cache-aware compression preserves DeepSeek cache hits
- **Image understanding (targeted analysis)** — Paste or drop images into chat. Only the image path is attached on send; the main model calls the `analyze_image` tool with a question tailored to the current conversation (rather than a pre-generated generic description). Built-in anti-hallucination constraints make the vision model report only what is actually visible and distinguish observation from speculation. Uses Qwen-VL or any vision API by default
- **Image generation** — When asked to generate/draw an image, the main model calls the `generate_image` tool via an OpenAI-compatible endpoint (supports relays like New API / sub2api), saves it locally, and shows a thumbnail inline (click to enlarge)
- **Cross-conversation memory** — Remembers approved user preferences and project context across conversations; memory entries can be viewed, edited, and deleted in settings
- **Token usage tracking** — The sidebar shows output tokens for the current round/agent run and cache hit rate; the usage dashboard aggregates by month, week, and model

### Built-in Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read local files (txt, md, py, json, csv, pdf, docx, xlsx, etc.) |
| `write_file` | Write or overwrite files on disk |
| `apply_patch` | Edit files via exact string replacement (old snippet → new content); supports multiple edits/files; errors out instead of corrupting the file when no/ambiguous match |
| `list_directory` | List directory contents |
| `run_command` | Run local commands (Git Bash preferred on Windows with PowerShell fallback; bash on macOS/Linux) with confirmation, allow-list, and timeout protection |
| `analyze_image` | Analyze a local image with the vision model for a specific question |
| `generate_image` | Generate an image with an image model and save it locally |
| `edit_image` | Edit an existing image from text instructions with Qwen-Image-Edit |
| `ocr_image` | Extract image text locally with offline RapidOCR |
| `web_search` | Search the internet via multiple engines with auto-fallback |
| `web_read` | Read forums/pages, remote PDFs, Word documents, and images; list page image candidates |
| `extract_images` | Extract web images, PDF pages, or embedded Word images for direct OCR or vision analysis |
| `browser_*` | Launch an isolated Edge/Chrome session, inspect page snapshots, click, type, scroll, and close |
| `ssh_*` | Maintain SSH sessions and execute remote commands in a ReAct loop |
| `read_conversations_by_date` | Read complete conversation history for a date range to create daily/weekly reports |
| `rlm_query` | Dispatch 1-16 sub-tasks to a low-cost model in parallel |
| `compact` | Manually trigger context compression |
| `background_run` / `background_check` | Run long shell commands asynchronously and poll their status |
| `todo_write` | Maintain a structured task list for multi-step work tracking |
| `subagent` | Spawn a focused sub-agent with its own tool loop |
| `glob_files` | Search files by glob pattern |
| `grep_files` | Search file contents by regex |
| `ask_user_question` | Ask the user a question and wait for response |
| `enter_plan_mode` / `exit_plan_mode` | Enter/exit planning mode |

Advanced tools also cover persistent tasks, a team message bus, and Git worktrees. Tools exposed by connected MCP Servers are added dynamically to the active agent.

### Multi-Engine Web Search

- **6 search backends** — Tavily, Brave Search, Firecrawl, Google Custom Search, SearXNG, DuckDuckGo
- **Auto-fallback** — If the preferred engine fails, automatically tries the next; DuckDuckGo (free) as ultimate fallback
- **Parallel fetching** — Search result pages fetched concurrently (up to 5 threads), significantly reducing wait time
- **Soft limit** — After 5 searches in one turn, the agent is nudged to consolidate results
- **Manual / Auto modes** — Auto lets the model decide; manual gives you a toolbar toggle

### Joint Text and Image Retrieval

- **Forum-aware text extraction** — `web_read` prioritizes readable content, preserves paragraph boundaries, and recognizes `srcset` and common lazy-load image attributes
- **Direct remote document reading** — PDF and DOCX URLs are detected, cached, and parsed automatically; PDF text includes page markers
- **Document image extraction** — `extract_images` can render selected PDF pages (preserving figures, captions, and layout), extract embedded PDF bitmaps, or unpack Word media
- **OCR first, vision on demand** — `extract_images(ocr=true)` runs the bundled RapidOCR immediately; text-heavy screenshots and scans need no vision API, while scenes, layouts, trends, and spatial relationships can still use `analyze_image`

### Image Tools

- **Targeted image analysis** — Only the absolute path is attached on send. Text-heavy images use local OCR first; the main model calls `analyze_image` only for visual semantics such as expressions, chart trends, layout, and specific regions. Vision requests have a configurable 10-300 second timeout and do not stack SDK retries
- **Anti-hallucination constraints** — The vision model is forced to report only what is actually visible, distinguish observation from speculation, read text/numbers verbatim, and say so when something is unclear — reducing wrong conclusions
- **Image generation** — `generate_image` calls an OpenAI-compatible `/v1/images/generations` endpoint (supports relays like New API / sub2api), saves locally, and renders a thumbnail card inline
- **Instruction-based image editing** — `edit_image` modifies an existing image from text instructions, including replacing objects, adding/removing elements, editing visible text, and style transfer, using Qwen-Image-Edit
- **Local OCR** — `ocr_image` uses the bundled RapidOCR ONNX engine offline, avoiding vision-model latency and usage charges for text extraction
- **Fetch model list** — One click in settings pulls the available model list from your vision/image-gen provider; click to fill it in
- **Separate config** — Independent `api_key` / `base_url` / `model` for vision and image-gen, configured under the "Image Tools" tab in settings

### Command Execution & Safety

- **Cross-platform shell** — Git for Windows bash is preferred so common Unix commands work directly; PowerShell is used as a fallback, while macOS/Linux use `/bin/bash`
- **Adaptive output decoding** — Git Bash prefers UTF-8 and PowerShell supports GBK/cp936 to reduce garbled Chinese output
- **Confirmation & allow-list** — Confirmation dialog before running commands; commands can be added to an allow-list for subsequent auto-execution; smart wildcard pattern suggestions
- **Timeout & interrupt** — Commands run with timeout protection and can be stopped anytime

### MCP & External Config

- **MCP client** — Supports stdio and Streamable HTTP transports; connected tools are registered dynamically with the agent
- **Visual management** — Add, edit, delete, enable, and test MCP Servers in settings, including commands, working directories, environment variables, URLs, and headers
- **Claude / Codex import** — Discover global and project-level Claude Code and Codex configs, then selectively import model configs or MCP Servers
- **Explicit save boundary** — Imported candidates show their source and only become active after the settings are saved

### Browser & Remote Operations

- **Browser control** — Launch a visible, isolated session in the locally installed Edge or Chrome, inspect page snapshots and element references, then click, type, and scroll
- **Isolation and confirmation** — The browser does not reuse the default profile or login state; open/click/type actions follow the confirmation policy, while passwords, verification codes, API keys, and payment details must be entered manually
- **SSH ReAct** — Connect with a key, SSH agent, or default private key and execute remote commands step by step; high-risk commands require confirmation

### Project Grouping & Working Directory

- **Conversation-bound project dir** — Each conversation can bind a project folder; tool relative paths resolve against it, fixing the model writing files to the wrong directory
- **Sidebar grouping by project** — Conversation list grouped into collapsible project sections; supports cross-group drag-to-reclassify and drag-to-reorder (with placeholder visual feedback)
- **Project picker home** — When starting a new conversation, choose a recent project, add a new one, or start with no project
- **Stale path warning** — When a project dir doesn't exist on this machine after cross-device sync, a banner offers one-click reset

### Conversation Management & Summaries

- **Temporary conversations** — Kept in memory only and excluded from disk persistence, the sidebar, search, archives, and cloud sync; discarded when switching back to a persistent conversation
- **Archive and bulk management** — Separate active/archive views with per-conversation, whole-project, and multi-select archive/restore/delete actions; actively generating conversations are protected
- **Compact long lists** — Each project shows its five most recent conversations by default and can be expanded; timestamps are visible in the sidebar
- **Visible-content search** — Searches titles and user/assistant message text while ignoring hidden tool results
- **Daily and weekly reports** — The agent can read complete conversations by date range and use the injected current date to prepare daily, weekly, or milestone summaries

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
- **Conversation management** — Project grouping, drag-to-reorder, visible-content search, temporary conversations, archives, bulk actions, rename, and delete
- **Collapsible tool bubbles** — Tool calls and results in collapsible message bubbles
- **File change panel** — File writes are grouped by path with cumulative added/removed line counts; click to inspect a line-numbered diff or locate the file
- **Chat navigation** — Previous/next message buttons with smooth scroll animation
- **Markdown & LaTeX** — Full rendering with marked.js and KaTeX (offline, no CDN)
- **Theme support** — Light and dark themes, adjustable font size
- **Context progress bar** — Real-time token usage display, auto-refreshes on conversation switch
- **Usage dashboard** — Monthly heatmap, weekly bars, and model distribution with input, output, total, cache-hit, and cache-miss metrics
- **Dynamic weather background** — Time-aware city scenes with clear, cloudy, rain, snow, fog, and thunder states; rain uses WebGL2 refraction with a Canvas fallback

## Screenshots

> <img width="1238" height="748" alt="QQ20260524-122750-HD" src="https://github.com/user-attachments/assets/f334c249-8b9c-4176-bb22-6e3b364bb37e" />

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  pywebview (WebView2 / WebKit)                          │
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
         │  ┌──────┐ ┌────────┐ ┌───────┐ ┌────────┐ │
         │  │ File │ │ Search │ │  MCP  │ │Browser │ │
         │  │ I/O  │ │ (6 eng)│ │ Tools │ │ / SSH  │ │
         │  └──────┘ └────────┘ └───────┘ └────────┘ │
         └─────────────────────────────────────────┘
```

## Requirements

- Windows 10/11 with [WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) (pre-installed on Win11); or macOS (uses the built-in WebKit, no extra runtime)
- Python 3.10+
- At least one LLM provider API key

## Installation

### Download a Release

Download the latest build from [GitHub Releases](https://github.com/SolitudeZY/Deepseek-GUI/releases):

- Windows: `QuickModel-Setup.exe` (Inno Setup installer)
- macOS Apple Silicon: `QuickModel-mac-arm64.zip`

### Run from source

```bash
git clone https://github.com/SolitudeZY/Deepseek-GUI.git
cd Deepseek-GUI

# requirements.txt includes platform markers; pyobjc is installed on macOS
pip install -r requirements.txt

python main.py
```

### Build

```bash
pip install pyinstaller

# Windows: produce the dist/QuickModel/ onedir bundle
pyinstaller QuickModel.spec --clean

# Then build the installer with Inno Setup 6 (PowerShell)
iscc /DMyAppVersion=X.Y.Z installer.iss

# macOS: produce dist/QuickModel.app
pyinstaller main_mac.spec --clean
```

Windows uses `onedir + Inno Setup` instead of `onefile` to avoid Python DLL load failures after an in-app update. A `v*` Git tag triggers GitHub Actions to build both the Windows installer and macOS app archive. Use `python bump_version.py X.Y.Z` for releases so the application version, commit, tag, and push stay synchronized.

## Quick Start

> See [Usage Guide (Chinese)](./使用说明.md) | [LLM API Base URL Reference](./主流%20LLM%20模型的%20API%20Base%20URL%20汇总.md)

1. Launch the app and click **Settings** in the top-right
2. Under "Model Config", choose a protocol/provider type and enter the API Key, Base URL, and model, or import an existing Claude/Codex config
3. Optional: add an MCP Server or import local Claude/Codex MCP configs
4. Optional: configure search keys, image tools, cloud sync, and the dynamic weather background
5. Save settings, then choose a project folder or start without a project

## Tips

- **Thinking mode**: Use high/max for complex reasoning; off for simple Q&A to save tokens
- **Web search**: Use auto mode for research tasks; switch to manual to control search usage
- **Temporary chat**: Use the sidebar's temporary entry for conversations that should not enter history, search, or cloud sync
- **RLM**: Ask the agent to batch-process tasks (e.g., "translate these 10 paragraphs") and it will use parallel sub-tasks
- **Compact**: If the conversation gets too long, use `/compact` or wait for auto-compact
- **Daily/weekly reports**: Ask the agent to summarize last week's conversations; it will resolve the dates and load the matching history
- **Cloud sync**: After setting the sync folder, click "Upload All" to backup; on a new PC click "Import All" to restore
- **Skills**: Save frequently-used prompts as skills for quick reuse

## Project Structure

```
quick_model/
├── main.py              # Entry point
├── QuickModel.spec      # Windows onedir build config
├── main_mac.spec        # macOS app bundle config
├── installer.iss        # Windows Inno Setup installer
├── app/
│   ├── agent.py         # Core agent loop (split into stream/parse, tool exec, context mgmt)
│   ├── tools.py         # Built-in tool implementations (file, search, shell)
│   ├── browser_tools.py # Playwright browser control (Edge / Chrome)
│   ├── model_protocol.py # Chat Completions / Responses / Anthropic adapters
│   ├── mcp_client.py    # MCP stdio / Streamable HTTP client
│   ├── external_config.py # Claude / Codex config discovery and import
│   ├── retrieval.py     # Web/remote document parsing and image extraction
│   ├── advanced_tools.py # Sub-agent, task, background task, todo management
│   ├── skills.py        # Skill CRUD, import, memory persistence
│   ├── team.py          # Multi-agent team, message bus (thread-safe), worktree
│   ├── sync.py          # Cloud sync module (conversations + config upload/detect/import)
│   ├── webview_app.py   # pywebview API bridge (Python ↔ JavaScript)
│   ├── config.py        # Configuration loading/saving with defaults
│   ├── conversation.py  # Conversation CRUD, import/export, sort ordering
│   ├── compact.py       # Context compression and summarization
│   ├── token_usage.py   # Token records and weekly/monthly aggregation
│   ├── vision.py        # Image description & image generation via vision API
│   └── static/          # HTML/CSS/JS frontend
│       ├── index.html   # Main UI layout
│       ├── core.js      # Shared state and DOM references (loaded first)
│       ├── render.js    # Markdown, KaTeX, and code rendering
│       ├── drag.js      # Manual conversation drag/reorder engine
│       ├── dialogs.js   # Questions, confirmation, lightbox, and diff dialogs
│       ├── settings.js  # Settings, MCP, model, and sync management
│       ├── starfield.js # City, weather, and star-trail background engine
│       ├── app.js       # Conversations, messages, streaming callbacks, main UI
│       ├── style.css    # Dark/light theme styles
│       └── animations.css # Animation and transition effects
└── tests/               # Conversation, protocol, browser, and usage tests
```

User data stays outside the repository: `%APPDATA%/AIDesktopAssistant/` on Windows and `~/Library/Application Support/AIDesktopAssistant/` on macOS.

## Tech Stack

- **Frontend**: pywebview (WebView2 on Windows / WebKit on macOS), HTML/CSS/JS
- **Backend**: Python 3.10+, OpenAI SDK, Anthropic SDK, MCP Python SDK
- **Rendering**: marked.js, KaTeX, highlight.js (all local, offline)
- **Automation**: Playwright (local Edge / Chrome), Paramiko (SSH), RapidOCR (offline OCR)
- **Concurrency**: threading + ThreadPoolExecutor (search fetching, background commands, multi-agent teams)
- **Packaging**: PyInstaller onedir + Inno Setup on Windows; PyInstaller app bundle on macOS

## License

MIT
