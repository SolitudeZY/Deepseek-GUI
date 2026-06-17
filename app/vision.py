import base64
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def is_image(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def _encode_image(path: str) -> tuple[str, str]:
    """返回 (base64_data, mime_type)"""
    ext = Path(path).suffix.lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}.get(ext, "image/png")
    data = base64.b64encode(Path(path).read_bytes()).decode("utf-8")
    return data, mime


def describe_image(
    path: str,
    prompt: str = "请详细描述这张图片的内容。",
    api_key: str = "",
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: str = "qwen-vl-plus",
) -> str:
    # 清洗 key：去掉首尾空白、误粘贴的 "Bearer " 前缀和换行
    api_key = (api_key or "").strip()
    if api_key.lower().startswith("bearer "):
        api_key = api_key[7:].strip()
    base_url = (base_url or "").strip().rstrip("/")
    model = (model or "").strip()

    if not api_key:
        return f"[图片：{Path(path).name}]（未配置 Vision API Key，无法解析图片内容）"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        b64, mime = _encode_image(path)
        # 反幻觉系统约束：视觉模型每次调用都是无状态的，且容易"脑补"图中没有的内容。
        # 强制它只报告实际可见信息、区分观察与推测、不确定就明说，降低错误结论风险。
        system_prompt = (
            "你是严谨的图像分析助手。请遵守：\n"
            "1. 只描述图片中确实可见的内容，绝不编造、补全或猜测图中没有的细节。\n"
            "2. 区分『观察到的事实』与『据此的推测』——推测必须明确标注（如『可能』『看起来像』）。\n"
            "3. 文字、数字、代码、图表数值必须逐字符照实读取；看不清或被遮挡就说『此处不清晰/无法辨认』，不要猜测填充。\n"
            "4. 若提问超出图片所能提供的信息，直接说明『图中无法确定这一点』，而不是强行给结论。\n"
            "5. 宁可少答、保守答，也不要给出不确定的断言。"
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
        )
        return resp.choices[0].message.content or "（无返回内容）"
    except Exception as e:
        # 尽量暴露原始 HTTP 状态码与响应体，方便定位 401/404 等问题
        status = getattr(e, "status_code", None)
        body = ""
        resp_obj = getattr(e, "response", None)
        if resp_obj is not None:
            try:
                body = resp_obj.text
            except Exception:
                body = str(getattr(e, "body", ""))
        detail = f"HTTP {status}: " if status else ""
        detail += (body or str(e)).strip()
        hint = ""
        if status == 401:
            hint = ("（认证失败：请确认 vision_api_key 与 vision_base_url 配套——"
                    "如 base_url 为 dashscope compatible-mode 时需填阿里云百炼的 key；"
                    f"并检查 key 无多余空格、模型名 '{model}' 正确）")
        return f"[图片解析失败：{detail}]{hint}"


def generate_image(
    prompt: str,
    api_key: str = "",
    base_url: str = "",
    model: str = "gpt-image-2",
    size: str = "1024x1024",
    save_dir: str = "",
    fmt: str = "openai",
) -> dict:
    """生成图片并保存到本地，默认 OpenAI 兼容格式，可选 DashScope 原生格式。

    fmt='openai'（默认）：OpenAI 兼容，base_url 填到 .../v1，自动补 /images/generations。
    fmt='dashscope'：DashScope 原生，base_url 填完整端点，使用 input.messages 格式。
    返回 dict：成功 {ok, path, filename, size}；失败 {ok: False, error}。
    """
    import uuid
    import requests
    from datetime import datetime

    # 清洗输入
    api_key = (api_key or "").strip()
    if api_key.lower().startswith("bearer "):
        api_key = api_key[7:].strip()
    base_url = (base_url or "").strip().rstrip("/")
    model = (model or "gpt-image-2").strip()
    prompt = (prompt or "").strip()
    fmt = (fmt or "openai").strip().lower()

    if not api_key:
        return {"ok": False, "error": "未配置图片生成 API Key（设置 → 图片工具 → 图片生成）"}
    if not base_url:
        return {"ok": False, "error": "未配置图片生成 Base URL"}
    if not prompt:
        return {"ok": False, "error": "prompt 为空"}

    is_dashscope = (fmt == "dashscope")

    # 组装端点
    if is_dashscope:
        url = base_url
    else:
        url = base_url if base_url.endswith("/images/generations") else base_url + "/images/generations"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # 构建请求体
    if is_dashscope:
        dashscope_size = size.replace("x", "*")
        payload = {
            "model": model,
            "input": {
                "messages": [
                    {"role": "user", "content": [{"text": prompt}]}
                ]
            },
            "parameters": {
                "size": dashscope_size,
            },
        }
    else:
        payload = {
            "model": model, "prompt": prompt, "n": 1, "size": size,
            "response_format": "b64_json",
        }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=180)
        resp.raise_for_status()
        data = resp.json()

        image_bytes = None

        if is_dashscope:
            choices = (data.get("output") or {}).get("choices") or []
            if not choices:
                return {"ok": False, "error": f"返回中无 choices：{str(data)[:300]}"}
            content = (choices[0].get("message") or {}).get("content") or []
            if not content:
                return {"ok": False, "error": f"返回中无 content：{str(choices[0])[:300]}"}
            image_url = content[0].get("image") or ""
            if not image_url:
                return {"ok": False, "error": f"content 中无 image：{str(content[0])[:300]}"}
            img_resp = requests.get(image_url, timeout=120)
            img_resp.raise_for_status()
            image_bytes = img_resp.content
        else:
            items = data.get("data") or []
            if not items:
                return {"ok": False, "error": f"返回中无 data 字段：{str(data)[:300]}"}
            item = items[0]
            if item.get("b64_json"):
                image_bytes = base64.b64decode(item["b64_json"])
            elif item.get("url"):
                img_resp = requests.get(item["url"], timeout=120)
                img_resp.raise_for_status()
                image_bytes = img_resp.content
            else:
                return {"ok": False, "error": f"未知返回格式：{str(item)[:300]}"}

        if not image_bytes:
            return {"ok": False, "error": "无法获取图片数据"}

        out_dir = Path(save_dir).expanduser() if save_dir else Path.cwd()
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gen_{ts}_{uuid.uuid4().hex[:6]}.png"
        dest = out_dir / filename
        dest.write_bytes(image_bytes)
        return {"ok": True, "path": str(dest), "filename": filename,
                "size": len(image_bytes)}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "请求超时（180 秒），模型生成较慢或网络问题"}
    except requests.exceptions.HTTPError as e:
        body = ""
        try:
            body = resp.text[:500]
        except Exception:
            pass
        status = getattr(getattr(e, "response", None), "status_code", None)
        hint = ""
        if status == 401:
            hint = "（认证失败：检查 imagegen_api_key 与 base_url 是否配套、key 无多余空格）"
        return {"ok": False, "error": f"HTTP {status}: {body or str(e)}{hint}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
