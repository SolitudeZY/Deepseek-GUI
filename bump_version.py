#!/usr/bin/env python3
"""发版助手：一条命令同步版本号到所有位置并打 tag 推送。

用法:
    python bump_version.py 1.5.3              # 改版本号 + commit + 打 tag v1.5.3 + push
    python bump_version.py 1.5.3 --no-push    # 只改本地，不 push（自己检查后手动 push）
    python bump_version.py --show             # 只显示当前版本号

版本号唯一真源是 app/config.py 的 APP_VERSION；本脚本改它、打同名 tag，
触发 GitHub Actions 编译 Mac/Win 并发 Release。「检查更新」读 APP_VERSION 作本地版本。
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "app" / "config.py"
VER_RE = re.compile(r'^(APP_VERSION\s*=\s*")([^"]+)(")', re.MULTILINE)
SEMVER_RE = re.compile(r'^\d+\.\d+\.\d+$')


def read_version() -> str:
    m = VER_RE.search(CONFIG.read_text(encoding="utf-8"))
    if not m:
        sys.exit(f"❌ 在 {CONFIG} 找不到 APP_VERSION")
    return m.group(2)


def write_version(new: str) -> None:
    text = CONFIG.read_text(encoding="utf-8")
    text = VER_RE.sub(rf'\g<1>{new}\g<3>', text, count=1)
    CONFIG.write_text(text, encoding="utf-8")


def run(*args: str) -> None:
    print("  $", " ".join(args))
    subprocess.run(args, check=True, cwd=ROOT)


def main() -> None:
    ap = argparse.ArgumentParser(description="同步版本号并打 tag 发版")
    ap.add_argument("version", nargs="?", help="新版本号，如 1.5.3")
    ap.add_argument("--no-push", action="store_true", help="只改本地与打 tag，不 push")
    ap.add_argument("--show", action="store_true", help="只显示当前版本号")
    args = ap.parse_args()

    if args.show or not args.version:
        print(f"当前版本: {read_version()}")
        if not args.show:
            ap.print_usage()
        return

    new = args.version.lstrip("v")
    if not SEMVER_RE.match(new):
        sys.exit(f"❌ 版本号格式应为 X.Y.Z（收到 {new!r}）")

    old = read_version()
    if new == old:
        sys.exit(f"❌ 新版本 {new} 与当前版本相同")

    tag = f"v{new}"
    # 防止 tag 重名
    existing = subprocess.run(["git", "tag", "-l", tag], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
    if existing:
        sys.exit(f"❌ tag {tag} 已存在，请换一个版本号")

    print(f"版本号 {old} → {new}，将打 tag {tag}")
    write_version(new)
    run("git", "add", str(CONFIG.relative_to(ROOT)))
    run("git", "commit", "-m", f"chore: bump version to {new}")
    run("git", "tag", "-a", tag, "-m", f"Release {tag}")
    if args.no_push:
        print(f"✅ 已改版本号并打 tag {tag}（未 push）。确认后执行：")
        print(f"   git push && git push origin {tag}")
    else:
        run("git", "push")
        run("git", "push", "origin", tag)
        print(f"✅ 已发版 {tag} 并推送，GitHub Actions 将自动编译并发 Release。")


if __name__ == "__main__":
    main()
