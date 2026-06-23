#!/usr/bin/env python3
"""发版助手：一条命令同步版本号到所有位置并打 tag 推送。

用法:
    python bump_version.py 1.5.3                    # 交互式输入更新说明（粘贴 markdown，Ctrl+Z/Ctrl+D 结束）
    python bump_version.py 1.5.3 -m "修复图片崩溃"   # 单行更新说明
    python bump_version.py 1.5.3 -F notes.md         # 从文件读多行 markdown 更新说明（推荐多行用）
    python bump_version.py 1.5.3 --no-push           # 只改本地与打 tag，不 push
    python bump_version.py --show                    # 只显示当前版本号

更新说明会写进 annotated tag 的消息，GitHub Actions 编译时提取它作为 Release 正文（支持 markdown）。
版本号唯一真源是 app/config.py 的 APP_VERSION；本脚本改它、打同名 tag，触发 CI 编译 Mac/Win 并发 Release。
"""
import argparse
import re
import subprocess
import sys
import tempfile
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


def collect_notes(args, tag: str) -> str:
    """按优先级取更新说明：-m > -F > 交互式输入。返回 tag 消息全文（首行为标题）。"""
    if args.message:
        body = args.message.strip()
    elif args.file:
        p = Path(args.file)
        if not p.exists():
            sys.exit(f"❌ 说明文件不存在：{p}")
        body = p.read_text(encoding="utf-8").strip()
    else:
        print(f"请输入 {tag} 的更新说明（支持 markdown，多行；"
              f"输入完成后按 {'Ctrl+Z 回车' if sys.platform == 'win32' else 'Ctrl+D'} 结束）：")
        body = sys.stdin.read().strip()
    if not body:
        sys.exit("❌ 更新说明为空，已取消发版")
    # tag 消息 = 用户更新说明全文（不加 "Release vX.Y.Z" 标题，
    # 否则 git 会把它当 tag subject，CI 用 %(contents) 提取时易吞掉正文首行）。
    return body


def main() -> None:
    ap = argparse.ArgumentParser(description="同步版本号并打 tag 发版")
    ap.add_argument("version", nargs="?", help="新版本号，如 1.5.3")
    ap.add_argument("-m", "--message", help="单行更新说明")
    ap.add_argument("-F", "--file", help="从文件读取更新说明（多行 markdown）")
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
    tag_msg = collect_notes(args, tag)
    write_version(new)
    run("git", "add", str(CONFIG.relative_to(ROOT)))
    run("git", "commit", "-m", f"chore: bump version to {new}")
    # 用临时文件传 tag 消息，避免多行 markdown 在命令行转义出错
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write(tag_msg)
        msg_file = f.name
    try:
        # --cleanup=whitespace：保留 '#' 开头的行（否则 git 默认 strip 模式会把
        # markdown 的 '## 标题' 当注释删掉），只去首尾空白。
        run("git", "tag", "-a", "--cleanup=whitespace", tag, "-F", msg_file)
    finally:
        Path(msg_file).unlink(missing_ok=True)
    if args.no_push:
        print(f"✅ 已改版本号并打 tag {tag}（未 push）。确认后执行：")
        print(f"   git push && git push origin {tag}")
    else:
        run("git", "push")
        run("git", "push", "origin", tag)
        print(f"✅ 已发版 {tag} 并推送，GitHub Actions 将自动编译并发 Release。")


if __name__ == "__main__":
    main()
