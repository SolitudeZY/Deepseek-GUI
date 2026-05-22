import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import get_conversations_dir


def _conv_path(conv_id: str) -> Path:
    return get_conversations_dir() / f"{conv_id}.json"


def new_conversation(model_config_name: str = "") -> dict:
    now = datetime.now()
    conv_id = f"conv_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    return {
        "id": conv_id,
        "title": "新对话",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "model_config": model_config_name,
        "sort_order": -1,
        "messages": [],
    }


def save_conversation(conv: dict) -> None:
    conv["updated_at"] = datetime.now().isoformat()
    with open(_conv_path(conv["id"]), "w", encoding="utf-8") as f:
        json.dump(conv, f, ensure_ascii=False, indent=2)


def load_conversation(conv_id: str) -> Optional[dict]:
    p = _conv_path(conv_id)
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_conversation(conv_id: str) -> None:
    p = _conv_path(conv_id)
    if p.exists():
        p.unlink()


def rename_conversation(conv_id: str, new_title: str) -> None:
    conv = load_conversation(conv_id)
    if conv:
        conv["title"] = new_title.strip() or "新对话"
        save_conversation(conv)


def list_conversations() -> list[dict]:
    """返回所有对话摘要。
    排序规则：
    - sort_order >= 0 的对话（手动拖拽固定）按 sort_order 升序排在最前
    - sort_order = -1 的对话按 updated_at 降序（最新在上），插在最前面
    这样新对话和最近活跃的对话始终出现在列表顶部。
    """
    convs = []
    for p in get_conversations_dir().glob("conv_*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            convs.append({
                "id": data["id"],
                "title": data.get("title", "新对话"),
                "updated_at": data.get("updated_at", ""),
                "sort_order": data.get("sort_order", -1),
                "model_config": data.get("model_config", ""),
            })
        except Exception:
            continue

    unpinned = [c for c in convs if c["sort_order"] < 0]
    pinned = [c for c in convs if c["sort_order"] >= 0]
    unpinned.sort(key=lambda c: c["updated_at"], reverse=True)
    pinned.sort(key=lambda c: c["sort_order"])
    return unpinned + pinned


def update_sort_orders(ordered_ids: list[str]) -> None:
    """拖拽后批量写入 sort_order（0-based），使手动顺序持久化。"""
    for i, conv_id in enumerate(ordered_ids):
        conv = load_conversation(conv_id)
        if conv:
            conv["sort_order"] = i
            save_conversation(conv)


def auto_title_from_message(conv: dict, first_user_message: str) -> None:
    """用首条用户消息的前 30 字作为临时标题（LLM 生成前的占位）。"""
    if conv.get("title") == "新对话":
        title = first_user_message.strip().replace("\n", " ")[:30]
        conv["title"] = title or "新对话"


def export_conversation_md(conv: dict) -> str:
    """将对话导出为 Markdown 字符串（仅用户和助手内容，不含工具调用）。"""
    lines = [f"# {conv.get('title', '对话')}\n"]
    lines.append(f"> 创建时间：{conv.get('created_at', '')}\n")
    lines.append(f"> 模型配置：{conv.get('model_config', '')}\n\n---\n")
    for msg in conv.get("messages", []):
        role = msg.get("role", "")
        content = msg.get("content") or ""
        if role == "user":
            lines.append(f"**User:**\n\n{content}\n\n")
        elif role == "assistant" and content:
            lines.append(f"**Assistant:**\n\n{content}\n\n")
    return "".join(lines)


def import_conversation_from_file(file_path: str) -> Optional[dict]:
    """从文件导入对话。支持 .json（原生格式）和 .md（导出格式）。"""
    p = Path(file_path)
    if not p.exists():
        return None

    if p.suffix.lower() == '.json':
        return _import_from_json(p)
    elif p.suffix.lower() == '.md':
        return _import_from_md(p)
    return None


def _import_from_json(p: Path) -> Optional[dict]:
    """导入原生 JSON 格式的对话文件。"""
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    # 如果是完整的对话 JSON（有 id 和 messages）
    if "messages" in data:
        conv = new_conversation(data.get("model_config", ""))
        conv["title"] = data.get("title", p.stem)
        conv["messages"] = data["messages"]
        save_conversation(conv)
        return conv

    return None


def _import_from_md(p: Path) -> Optional[dict]:
    """解析导出的 Markdown 格式，还原为对话。"""
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return None

    messages = []
    title = p.stem

    # 提取标题
    lines = text.split('\n')
    for line in lines:
        if line.startswith('# '):
            title = line[2:].strip()
            break

    # 按 **User:** 和 **Assistant:** 分割
    parts = re.split(r'\n\*\*(User|Assistant):\*\*\s*\n', text)
    # parts: [header, 'User', content, 'Assistant', content, ...]
    i = 1
    while i < len(parts) - 1:
        role = parts[i].lower()
        content = parts[i + 1].strip()
        if role in ('user', 'assistant') and content:
            messages.append({"role": role, "content": content})
        i += 2

    if not messages:
        return None

    conv = new_conversation("")
    conv["title"] = title
    conv["messages"] = messages
    save_conversation(conv)
    return conv
