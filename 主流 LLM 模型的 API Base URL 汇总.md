# 主流 LLM 模型的 API Base URL 汇总

## 国际厂商

### 1. OpenAI

* **官网**：[platform.openai.com](https://platform.openai.com/)
* **Base URL** : `https://api.openai.com/v1`
* **Chat Completions** : `/chat/completions`（完整的: `https://api.openai.com/v1/chat/completions`）
* **模型** : GPT-4o, GPT-4o-mini, o3, o4-mini, GPT-4.1 等
* **SDK 兼容** : `from openai import OpenAI`，默认 base_url 即为此地址

### 2. Anthropic (Claude)

* **官网**：[console.anthropic.com](https://console.anthropic.com/)
* **Base URL** : `https://api.anthropic.com`
* **Messages API** : `/v1/messages`（完整的: `https://api.anthropic.com/v1/messages`）
* **模型** : Claude Opus 4.5, Claude Sonnet 4, Claude Haiku 3.5 等
* **认证头** : `x-api-key` + `anthropic-version: 2023-06-01`

### 3. Google Gemini

* **官网**：[ai.google.dev](https://ai.google.dev/)
* **Base URL** : `https://generativelanguage.googleapis.com`
* **generateContent** : `/v1beta/models/{model}:generateContent`
* 如: `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent`
* **streamGenerateContent** : `/v1beta/models/{model}:streamGenerateContent`
* **模型** : Gemini 2.5 Pro, Gemini 2.5 Flash, Gemini 2.0 Flash-Lite 等
* **认证** : `x-goog-api-key` 头或 OAuth

### 4. xAI (Grok)

* **官网**：[console.x.ai](https://console.x.ai/)
* **Base URL** : `https://api.x.ai/v1`
* **兼容 OpenAI SDK** ，直接替换 base_url 即可
* **模型** : grok-4, grok-3 等

### 5. Mistral

* **官网**：[console.mistral.ai](https://console.mistral.ai/)
* **Base URL** : `https://api.mistral.ai/v1`
* **兼容 OpenAI SDK**
* **模型** : Mistral Large, Mistral Small, Codestral, Pixtral 等

### 6. Cohere

* **官网**：[dashboard.cohere.com](https://dashboard.cohere.com/)
* **Base URL** : `https://api.cohere.com/v1`
* **Chat** : `https://api.cohere.com/v1/chat`
* **模型** : Command R+, Command R 等

### 7. DeepSeek

* **官网**：[platform.deepseek.com](https://platform.deepseek.com/)
* **OpenAI 兼容 Base URL** : `https://api.deepseek.com`
* **Anthropic 兼容 Base URL** : `https://api.deepseek.com/anthropic`
* **模型** : deepseek-v4-pro, deepseek-v4-flash（chat 和 reasoner 即将废弃）
* 同时兼容 OpenAI SDK 和 Anthropic SDK 格式

### 8. Meta Llama（通过第三方）

Llama 本身没有官方 API，通常通过以下平台调用：

* **Groq**：[console.groq.com](https://console.groq.com/) — `https://api.groq.com/openai/v1`
* **Together AI**：[api.together.xyz](https://api.together.xyz/) — `https://api.together.xyz/v1`
* **Replicate**：[replicate.com](https://replicate.com/) — `https://api.replicate.com/v1`
* **HuggingFace Inference**：[huggingface.co](https://huggingface.co/) — `https://api-inference.huggingface.co/models/meta-llama/...`

---

## 国内厂商

### 9. Kimi（月之暗面）

* **官网**：[platform.moonshot.cn](https://platform.moonshot.cn/)
* **Base URL** : `https://api.moonshot.cn/v1`
* **兼容 OpenAI SDK**
* **模型** : moonshot-v1-8k/32k/128k, kimi-latest 等

### 10. 通义千问 Qwen（阿里云）

* **官网**：[bailian.console.aliyun.com](https://bailian.console.aliyun.com/)
* **Base URL** : `https://dashscope.aliyuncs.com/compatible-mode/v1`
* **兼容 OpenAI SDK**
* **模型** : qwen3-max, qwen3-plus, qwen3-turbo 等

### 11. 智谱 GLM

* **官网**：[open.bigmodel.cn](https://open.bigmodel.cn/)
* **Base URL** : `https://open.bigmodel.cn/api/paas/v4`
* **兼容 OpenAI SDK**
* **模型** : GLM-4-Plus, GLM-4-Air, GLM-4-Flash 等

### 12. MiniMax（海螺AI）

* **官网**：[platform.minimaxi.com](https://platform.minimaxi.com/)
* **Base URL** : `https://api.minimax.chat/v1`
* Chat completions 路径为 `/text/chatcompletion_v2`（非标准，需注意）
* **模型** : abab6.5s, abab7 等

### 13. 百度文心一言

* **官网**：[console.bce.baidu.com](https://console.bce.baidu.com/qianfan/overview)
* **Base URL** : `https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/`
* 不同模型后缀不同，如 `ernie-4.0-turbo-8k`、`completions_pro` 等
* 格式与 OpenAI 不完全兼容

### 14. 字节豆包（火山引擎）

* **官网**：[console.volcengine.com/ark](https://console.volcengine.com/ark)
* **Base URL** : `https://ark.cn-beijing.volces.com/api/v3`
* **兼容 OpenAI SDK**
* **模型** : doubao-1.5-pro, doubao-1.5-lite 等

### 15. 讯飞星火

* **官网**：[xinghuo.xfyun.cn](https://xinghuo.xfyun.cn/)
* **Base URL** : 通过 WebSocket 协议，URL 格式为 `wss://spark-api.xf-yun.com/{version}/chat`
* 新版也提供 HTTP 接口，与 OpenAI 不兼容
