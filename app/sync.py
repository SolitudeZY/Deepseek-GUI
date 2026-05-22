"""云同步模块 — 通过本地同步文件夹（坚果云/OneDrive等）实现对话同步。

工作原理：
- 对话保存时自动复制 JSON 到同步文件夹
- 启动时扫描同步文件夹，检测本地没有的对话文件
- 用户可选择性导入新对话
"""
import json
import shutil
from pathlib import Path
from typing import Optional

from app.config import get_conversations_dir, load_config, save_config


SYNC_SUBDIR = "QuickModel_Sync"


def get_sync_dir() -> Optional[Path]:
    """获取同步目录路径。返回 None 表示未配置。"""
    config = load_config()
    folder = config.get("sync_folder", "")
    if not folder:
        return None
    sync_dir = Path(folder) / SYNC_SUBDIR
    sync_dir.mkdir(parents=True, exist_ok=True)
    return sync_dir


def upload_conversation(conv_id: str) -> bool:
    """将指定对话上传（复制）到同步文件夹。"""
    sync_dir = get_sync_dir()
    if not sync_dir:
        return False
    src = get_conversations_dir() / f"{conv_id}.json"
    if not src.exists():
        return False
    dest = sync_dir / f"{conv_id}.json"
    shutil.copy2(src, dest)
    return True


def upload_all_conversations() -> int:
    """将所有本地对话上传到同步文件夹。返回上传数量。"""
    sync_dir = get_sync_dir()
    if not sync_dir:
        return 0
    count = 0
    for src in get_conversations_dir().glob("conv_*.json"):
        dest = sync_dir / src.name
        # 只在源文件更新时覆盖
        if not dest.exists() or src.stat().st_mtime > dest.stat().st_mtime:
            shutil.copy2(src, dest)
            count += 1
    return count


def detect_new_conversations() -> list[dict]:
    """检测同步文件夹中本地没有的对话，返回摘要列表。"""
    sync_dir = get_sync_dir()
    if not sync_dir:
        return []
    local_dir = get_conversations_dir()
    new_convs = []
    for f in sync_dir.glob("conv_*.json"):
        local_file = local_dir / f.name
        # 本地不存在，或同步文件夹的版本更新
        if not local_file.exists() or f.stat().st_mtime > local_file.stat().st_mtime:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                new_convs.append({
                    "id": data.get("id", f.stem),
                    "title": data.get("title", "未命名"),
                    "updated_at": data.get("updated_at", ""),
                    "filename": f.name,
                    "is_new": not local_file.exists(),
                })
            except Exception:
                continue
    # 按更新时间降序
    new_convs.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return new_convs


def import_from_sync(filenames: list[str]) -> int:
    """从同步文件夹导入选中的对话到本地。返回导入数量。"""
    sync_dir = get_sync_dir()
    if not sync_dir:
        return 0
    local_dir = get_conversations_dir()
    count = 0
    for name in filenames:
        src = sync_dir / name
        if src.exists():
            shutil.copy2(src, local_dir / name)
            count += 1
    return count


def delete_from_sync(conv_id: str) -> bool:
    """从同步文件夹删除指定对话。"""
    sync_dir = get_sync_dir()
    if not sync_dir:
        return False
    dest = sync_dir / f"{conv_id}.json"
    if dest.exists():
        dest.unlink()
        return True
    return False
