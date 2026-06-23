# AGENTS.md

本文件供 AI 编码助手（Cursor、GitHub Copilot、Codex、Cline、Zed 等支持 `AGENTS.md` 约定的工具）自动加载，帮助快速了解本项目。

## 项目说明的唯一真源：CLAUDE.md

**本项目完整的开发约定、架构说明、构建流程、关键陷阱都记录在仓库根目录的 [`CLAUDE.md`](./CLAUDE.md) 中。**

开始任何开发前，请先完整阅读 `CLAUDE.md`。它是本项目说明的唯一真源，本文件不重复其内容，以免两处脱节。`CLAUDE.md` 涵盖：

- **运行 / 构建**：conda 环境 `ai_api`、入口 `main.py`、Windows/macOS 打包命令
- **架构**：pywebview（WebView2）前端 + Python 后端的模块划分（`app/` 各文件职责）
- **前端 JS 模块拆分**：`app/static/` 下普通 `<script>` 共享全局作用域的加载顺序与改动铁律
- **静态资源缓存破坏**：mtime `?v=` 自动注入；改前端后需重启 app；`debug` 与 DevTools 缓存旁路
- **跨平台适配**：Windows / macOS 分支位置与同步要点
- **工具开发模式**：新增工具的三步（`tools.py` 函数 → `TOOLS_SCHEMA` → `dispatch`）
- **图片理解 / 生成、prompt cache 前缀稳定铁律、项目分组与 cwd、文件改动追踪** 等
- **macOS 自动编译 / 版本号管理**：GitHub Actions 流程、`bump_version.py` 发版脚本

## 快速上手

- Python 解释器：`D:/miniconda/envs/ai_api/python.exe`（base 环境没装 pywebview，会报错）
- 入口：`D:/miniconda/envs/ai_api/python.exe main.py`
- 改后端 Python 或前端 `app/static/` 后都建议**重启 app**（缓存原因，详见 CLAUDE.md）

> 维护提示：项目约定有变更时，**只更新 `CLAUDE.md`**；本文件仅作指引，不应承载会随时间变化的细节。
