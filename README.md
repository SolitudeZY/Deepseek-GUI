# QuickModel——Deepseek GUI

Windows / macOS 桌面 AI 助手，支持通过 OpenAI 兼容 API 接入多家 LLM 服务商。基于 pywebview (WebView2 / WebKit) + Python 后端构建。

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

中文 | [English](./README.en.md)

> 详细图文教程请参阅 [使用说明](./使用说明.md) | [主流 LLM 模型的 API Base URL 汇总](./主流%20LLM%20模型的%20API%20Base%20URL%20汇总.md)

## 功能特性

### 核心 Agent

- **多服务商支持** — 兼容任何 OpenAI 格式 API：DeepSeek (V3/R1/V4 Pro/V4 Flash)、OpenAI、Qwen、Ollama 等
- **多模型配置** — 设置中可配置多个模型后端，随时切换；每个模型可独立设置上下文长度和压缩阈值
- **思考模式 (off / high / max)** — 三级推理强度，工具栏按钮循环切换，跨会话持久化
- **自动压缩** — 上下文超过阈值自动摘要压缩（默认 600K，可自定义）；支持 `/compact` 手动压缩；前缀缓存感知压缩保留 DeepSeek 缓存命中
- **图片理解（针对性分析）** — 拖拽或粘贴图片即可分析。发送时仅附图片路径，由主模型按当前问题调用 `analyze_image` 工具做针对性分析（而非预生成通用描述）；内置反幻觉约束，只报告图中实际可见内容、区分观察与推测。默认使用 Qwen-VL 视觉模型
- **图片生成** — 用户要求生成/绘制图片时，主模型调用 `generate_image` 工具，经 OpenAI 兼容接口（支持 New API、sub2api 等中转）生成并保存到本地，对话中直接显示缩略图（点击放大）
- **实时费用追踪** — 侧边栏显示每轮/每会话 token 用量及缓存命中率

### 内置工具

| 工具 | 说明 |
|------|------|
| `read_file` | 读取本地文件（txt, md, py, json, csv, pdf, docx, xlsx 等） |
| `write_file` | 写入或覆盖文件 |
| `apply_patch` | 精确字符串替换修改文件（原文片段 → 新内容），支持多处/多文件编辑；匹配不到或不唯一时报错而非写坏文件 |
| `list_directory` | 列出目录内容 |
| `run_command` | 执行命令（Windows 用 PowerShell，macOS/Linux 用 bash），带确认对话框与命令白名单，可记住允许的命令自动执行 |
| `analyze_image` | 用视觉模型针对具体问题分析本地图片 |
| `generate_image` | 用生图模型生成图片并保存到本地 |
| `web_search` | 多引擎网络搜索，自动降级 |
| `web_read` | 抓取并读取完整网页内容 |
| `rlm_query` | 并行派发 1-16 个子任务到低成本模型 |
| `compact` | 手动触发上下文压缩 |
| `todo_write` | 维护结构化任务清单 |
| `subagent` | 派生子 Agent 独立执行工具循环 |
| `glob_files` | 按模式匹配搜索文件 |
| `grep_files` | 按内容搜索文件 |
| `ask_user_question` | 向用户提问并等待回答 |
| `enter_plan_mode` / `exit_plan_mode` | 进入/退出计划模式 |

### 多引擎网络搜索

- **6 种搜索后端** — Tavily、Brave Search、Firecrawl、Google Custom Search、SearXNG、DuckDuckGo
- **自动降级** — 首选引擎失败时自动尝试下一个；DuckDuckGo（免费无需 Key）作为最终兜底
- **并行抓取** — 搜索结果页面并发抓取全文（最多 5 线程），大幅减少等待时间
- **软限制** — 单轮超过 5 次搜索后提示模型整合结果
- **手动/自动模式** — Auto 由模型决定是否搜索；Manual 通过工具栏开关控制

### 图片工具

- **针对性图片分析** — 发送图片时仅附绝对路径，主模型按当前对话上下文撰写贴合问题的 `question` 调用 `analyze_image`，获得有针对性的结果（人物表情、图表数值、代码截图文字、特定区域细节等），而非泛泛的全景描述
- **反幻觉约束** — 视觉模型被强制只报告实际可见内容、区分观察与推测、文字/数值逐字符照读、看不清就说不清，降低错误结论风险
- **图片生成** — 调用 `generate_image` 经 OpenAI 兼容 `/v1/images/generations` 生成图片，支持 New API / sub2api 等中转，保存到本地并在对话中显示缩略图卡片
- **读取模型列表** — 设置面板可一键拉取视觉/生图服务商的可用模型列表，点击直接填入
- **配套配置** — 视觉与生图各自独立的 `api_key` / `base_url` / `model`，设置面板「图片工具」标签分子页配置

### 命令执行与安全

- **跨平台 Shell** — Windows 走 PowerShell、macOS/Linux 走 bash；输出编码自适应（Windows 兼容 GBK）
- **命令确认与白名单** — 执行命令前弹确认对话框，可将命令加入允许列表实现后续自动执行；支持智能通配符模式建议
- **超时与中断** — 命令带超时保护，可随时停止执行

### 项目分组与工作目录

- **会话绑定项目目录** — 每个会话可绑定一个项目文件夹，工具的相对路径以此为基准，根治模型把文件写到错误目录的问题
- **侧边栏按项目分组** — 对话列表按项目折叠分组，支持跨组拖拽归类、拖拽排序（带占位块视觉反馈）
- **主页项目选择** — 新建对话时可选最近项目、添加新项目或无项目快速开始
- **路径失效提示** — 跨设备同步后项目目录在本机不存在时，顶部提示并可一键重设

### 云同步与导入导出

- **一键全量同步** — 对话历史 + 配置文件一键上传到云盘文件夹（坚果云/OneDrive 等）
- **一键全量导入** — 换电脑时一键导入所有对话和配置，无需手动迁移
- **自动上传** — 对话完成后自动复制到同步文件夹
- **启动检测** — 每次启动自动检测云端新对话，标题栏提示
- **选择性导入** — 复选框界面，可自行选择要导入的对话
- **配置同步** — API Key、模型配置、允许的命令列表等全部同步（本机同步路径不会被覆盖）
- **导出为 Markdown** — 仅导出用户和助手的对话内容，不含工具调用
- **导入对话** — 支持从 .json（完整备份）或 .md（导出格式）文件导入历史对话

### 技能系统

- **内置与自定义技能** — 保存并复用提示词模板
- **导入 Claude 风格技能** — 从文件夹导入（自动识别 `SKILL.md` + 附属文件，支持批量导入）
- **完整管理面板** — 创建、编辑、删除技能

### 记忆系统

- **持久化键值存储** — Agent 可跨对话保存和回忆信息（`memory_read`、`memory_write`）
- **自动注入** — 新对话开始时自动注入记忆摘要

### Worktree 隔离

- **Git worktree 集成** — 每个对话可在独立 worktree 中操作
- **命令安全** — 确认对话框，支持智能通配符模式建议
- **Worktree 面板** — 侧面板显示活跃 worktree、分支和绑定任务

### 多 Agent 协作

- **多 Agent 团队** — 派生持久化团队成员，独立线程运行
- **消息总线** — 线程安全的收件箱/发件箱，Agent 间通信
- **UI 通知** — 团队成员完成工作时实时回调
- **空闲自动认领** — 空闲成员自动从任务板认领未分配任务

### 任务管理

- **持久化任务** — 跨对话存续的结构化任务
- **依赖图** — 任务间可设置阻塞关系（pending → in_progress → completed）
- **Worktree 绑定** — 绑定的 worktree 移除时任务自动完成

### RLM 并行处理

- **批量子任务** — 最多并行派发 16 个独立提示到 deepseek-v4-flash
- **应用场景** — 批量翻译、代码审查、多文件分析、数据提取
- **自动选模型** — 自动从已配置模型列表中选择 flash 模型

### 界面

- **pywebview 桌面应用** — 原生窗口 + Web 聊天界面
- **对话管理** — 侧边栏拖拽排序、搜索（标题+内容）、重命名、删除
- **可折叠工具气泡** — 工具调用和结果以可折叠消息气泡展示
- **聊天导航** — 上/下一条消息按钮，平滑滚动
- **Markdown & LaTeX** — 完整渲染，使用 marked.js 和 KaTeX（本地离线，无 CDN）
- **主题支持** — 深色/浅色主题，可调字体大小
- **上下文进度条** — 实时显示 token 用量和上下文利用率，切换对话时自动刷新
- **CSS 动画** — 丰富的过渡动画和交互反馈，不受系统"减少动画"设置影响
- **随机彩色边框** — 对话列表 active 项每次点击随机换色

## 截图

> <img width="1238" height="748" alt="QQ20260524-122750-HD" src="https://github.com/user-attachments/assets/f334c249-8b9c-4176-bb22-6e3b364bb37e" />

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  pywebview (WebView2)                                   │
│  ┌───────────────┐    JS ↔ Python API    ┌───────────┐  │
│  │  Frontend     │◄─────────────────────►│  Backend  │  │
│  │  HTML/CSS/JS  │                       │  Python   │  │
│  └───────────────┘                       └─────┬─────┘  │
└────────────────────────────────────────────────┼────────┘
                                                 │
         ┌───────────────────────────────────────┼──────┐
         │              Agent Loop               │      │
         │  ┌─────────┐  ┌──────────┐    ┌───────┴───┐  │
         │  │ Stream & │  │ Tool    │    │ Context   │  │
         │  │ Parse    │  │ Registry│    │ Manager   │  │
         │  └─────────┘  └──────────┘    └───────────┘  │
         └──────────────────────────────────────────────┘
                          │
         ┌────────────────┼────────────────────────┐
         │                ▼                        │
         │  ┌──────┐ ┌────────┐ ┌──────┐ ┌─────┐   │
         │  │ File │ │ Search │ │ Team │ │ ... │   │
         │  │ I/O  │ │ (6 eng)│ │ Bus  │ │     │   │
         │  └──────┘ └────────┘ └──────┘ └─────┘   │
         └─────────────────────────────────────────┘
```

## 环境要求

- Windows 10/11，需安装 [WebView2 Runtime](https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/)（Win11 通常已预装）；或 macOS（使用系统自带 WebKit，无需额外运行时）
- Python 3.10+
- 至少一家 LLM 服务商的 API Key

## 安装

### 从源码运行

```bash
git clone https://github.com/SolitudeZY/Deepseek-GUI.git
cd Deepseek-GUI

# Windows
pip install openai pywebview tavily-python duckduckgo-search firecrawl-py

# macOS（额外需要 pyobjc 提供 cocoa/WebKit 后端）
pip install -r requirements.txt

python main.py
```

### 打包

```bash
pip install pyinstaller

# Windows
pyinstaller --onefile --windowed --name QuickModel --icon=icon.ico --add-data "app/static;app/static" --add-data "icon.ico;." main.py

# macOS（注意 --add-data 分隔符为 : 且产出 .app）
pyinstaller --windowed --name QuickModel --icon=icon.icns --add-data "app/static:app/static" --add-data "icon.png:." main.py
```

Windows 生成的 `dist/QuickModel/` 文件夹（或单文件 exe）可直接分发；macOS 生成 `dist/QuickModel.app`。

## 快速开始

> 详细图文教程请参阅 [使用说明](./使用说明.md) | [主流 LLM 模型的 API Base URL 汇总](./主流%20LLM%20模型的%20API%20Base%20URL%20汇总.md)

1. 启动后点击右上角 **设置**
2. 在「模型配置」中填入 API Key 和 Base URL
3. 可选：配置搜索引擎 Key（Tavily/Brave 等）
4. 可选：配置云同步文件夹实现跨电脑同步
5. 关闭设置，开始对话

## 使用技巧

- **思考模式**：复杂推理任务开启 high/max；简单问答用 off 节省 token
- **联网搜索**：研究任务用 auto 模式；想控制搜索用量时切换到 manual
- **RLM**：让 Agent 批量处理任务（如"翻译这 10 段"），会自动使用并行子任务
- **Compact**：对话过长时使用 `/compact` 或等待自动压缩
- **云同步**：设置同步文件夹后，点「一键上传全部」即可备份；新电脑点「一键导入全部」恢复
- **技能**：常用提示词保存为技能，下次直接调用

## 项目结构

```
quick_model/
├── main.py              # 入口
├── app/
│   ├── agent.py         # 核心 Agent 循环（拆分为流式解析/工具执行/上下文管理）
│   ├── tools.py         # 内置工具实现（文件、搜索、命令）
│   ├── advanced_tools.py # 子 Agent、任务、后台任务、Todo 管理
│   ├── skills.py        # 技能 CRUD、导入、记忆持久化
│   ├── team.py          # 多 Agent 团队、消息总线（线程安全）、Worktree
│   ├── sync.py          # 云同步模块（对话+配置 上传/检测/导入）
│   ├── webview_app.py   # pywebview API 桥接（Python ↔ JavaScript）
│   ├── config.py        # 配置加载/保存
│   ├── conversation.py  # 对话 CRUD、导入导出、排序
│   ├── compact.py       # 上下文压缩与摘要
│   ├── vision.py        # 图片描述与图片生成（Vision API）
│   └── static/          # HTML/CSS/JS 前端
│       ├── index.html   # 主界面布局
│       ├── app.js       # 前端逻辑与事件处理
│       ├── style.css    # 深色/浅色主题样式
│       └── animations.css # 动画与过渡效果
└── conversations/       # 对话历史（自动创建于 %APPDATA%）
```

## 技术栈

- **前端**：pywebview（Windows: WebView2 / macOS: WebKit）、HTML/CSS/JS
- **后端**：Python 3.10+、OpenAI SDK
- **渲染**：marked.js、KaTeX、highlight.js（全部本地离线）
- **并发**：threading + ThreadPoolExecutor（搜索并行抓取、多 Agent 团队）
- **打包**：PyInstaller

## 许可证

MIT
