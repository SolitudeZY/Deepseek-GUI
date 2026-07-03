"""
wxwork.py — 企业微信聊天记录管理

存储位置：%APPDATA%/AIDesktopAssistant/wxwork/records.json
数据模型：单文件存储所有聊天记录，按时间排序。
"""

import json
from datetime import datetime, time as _time
from pathlib import Path
from app.config import get_app_data_dir


def _wxwork_dir() -> Path:
    d = get_app_data_dir() / "wxwork"
    d.mkdir(exist_ok=True)
    return d


def _records_path() -> Path:
    return _wxwork_dir() / "records.json"


def _load_records() -> list[dict]:
    """加载所有聊天记录，返回按时间升序的列表。"""
    p = _records_path()
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("records", [])
    except Exception:
        return []


def _save_records(records: list[dict]) -> None:
    """保存聊天记录，自动按时间排序。"""
    records.sort(key=lambda r: r.get("time", ""))
    p = _records_path()
    p.parent.mkdir(exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"records": records, "updated_at": datetime.now().isoformat()},
                  f, ensure_ascii=False, indent=2)


# ── 数据校验 ──────────────────────────────────────────────────────────

_RECORD_FIELDS = {
    "time": (str, True),       # ISO 格式时间，如 "2026-07-03T14:30:00"
    "talker": (str, True),     # 会话名称（群名或联系人名）
    "talker_type": (str, False),  # "group" 或 "contact"
    "sender": (str, False),    # 发言人（群聊时有意义）
    "content": (str, True),    # 消息内容
    "msg_type": (str, False),  # "text" | "image" | "file" | "system" 等
}


def _validate_record(rec: dict, index: int = 0) -> str | None:
    """校验单条记录，合法返回 None，否则返回错误信息。"""
    if not isinstance(rec, dict):
        return f"第 {index + 1} 条：不是对象"
    for field, (typ, required) in _RECORD_FIELDS.items():
        if field not in rec:
            if required:
                return f"第 {index + 1} 条：缺少必填字段 '{field}'"
            continue
        if not isinstance(rec[field], typ):
            return f"第 {index + 1} 条：字段 '{field}' 应为 {typ.__name__}，实际为 {type(rec[field]).__name__}"
    # 校验时间格式
    t = rec.get("time", "")
    if t:
        try:
            datetime.fromisoformat(t)
        except ValueError:
            return f"第 {index + 1} 条：时间格式无效 '{t}'，应为 ISO 格式如 '2026-07-03T14:30:00'"
    return None


# ── 公开 API ──────────────────────────────────────────────────────────

def import_records(file_path: str, replace: bool = False) -> str:
    """从 JSON 文件导入聊天记录。

    file_path: 导入的 JSON 文件路径。文件格式：
      {"records": [{"time": "...", "talker": "...", "content": "...", ...}, ...]}
      或直接是记录数组：[{...}, {...}]

    replace: 是否替换全部已有记录（默认 False = 追加，去重合并）。
    """
    p = Path(file_path).expanduser()
    if not p.exists():
        return f"错误：文件不存在 — {file_path}"

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return f"错误：JSON 解析失败 — {e}"
    except Exception as e:
        return f"错误：读取文件失败 — {e}"

    # 支持两种格式：{"records": [...]} 或直接 [...]
    if isinstance(data, list):
        new_records = data
    elif isinstance(data, dict) and "records" in data:
        new_records = data["records"]
    else:
        return "错误：JSON 格式不正确。需要 {\"records\": [...]} 或直接是记录数组。"

    if not isinstance(new_records, list):
        return "错误：records 应为数组"

    # 校验每条记录
    errors = []
    for i, rec in enumerate(new_records):
        err = _validate_record(rec, i)
        if err:
            errors.append(err)
    if errors:
        return "数据校验失败：\n" + "\n".join(errors[:10]) + (
            f"\n\n[共 {len(errors)} 条错误，仅显示前 10 条]" if len(errors) > 10 else "")

    if replace:
        _save_records(new_records)
        return f"✅ 已导入 {len(new_records)} 条记录（替换模式，已清空旧数据）"

    # 追加模式：按 (time, talker, sender, content) 去重
    existing = _load_records()
    existing_keys = {
        (r.get("time", ""), r.get("talker", ""), r.get("sender", ""), r.get("content", ""))
        for r in existing
    }
    added = 0
    for rec in new_records:
        key = (rec.get("time", ""), rec.get("talker", ""), rec.get("sender", ""), rec.get("content", ""))
        if key not in existing_keys:
            existing.append(rec)
            existing_keys.add(key)
            added += 1

    _save_records(existing)
    skipped = len(new_records) - added
    msg = f"✅ 已导入 {added} 条新记录"
    if skipped > 0:
        msg += f"，跳过 {skipped} 条重复（已存在）"
    msg += f"。当前共 {len(existing)} 条记录。"
    return msg


def query_records(start_date: str = "", end_date: str = "",
                  talker: str = "", keyword: str = "",
                  sender: str = "", msg_type: str = "",
                  max_results: int = 200) -> str:
    """按条件查询聊天记录。返回格式化文本。

    start_date/end_date: YYYY-MM-DD（含边界）
    talker: 会话名称（模糊匹配）
    keyword: 内容关键词（模糊匹配）
    sender: 发言人（模糊匹配）
    msg_type: 消息类型（精确匹配）
    """
    records = _load_records()
    if not records:
        return "暂无企业微信聊天记录。请先用 wxwork_import 导入数据。"

    lo = _parse_date(start_date, end=False)
    hi = _parse_date(end_date, end=True)

    # 过滤
    def _match(r: dict) -> bool:
        if lo or hi:
            t = r.get("time", "")
            if not t:
                return False
            try:
                when = datetime.fromisoformat(t)
            except ValueError:
                return False
            if lo and when < lo:
                return False
            if hi and when > hi:
                return False
        if talker:
            kw = talker.lower()
            if kw not in r.get("talker", "").lower():
                return False
        if keyword:
            kw = keyword.lower()
            if kw not in r.get("content", "").lower():
                return False
        if sender:
            kw = sender.lower()
            if kw not in r.get("sender", "").lower():
                return False
        if msg_type:
            if r.get("msg_type", "text") != msg_type:
                return False
        return True

    matched = [r for r in records if _match(r)]

    if not matched:
        parts = ["未找到匹配的记录。当前筛选条件："]
        if start_date or end_date:
            parts.append(f"  时间：{start_date or '不限'} ~ {end_date or '不限'}")
        if talker:
            parts.append(f"  会话：{talker}")
        if keyword:
            parts.append(f"  关键词：{keyword}")
        if sender:
            parts.append(f"  发言人：{sender}")
        parts.append(f"\n（共 {len(records)} 条记录，0 条匹配）")
        return "\n".join(parts)

    # 格式化输出
    lines = []
    lines.append(f"共 {len(matched)} 条匹配记录（总数 {len(records)} 条）：\n")
    shown = matched[:max_results]
    for r in shown:
        t = r.get("time", "")[:19].replace("T", " ")
        talker_name = r.get("talker", "未知")
        talker_type = r.get("talker_type", "")
        type_tag = "👥" if talker_type == "group" else "👤" if talker_type == "contact" else ""
        sender_name = r.get("sender", "")
        if sender_name:
            header = f"[{t}] {type_tag} {talker_name} | {sender_name}"
        else:
            header = f"[{t}] {type_tag} {talker_name}"
        content = r.get("content", "")
        msg_t = r.get("msg_type", "text")
        if msg_t and msg_t != "text":
            header += f" [{msg_t}]"
        lines.append(header)
        lines.append(f"  {content}")
        lines.append("")

    if len(matched) > max_results:
        lines.append(f"[共 {len(matched)} 条，仅显示前 {max_results} 条。请缩小筛选范围获取更精确结果。]")

    return "\n".join(lines)


def list_talkers() -> str:
    """列出所有会话（群聊/联系人），含消息数和时间范围。"""
    records = _load_records()
    if not records:
        return "暂无企业微信聊天记录。"

    # 按 talker 分组统计
    groups: dict[str, dict] = {}
    for r in records:
        name = r.get("talker", "未知")
        ttype = r.get("talker_type", "")
        if name not in groups:
            groups[name] = {
                "type": ttype,
                "count": 0,
                "first": r.get("time", ""),
                "last": r.get("time", ""),
                "senders": set(),
            }
        g = groups[name]
        g["count"] += 1
        t = r.get("time", "")
        if t and (not g["first"] or t < g["first"]):
            g["first"] = t
        if t and (not g["last"] or t > g["last"]):
            g["last"] = t
        s = r.get("sender", "")
        if s:
            g["senders"].add(s)

    # 排序：群聊在前，按消息数降序
    sorted_groups = sorted(groups.items(), key=lambda x: (-x[1]["count"], x[0]))

    lines = [f"共 {len(sorted_groups)} 个会话，{len(records)} 条记录：\n"]
    for name, info in sorted_groups:
        type_tag = "👥" if info["type"] == "group" else "👤" if info["type"] == "contact" else "❓"
        first = info["first"][:10] if info["first"] else "?"
        last = info["last"][:10] if info["last"] else "?"
        senders = f"，{len(info['senders'])} 人发言" if info["senders"] else ""
        lines.append(f"  {type_tag} {name} — {info['count']} 条消息{senders}（{first} ~ {last}）")

    lines.append(f"\n💡 用 wxwork_query 查询具体会话内容，如 wxwork_query(talker=\"{sorted_groups[0][0] if sorted_groups else '...'}\")")
    return "\n".join(lines)


def _parse_date(d: str, end: bool) -> datetime | None:
    d = (d or "").strip()
    if not d:
        return None
    try:
        day = datetime.strptime(d[:10], "%Y-%m-%d").date()
        return datetime.combine(day, _time.max if end else _time.min)
    except ValueError:
        return None


def get_record_count() -> int:
    return len(_load_records())