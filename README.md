# QuickModel

Windows 桌面 AI 助手，支持通过 OpenAI 兼容 API 接入多家 LLM 服务商。基于 pywebview (WebView2) + Python 后端构建。

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

中文 | [English](./README.en.md)

## 功能特性

### 核心 Agent

- **多服务商支持** — 兼容任何 OpenAI 格式 API：DeepSeek (V3/R1/V4 Pro/V4 Flash)、OpenAI、Qwen、Ollama 等
- **多模型配置** — 设置中可配置多个模型后端，随时切换
- **思考模式 (off / high / max)** — 三级推理强度，工具栏按钮循环切换，跨会话持久化
- **自动压缩** — 上下文超过 600k token 自动摘要压缩（压缩阈值支持自定义）；支持 `/compact` 手动压缩；前缀缓存感知压缩保留 DeepSeek 缓存命中
- **图片理解** — 拖拽或粘贴图片即可分析，默认使用 Qwen-VL 视觉模型
- **实时费用追踪** — 侧边栏显示每轮/每会话 token 用量及缓存命中率

### 内置工具

| 工具 | 说明 |
|------|------|
| `read_file` | 读取本地文件（txt, md, py, json, csv, pdf, docx, xlsx 等） |
| `write_file` | 写入或覆盖文件 |
| `apply_patch` | 应用 unified diff 补丁精确修改指定行 |
| `list_directory` | 列出目录内容 |
| `run_command` | 执行 PowerShell 命令（带确认对话框） |
| `web_search` | 多引擎网络搜索，自动降级 |
| `web_read` | 抓取并读取完整网页内容 |
| `rlm_query` | 并行派发 1-16 个子任务到低成本模型 |
| `compact` | 手动触发上下文压缩 |
| `todo_write` | 维护结构化任务清单 |
| `subagent` | 派生子 Agent 独立执行工具循环 |
| `glob_files` | 按模式匹配搜索文件 |
| `grep_files` | 按内容搜索文件 |

### 多引擎网络搜索

- **6 种搜索后端** — Tavily、Brave Search、Firecrawl、Google Custom Search、SearXNG、DuckDuckGo
- **自动降级** — 首选引擎失败时自动尝试下一个；DuckDuckGo（免费无需 Key）作为最终兜底
- **自动阅读** — 自动抓取搜索结果页面全文，减少二次搜索
- **软限制** — 单轮超过 5 次搜索后提示模型整合结果
- **手动/自动模式** — Auto 由模型决定是否搜索；Manual 通过工具栏开关控制

### 云同步与导入导出

- **云同步** — 支持将对话自动同步到本地云盘文件夹（坚果云/OneDrive 等），实现跨电脑无缝使用
- **自动上传** — 对话完成后自动复制到同步文件夹
- **启动检测** — 每次启动自动检测云端新对话，标题栏提示
- **选择性导入** — 复选框界面，可自行选择要导入的对话
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
- **消息总线** — 内存收件箱/发件箱，Agent 间通信
- **UI 通知** — 团队成员完成工作时实时回调

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


## 环境要求

- Windows 10/11，需安装 [WebView2 Runtime](https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/)（Win11 通常已预装）
- Python 3.10+
- 至少一家 LLM 服务商的 API Key

## 安装

### 从源码运行

```bash
git clone https://github.com/SolitudeZY/Deepseek-GUI.git
cd Deepseek-GUI

pip install openai pywebview tavily-python duckduckgo-search firecrawl-py

python main.py
```

### 下载预编译 .exe

从 [Releases](https://github.com/SolitudeZY/Deepseek-GUI/releases) 下载 `QuickModel.exe`，双击直接运行，无需安装。

## 打包

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name QuickModel --icon=icon.ico --add-data "app/static;app/static" --add-data "icon.ico;." main.py
```

输出文件：`dist/QuickModel.exe`

## 配置

首次启动后，点击右上角**设置**进行配置。配置文件存储于 `%APPDATA%\AIDesktopAssistant\config.json`。

| 配置项 | 说明 |
|--------|------|
| `model_configs` | 多模型后端配置（设置中可切换） |
| `thinking` | 推理强度：`"off"`、`"high"` 或 `"max"` |
| `search_engine` | 首选搜索引擎：`tavily`、`brave`、`firecrawl`、`duckduckgo`、`google`、`searxng` |
| `search_fallback` | 失败时自动降级到其他引擎 |
| `sync_folder` | 云同步文件夹路径（如坚果云同步目录） |
| `sync_auto_upload` | 对话完成后自动上传到同步文件夹 |
| `vision_api_key` / `vision_model` | 图片理解模型配置 |

## 支持的服务商

| 服务商 | Base URL |
|--------|----------|
| DeepSeek | `https://api.deepseek.com/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Ollama（本地） | `http://localhost:11434/v1` |
| DashScope（通义千问） | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 其他 OpenAI 兼容 API | 自定义地址 |

## 使用技巧

- **云同步**：设置中配置同步文件夹后，对话自动上传；在另一台电脑上点击"检测新对话"即可导入
- **技能**：打开技能面板创建或导入专业化提示词
- **Worktree**：需要修改代码时，让 Agent 先创建 worktree 进行隔离
- **记忆**：告诉 Agent "记住这个..."，它会保存到持久记忆
- **思考**：通过 💭 按钮循环切换 off → high → max；off 快速响应，max 深度推理
- **搜索**：研究任务用 auto 模式；想控制搜索用量时切换到 manual
- **RLM**：让 Agent 批量处理任务（如"翻译这 10 段"），会自动使用并行子任务
- **Compact**：对话过长时使用 `/compact` 或等待自动压缩

## 项目结构

```
quick_model/
├── main.py              # 入口
├── app/
│   ├── agent.py         # 核心 Agent 循环、工具调度、压缩逻辑
│   ├── tools.py         # 内置工具实现（文件、搜索、命令）
│   ├── advanced_tools.py # 子 Agent、任务、后台任务、Todo 管理
│   ├── skills.py        # 技能 CRUD、导入、记忆持久化
│   ├── team.py          # 多 Agent 团队、消息总线、Worktree 索引
│   ├── sync.py          # 云同步模块（上传/检测/导入）
│   ├── webview_app.py   # pywebview API 桥接（Python ↔ JavaScript）
│   ├── config.py        # 配置加载/保存
│   ├── conversation.py  # 对话 CRUD、导入导出、排序
│   ├── compact.py       # 上下文压缩与摘要
│   ├── vision.py        # 图片描述（Vision API）
│   ├── command_safety.py # 命令白名单与模式匹配
│   ├── static/          # HTML/CSS/JS 前端
│   │   ├── index.html   # 主界面布局
│   │   ├── app.js       # 前端逻辑与事件处理
│   │   ├── style.css    # 深色/浅色主题样式
│   │   └── animations.css # 动画与过渡效果
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
