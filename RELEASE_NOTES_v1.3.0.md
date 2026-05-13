# QuickModel v1.3.0 Release Notes

**Date**: 2026-05-13  
**Since**: v1.2.0 (2026-04-28)

---

## New Features

### apply_patch — 精准代码修改工具
新增 `apply_patch` 工具，支持以 unified diff 格式精确修改文件的指定行，比 `write_file` 覆盖整个文件更安全、更高效。Agent 现在会优先使用 diff 方式做小范围修改，减少 token 消耗和误写风险。

### RLM 并行子任务（rlm_query）
新增 `rlm_query` 工具，可一次性派发 1~16 个独立提示词到低成本模型（deepseek-v4-flash）并行执行。适用于批量翻译、代码审查、多文件分析、数据提取等场景，极大提升批处理效率。

### 推理强度三档切换
推理强度从原来的开关模式升级为三档循环：**关 → 高(high)→ 深(max)**，可通过工具栏 💭 按钮切换。设置跨会话持久化，简单任务用「关」加速响应，复杂推理用「深」获得更深入的思考过程。

### 实时成本显示
侧边栏新增 token 用量和成本统计，按轮次和会话维度展示，包含缓存命中/未命中明细，帮助用户实时掌握 API 费用。

### 多搜索引擎支持
新增 **Brave Search** 和 **Firecrawl** 搜索后端，弃用即将关闭的 Bing Search API 设置。目前共支持 6 个搜索后端：
- Tavily、Brave Search、Firecrawl、Google Custom Search、SearXNG、DuckDuckGo
- 自动降级：首选引擎失败时依次尝试下一个可用引擎，DuckDuckGo（免费无 key）作为最终兜底

### 搜索结果自动抓取
`web_search` 完成后自动读取前 N 个结果的完整网页内容（可配置数量），减少 Agent 后续额外搜索，提升信息获取效率。

### 软件图标
应用程序现在自带精美图标（icon.ico），打包后的 exe 和任务栏显示更专业。

### Enter / Shift+Enter 快捷操作
- **Enter**：发送消息 + 允许当前命令
- **Shift+Enter**：始终允许当前命令并加入白名单
  大幅提升了命令确认交互效率。

## Improvements

### 一键导入 Skills
支持从本地文件夹一键导入 Claude 风格的技能（自动检测 `SKILL.md` 及附属文件），递归扫描最多 3 层目录，简化技能迁移流程。

### API 调用缓存优化
优化了 API 调用逻辑，充分利用 DeepSeek 前缀缓存机制，提高缓存命中率，降低 API 调用成本。

### Web Search API Key 提示优化
当搜索 API Key 缺失时，Agent 会主动提示用户如何获取对应服务的 API Key，降低配置门槛。

### 对话侧栏排序优化
优化了对话历史栏的排序逻辑，新创建的对话置顶更加稳定。

### 删除冗余文件
移除了项目中的 `PRD.md` 和 `CLAUDE.md` 等不再使用的文档，保持仓库整洁。

### README 全面更新
中英文 README 同步更新，恢复徽章标签和语言跳转链接，整合所有新功能文档，更清晰易读。

## Bug Fixes

- 修复了对话历史记录中错误信息不保存的问题
- 修复了某些场景下的 API 调用错误
- 修复了新建对话后对话历史列表跳动错位的问题
- 修复了 Web Search API 首次调用时的错误
- 增强技能系统的稳定性和异常处理

---

## 升级说明

```bash
git pull
pip install -r requirements.txt
```

如有配置旧版 Bing Search API，建议在设置中切换到 Brave Search 或 Firecrawl。

## 兼容性

所有 v1.2.0 的对话记录、技能、记忆和配置文件完全向前兼容，无需手动迁移。
