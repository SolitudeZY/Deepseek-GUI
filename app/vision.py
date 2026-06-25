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
    use_full_url: bool = False,
) -> dict:
    """生成图片并保存到本地，默认 OpenAI 兼容格式，可选 DashScope 原生格式。

    fmt='openai'（默认）：OpenAI 兼容，base_url 填到 .../v1，自动补 /images/generations。
    use_full_url=True 时，base_url 原样使用不做拼接。
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
    DASHSCOPE_PATH = "/services/aigc/multimodal-generation/generation"
    if use_full_url:
        url = base_url
    elif is_dashscope:
        if base_url.endswith(DASHSCOPE_PATH):
            url = base_url
        else:
            url = base_url + DASHSCOPE_PATH
    else:
        url = base_url if base_url.endswith("/images/generations") else base_url + "/images/generations"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # 构建请求体
    if is_dashscope:
        dashscope_size = size.replace("x", "*").replace("X", "*")
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
            # 同步返回：output.choices[0].message.content[0].image
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


def edit_image(
    image_path: str,
    prompt: str,
    api_key: str = "",
    base_url: str = "",
    model: str = "qwen-image-edit",
    save_dir: str = "",
) -> dict:
    """指令式图像编辑（阿里 Qwen-Image-Edit / dashscope multimodal-generation）。

    在已有图片基础上按文字指令编辑（如"把图中的猫换成狗"）。本地图转 base64 传入。
    复用 generate_image 的 dashscope 端点拼接、响应解析、保存逻辑。
    返回 dict：成功 {ok, path, filename, size}；失败 {ok: False, error}。
    """
    import uuid
    import requests
    from datetime import datetime

    api_key = (api_key or "").strip()
    if api_key.lower().startswith("bearer "):
        api_key = api_key[7:].strip()
    base_url = (base_url or "").strip().rstrip("/")
    model = (model or "qwen-image-edit").strip()
    prompt = (prompt or "").strip()
    image_path = (image_path or "").strip()

    if not api_key:
        return {"ok": False, "error": "未配置图片生成 API Key（设置 → 图片工具 → 图片生成）"}
    if not base_url:
        return {"ok": False, "error": "未配置图片生成 Base URL"}
    if not prompt:
        return {"ok": False, "error": "编辑指令 prompt 为空"}
    if not image_path or not Path(image_path).exists():
        return {"ok": False, "error": f"原图不存在：{image_path}"}
    if not is_image(image_path):
        return {"ok": False, "error": f"不是受支持的图片格式：{image_path}"}

    # 端点：dashscope multimodal-generation（同 generate_image 的 dashscope 分支）
    DASHSCOPE_PATH = "/services/aigc/multimodal-generation/generation"
    url = base_url if base_url.endswith(DASHSCOPE_PATH) else base_url + DASHSCOPE_PATH

    b64, mime = _encode_image(image_path)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "input": {
            "messages": [
                {"role": "user", "content": [
                    {"image": f"data:{mime};base64,{b64}"},
                    {"text": prompt},
                ]}
            ]
        },
    }
    return _dashscope_image_request(url, headers, payload, save_dir, prefix="edit")


def _dashscope_image_request(url, headers, payload, save_dir, prefix="gen") -> dict:
    """发 dashscope 图像请求，解析 output.choices[0].message.content[0].image，
    下载图片字节并保存到本地。供 edit_image 复用。"""
    import uuid
    import requests
    from datetime import datetime

    resp = None
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=180)
        resp.raise_for_status()
        data = resp.json()
        choices = (data.get("output") or {}).get("choices") or []
        if not choices:
            return {"ok": False, "error": f"返回中无 choices：{str(data)[:300]}"}
        content = (choices[0].get("message") or {}).get("content") or []
        if not content:
            return {"ok": False, "error": f"返回中无 content：{str(choices[0])[:300]}"}
        image_url = ""
        for c in content:
            if isinstance(c, dict) and c.get("image"):
                image_url = c["image"]
                break
        if not image_url:
            return {"ok": False, "error": f"content 中无 image：{str(content[0])[:300]}"}
        img_resp = requests.get(image_url, timeout=120)
        img_resp.raise_for_status()
        image_bytes = img_resp.content
        if not image_bytes:
            return {"ok": False, "error": "无法获取图片数据"}

        out_dir = Path(save_dir).expanduser() if save_dir else Path.cwd()
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{ts}_{uuid.uuid4().hex[:6]}.png"
        dest = out_dir / filename
        dest.write_bytes(image_bytes)
        return {"ok": True, "path": str(dest), "filename": filename, "size": len(image_bytes)}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "请求超时（180 秒），模型生成较慢或网络问题"}
    except requests.exceptions.HTTPError as e:
        body = ""
        try:
            body = resp.text[:500] if resp is not None else ""
        except Exception:
            pass
        status = getattr(getattr(e, "response", None), "status_code", None)
        hint = "（认证失败：检查 key 与 base_url 是否配套）" if status == 401 else ""
        return {"ok": False, "error": f"HTTP {status}: {body or str(e)}{hint}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── 本地 OCR（RapidOCR / ONNX，离线）─────────────────────────────────
_RAPID_OCR = None
_RAPID_OCR_FAILED = False


def ocr_image(image_path: str) -> str:
    """用本地 RapidOCR(ONNX) 识别图片中的文字。引擎单例懒加载（首次较慢）。"""
    global _RAPID_OCR, _RAPID_OCR_FAILED
    image_path = (image_path or "").strip()
    if not image_path or not Path(image_path).exists():
        return f"错误：图片不存在 — {image_path}"
    if not is_image(image_path):
        return f"错误：不是受支持的图片格式 — {image_path}"
    if _RAPID_OCR is None and not _RAPID_OCR_FAILED:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _RAPID_OCR = RapidOCR()
        except ImportError:
            _RAPID_OCR_FAILED = True
            return ("错误：当前运行环境缺少 rapidocr-onnxruntime，无法本地 OCR。\n"
                    "请用项目 conda 环境 ai_api 的解释器启动 app，并确保已 "
                    "pip install rapidocr-onnxruntime（运行期安装需重启 app 才生效）。")
        except Exception as e:
            _RAPID_OCR_FAILED = True
            return f"错误：RapidOCR 初始化失败 — {e}"
    if _RAPID_OCR is None:
        return "错误：OCR 引擎不可用。"
    try:
        result, _ = _RAPID_OCR(image_path)
        if not result:
            return "（未识别到文字）"
        lines = [item[1] for item in result if len(item) >= 2]
        return "\n".join(lines) if lines else "（未识别到文字）"
    except Exception as e:
        return f"错误：OCR 识别失败 — {e}"
