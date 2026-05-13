# QuickModel

Windows 桌面 AI 助手，支持通过 OpenAI 兼容 API 接入多家 LLM 服务商。基于 pywebview (WebView2) + Python 后端构建。

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

[English](./README.md) | 中文

## 功能特性

### 核心 Agent
- **多服务商支持** — 兼容任何 OpenAI 格式 API：DeepSeek（V3/R1/V4 Pro/V4 Flash）、OpenAI、Qwen、Ollama 等
- **多模型配置** — 在设置中配置并切换多个模型后端
- **推理强度三档（关 / 高 / 深）** — 工具栏循环切换思考深度，跨会话持久化
- **自动压缩** — 超过 80k token（V4 模型 800k）自动总结压缩上下文；支持 `/compact` 手动压缩；前缀缓存感知压缩策略最大化 DeepSeek 缓存命中
- **图片理解** — 粘贴或拖拽图片到聊天中，通过 Qwen-VL 或任意视觉 API 描述并注入上下文
- **实时成本跟踪** — 按轮次和会话统计 token 用量，含缓存命中/未命中明细，侧边栏实时显示

### 内置工具
| 工具 | 描述 |
|------|------|
| `read_file` | 读取本地文件（txt、md、py、json、csv、pdf、docx、xlsx 等） |
| `write_file` | 写入或覆盖磁盘文件 |
| `apply_patch` | 用 unified diff 格式精准修改文件指定行（比 `write_file` 更安全） |
| `list_directory` | 列出目录内容 |
| `run_command` | 执行 PowerShell 命令（带确认弹窗） |
| `web_search` | 通过多引擎搜索互联网，支持自动降级 |
| `web_read` | 获取并阅读完整网页内容（HTML → 纯文本） |
| `rlm_query` | 并行派发 1–16 个子任务到低成本模型（deepseek-v4-flash） |
| `compact` | 手动触发上下文压缩 |
| `todo_write` | 维护结构化待办清单，追踪多步骤工作 |
| `subagent` | 生成专注的子代理，拥有独立工具循环 |

### 多引擎网络搜索
- **6 个搜索后端** — Tavily、Brave Search、Firecrawl、Google Custom Search、SearXNG、DuckDuckGo
- **自动降级** — 首选引擎失败时自动尝试下一个可用引擎；DuckDuckGo（免费无需 key）作为最终兜底
- **自动读取** — 搜索完成后自动抓取前几个结果的完整网页内容，减少后续搜索次数
- **软限制** — 单轮搜索达 5 次后，自动提示 Agent 整理已有结果
- **自动/手动模式** — 自动模式下模型自行决定搜索；手动模式下由工具栏按钮控制

### 技能系统（Skills）
- **内置与自定义技能** — 保存并复用提示词模板，改变 Agent 行为
- **导入 Claude 风格技能** — 从文件夹导入（自动检测 `SKILL.md` + 附属文件，支持批量导入）
- **完整管理面板** — 创建、编辑、删除技能

### 记忆系统（Memory）
- **持久化键值存储** — Agent 可跨对话保存和回忆事实（`memory_read`、`memory_write`）
- **自动注入** — `/new` 新建对话时自动注入记忆摘要

### 工作树隔离（Worktree）
- **Git Worktree 集成** — 每个对话可在独立 worktree 中操作
- **命令安全** — 执行前确认弹窗，支持智能通配符模式建议（`git *`、`python *`）
- **工作树面板** — 侧面板显示活跃工作树、分支及绑定任务

### 团队协作（Team）
- **多 Agent 团队** — 生成在独立线程中运行的持久化团队成员
- **消息总线** — 内存收件箱/发件箱实现 Agent 间通信
- **UI 通知** — 团队成员完成工作时实时回调

### 任务管理（Task）
- **持久化任务** — 跨对话存活的结构化任务
- **依赖图** — 任务间可互相阻塞（pending → in_progress → completed）
- **工作树绑定** — 移除 worktree 时自动完成绑定任务

### RLM 并行处理
- **批量子任务** — 一次派发最多 16 个独立提示词到 deepseek-v4-flash 并行执行
- **应用场景** — 批量翻译、代码审查、多文件分析、数据提取
- **自动选择模型** — 从已配置的模型列表中自动选取 flash 模型

### 用户界面
- **pywebview 桌面应用** — 原生窗口承载网页聊天界面
- **对话管理** — 侧边栏支持拖拽排序、搜索、重命名、删除、导出为 Markdown
- **可折叠工具气泡** — 工具调用和结果以可折叠气泡展示
- **聊天导航** — 上/下一条消息按钮，平滑滚动动画
- **Markdown & LaTeX** — 完整渲染支持，marked.js + KaTeX（本地离线，无 CDN）
- **主题支持** — 浅色/深色主题，可调节字号
- **成本与上下文显示** — 侧边栏实时显示 token 用量、缓存命中率、上下文使用情况

## 截图

> 即将更新

## 环境要求

- Windows 10/11，需安装 [WebView2 Runtime](https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/)（Win11 通常已预装）
- Python 3.10+
- 至少一家 LLM 服务商的 API Key

## 安装

### 从源码运行

```bash
git clone https://github.com/your-username/quick-model.git
cd quick-model

pip install openai pywebview tavily-python duckduckgo-search firecrawl-py

python main.py
```

### 下载预编译 .exe

从 [Releases](https://github.com/your-username/quick-model/releases) 下载 `QuickModel.exe`，双击直接运行，无需安装。

## 打包

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name QuickModel --icon=icon.ico --add-data "app/static;app/static" --add-data "icon.ico;." main.py
```

输出文件：`dist/QuickModel.exe`

## 配置

首次启动后，点击右上角**设置**进行配置。配置文件存储于 `%APPDATA%\AIDesktopAssistant\config.json`。

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

| 配置项 | 说明 |
|--------|------|
| `model_configs` | 多模型后端（可在设置中切换） |
| `thinking` | 推理强度：`"off"`（关）、`"high"`（高）、`"max"`（深） |
| `search_engine` | 首选搜索引擎：`tavily`、`brave`、`firecrawl`、`duckduckgo`、`google`、`searxng` |
| `search_fallback` | 失败时自动降级到下一个可用引擎 |
| `tavily_api_key` | [app.tavily.com](https://app.tavily.com) — 免费 1000 次/月 |
| `brave_api_key` | [brave.com/search/api](https://brave.com/search/api/) — 免费 2000 次/月 |
| `firecrawl_api_key` | [firecrawl.dev](https://www.firecrawl.dev) — 免费 500 次/月，返回完整 Markdown |
| `google_api_key` / `google_cx` | Google Custom Search — 免费 100 次/天（2026年起仅限 50 个域名） |
| `searxng_url` | 自建 SearXNG 实例地址 |
| `search_mode` | `"auto"` = 模型自行决定；`"manual"` = 用户工具栏手动开关 |
| `vision_api_key` / `vision_base_url` / `vision_model` | 图片描述的视觉模型 |

## 支持的服务商

| 服务商 | Base URL |
|--------|----------|
| DeepSeek | `https://api.deepseek.com/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Ollama（本地） | `http://localhost:11434/v1` |
| DashScope（通义千问） | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 其他 OpenAI 兼容 API | 自定义地址 |

## 使用技巧

- **技能**：开始任务前先打开技能面板创建或导入专业化配置
- **工作树**：当 Agent 需要修改代码时，先让它创建 worktree 以隔离环境
- **记忆**：对 Agent 说「记住这个…」，它会保存到持久化记忆中
- **推理强度**：用 💭 按钮在 关 → 高 → 深 间循环切换；简单任务用「关」加速响应，复杂推理用「深」
- **搜索**：研究类任务用自动模式；需要控制搜索用量时切换到手动模式
- **RLM 并行**：让 Agent 批量处理任务（如「翻译这 10 段文字」），它会自动使用并行子任务
- **apply_patch**：精确代码修改时，Agent 会使用 unified diff 而非覆盖整个文件
- **压缩**：对话过长时使用 `/compact` 或等待自动压缩
- **成本**：侧边栏实时查看 token 用量和缓存命中率，优化 API 费用

## 项目结构

```
quick_model/
├── main.py              # 入口文件
├── app/
│   ├── agent.py         # 核心 Agent 循环、工具分发、压缩逻辑
│   ├── tools.py         # 内置工具实现（文件、搜索、Shell）
│   ├── advanced_tools.py # 子代理、任务、后台任务、待办管理
│   ├── skills.py        # 技能 CRUD、导入、记忆持久化
│   ├── team.py          # 多 Agent 团队、消息总线、worktree 索引
│   ├── webview_app.py   # pywebview API 桥接（Python ↔ JavaScript）
│   ├── config.py        # 配置加载/保存，默认值
│   ├── conversation.py  # 对话 CRUD、导出、排序
│   ├── compact.py       # 上下文压缩和总结
│   ├── vision.py        # 通过视觉 API 进行图片描述
│   ├── command_safety.py # 命令白名单和模式匹配
│   ├── static/          # HTML/CSS/JS 前端
│   │   ├── index.html   # 主界面布局
│   │   ├── app.js       # 前端逻辑与事件处理
│   │   └── style.css    # 深色/浅色主题样式
│   └── skills/          # 默认技能定义（.md 文件）
└── conversations/       # 对话历史（自动创建）
```

## 技术栈

- **前端**：pywebview (WebView2)、HTML/CSS/JS
- **后端**：Python、OpenAI SDK
- **渲染**：marked.js、KaTeX、highlight.js（全部本地离线）
- **打包**：PyInstaller

## 许可证

MIT
