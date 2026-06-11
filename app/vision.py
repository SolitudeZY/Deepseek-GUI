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
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
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
