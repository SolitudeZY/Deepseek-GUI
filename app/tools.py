import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

# ── 文件改动旁路记录（thread-local，不污染模型上下文/prompt cache）────────
# write_file / apply_patch 写盘时把 {path, old, new} 记到这里，由 webview_app 的
# _on_tool_result 在同线程同步读取，用于去重展示与生成 diff。绝不进工具返回字符串。
_file_op_local = threading.local()


def _reset_file_op_log():
    """工具入口调用：清空本线程上一次的改动记录。"""
    _file_op_local.log = {}


def _record_file_op(path: str, old_content: str, new_content: str):
    """记录一次文件改动。同一文件多次改动时：保留最早的 old、最新的 new（累计本次工具调用内）。"""
    log = getattr(_file_op_local, "log", None)
    if log is None:
        log = {}
        _file_op_local.log = log
    key = str(path)
    if key in log:
        log[key]["new"] = new_content  # 沿用最早的 old，仅更新 new
    else:
        log[key] = {"path": key, "old": old_content, "new": new_content}


def get_file_op_log() -> list:
    """返回本线程最近一次工具调用记录的文件改动列表 [{path, old, new}]。"""
    log = getattr(_file_op_local, "log", None)
    return list(log.values()) if log else []


# ── 文档解析依赖（延迟加载，加快启动）──────────────────────────
_PDF_OK = None
_DOCX_OK = None
_XLSX_OK = None


def _check_pdf():
    global _PDF_OK
    if _PDF_OK is None:
        try:
            import pdfplumber  # noqa: F401
            _PDF_OK = True
        except ImportError:
            _PDF_OK = False
    return _PDF_OK


def _check_docx():
    global _DOCX_OK
    if _DOCX_OK is None:
        try:
            from docx import Document as DocxDocument  # noqa: F401
            _DOCX_OK = True
        except ImportError:
            _DOCX_OK = False
    return _DOCX_OK


def _check_xlsx():
    global _XLSX_OK
    if _XLSX_OK is None:
        try:
            import openpyxl  # noqa: F401
            _XLSX_OK = True
        except ImportError:
            _XLSX_OK = False
    return _XLSX_OK

MAX_FILE_CHARS = 50_000


# ── 工具实现 ──────────────────────────────────────────────────────────

def _resolve(path: str, cwd: str = "") -> Path:
    """将路径解析为基于项目目录 cwd 的绝对路径。

    - 绝对路径（含 Windows 盘符、~ 展开后）：原样使用，不受 cwd 影响。
    - 相对路径 + 提供了 cwd：相对于 cwd 解析（项目目录）。
    - 相对路径 + 无 cwd：回退进程默认目录（向后兼容）。
    """
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    if cwd:
        base = Path(cwd).expanduser()
        if base.is_dir():
            return base / p
    return p


def read_file(path: str, cwd: str = "") -> str:
    p = _resolve(path, cwd)
    if not p.exists():
        return f"错误：文件不存在 — {path}"
    if not p.is_file():
        return f"错误：路径不是文件 — {path}"

    suffix = p.suffix.lower()

    try:
        if suffix == ".pdf":
            return _read_pdf(p)
        elif suffix == ".docx":
            return _read_docx(p)
        elif suffix in (".xlsx", ".xls"):
            return _read_xlsx(p)
        else:
            text = p.read_text(encoding="utf-8", errors="replace")
            return _truncate(text, path)
    except Exception as e:
        return f"读取文件失败：{e}"


def _read_pdf(p: Path) -> str:
    if not _check_pdf():
        return "错误：pdfplumber 未安装，无法读取 PDF"
    import pdfplumber
    text_parts = []
    with pdfplumber.open(p) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return _truncate("\n".join(text_parts), str(p))


def _read_docx(p: Path) -> str:
    if not _check_docx():
        return "错误：python-docx 未安装，无法读取 Word 文档"
    from docx import Document as DocxDocument
    doc = DocxDocument(str(p))
    text = "\n".join(para.text for para in doc.paragraphs)
    return _truncate(text, str(p))


def _read_xlsx(p: Path) -> str:
    if not _check_xlsx():
        return "错误：openpyxl 未安装，无法读取 Excel 文件"
    import openpyxl
    wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
    lines = []
    for sheet in wb.worksheets:
        lines.append(f"=== Sheet: {sheet.title} ===")
        for row in sheet.iter_rows(values_only=True):
            lines.append("\t".join("" if v is None else str(v) for v in row))
    return _truncate("\n".join(lines), str(p))


def _truncate(text: str, path: str) -> str:
    if len(text) > MAX_FILE_CHARS:
        return text[:MAX_FILE_CHARS] + f"\n\n[文件已截断，仅显示前 {MAX_FILE_CHARS} 字符，原始路径：{path}]"
    return text


def list_directory(path: str, cwd: str = "") -> str:
    p = _resolve(path, cwd) if path else (Path(cwd).expanduser() if cwd else Path(path).expanduser())
    if not p.exists():
        return f"错误：路径不存在 — {path}"
    if not p.is_dir():
        return f"错误：路径不是目录 — {path}"
    try:
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        lines = []
        for e in entries:
            tag = "[目录]" if e.is_dir() else "[文件]"
            size = "" if e.is_dir() else f"  {e.stat().st_size:,} bytes"
            lines.append(f"{tag} {e.name}{size}")
        return "\n".join(lines) if lines else "（空目录）"
    except PermissionError:
        return f"错误：无权限访问 — {path}"


def glob_files(pattern: str, path: str = ".", cwd: str = "") -> str:
    """Match files by glob pattern, sorted by modification time (newest first)."""
    import glob as _glob
    # path 为相对路径时以项目目录 cwd 为基准
    path = str(_resolve(path, cwd))
    # 若 pattern 本身是绝对路径，拆出锚点目录作为 base，pattern 转成相对部分
    pat = (pattern or "").replace("\\", "/")
    pp = Path(pat)
    if pp.is_absolute() or (len(pat) > 1 and pat[1] == ":"):
        # 找到第一个含通配符的部分，之前的当作 base 目录
        parts = pp.parts
        anchor_parts = []
        rest_parts = []
        for i, seg in enumerate(parts):
            if any(c in seg for c in "*?[]"):
                rest_parts = parts[i:]
                break
            anchor_parts.append(seg)
        else:
            # 整个 pattern 无通配符：直接当作具体路径匹配
            anchor_parts, rest_parts = parts[:-1], parts[-1:]
        base = Path(*anchor_parts) if anchor_parts else Path(path)
        pattern = "/".join(rest_parts) if rest_parts else "*"
    else:
        base = Path(path).expanduser().resolve()
    if not base.exists():
        return f"错误：路径不存在 — {base}"
    # 用对坏目录健壮的遍历替代 list(base.glob(...))：
    # Windows 下 C:\Users\<用户>\AppData\Local\Application Data 等是自引用 junction，
    # Path.glob('**/...') 会无限深入直到超 MAX_PATH 抛 OSError(WinError 3)，
    # 而 list() 一次性耗尽迭代器会让整个工具崩掉。这里捕获 OSError 跳过坏目录、
    # 用 followlinks=False + 深度上限避免 junction 死循环。
    recursive = pattern.startswith("**")
    # 取末段作为文件名匹配模式（** / *.py → *.py；具体名 → 该名）
    leaf = pattern.split("/")[-1] if pattern else "*"
    try:
        matches = _safe_glob(base, leaf, recursive)
        if not matches and not recursive:
            matches = _safe_glob(base, leaf, True)
    except ValueError as e:
        return (f"错误：无效的 glob 模式 '{pattern}' — {e}。"
                f"提示：pattern 应为相对模式（如 '**/*.py'），绝对目录请放到 path 参数。")
    if not matches:
        return f"未找到匹配 '{pattern}' 的文件"
    # Sort by modification time, newest first
    matches.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    # Limit output
    total = len(matches)
    shown = matches[:100]
    lines = []
    for m in shown:
        try:
            lines.append(str(m.relative_to(base)))
        except ValueError:
            lines.append(str(m))
    result = "\n".join(lines)
    if total > 100:
        result += f"\n\n[共 {total} 个匹配，仅显示前 100 个]"
    return result


def _safe_glob(base: Path, leaf_pattern: str, recursive: bool, max_depth: int = 25, cap: int = 5000):
    """对坏目录/自引用 junction 健壮的文件匹配。

    非递归：只匹配 base 直接子项。递归：手动用 os.scandir 下行，并用 realpath 的
    visited 集打破循环——Windows 的 junction 不是普通 symlink，os.walk(followlinks=False)
    并不会跳过它，自引用 junction（如 AppData\\Local\\Application Data）会无限深入直至
    超 MAX_PATH 抛 OSError。这里：① 跳过抛 OSError 的目录（无权限/超长）② 记录每个目录
    的 realpath，重复出现即剪枝（断环）③ max_depth + cap 双重兜底。"""
    import fnmatch
    from pathlib import Path as _P
    results = []
    try:
        if not recursive:
            for entry in os.scandir(base):
                if fnmatch.fnmatch(entry.name, leaf_pattern):
                    results.append(_P(entry.path))
            return results
    except OSError:
        return results

    visited = set()
    stack = [(str(base), 0)]
    while stack:
        if len(results) >= cap:
            break
        cur, depth = stack.pop()
        if depth > max_depth:
            continue
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            # 只对 junction/symlink 解析 realpath 去重（断环）；普通目录
                            # 不可能成环，跳过昂贵的 realpath 调用以保持速度。
                            is_reparse = False
                            try:
                                is_reparse = bool(entry.stat(follow_symlinks=False).st_reparse_tag)
                            except (OSError, AttributeError):
                                is_reparse = entry.is_symlink()
                            if is_reparse:
                                try:
                                    real = os.path.realpath(entry.path)
                                except OSError:
                                    continue
                                if real in visited:
                                    continue   # 断环：junction 自引用在此剪掉
                                visited.add(real)
                            stack.append((entry.path, depth + 1))
                        elif fnmatch.fnmatch(entry.name, leaf_pattern):
                            results.append(_P(entry.path))
                    except OSError:
                        continue
        except OSError:
            continue  # 跳过无权限/超长路径的目录
    return results


def analyze_image(path: str, question: str = "", vision_config: dict = None) -> str:
    """用视觉模型针对具体问题分析一张本地图片。

    与发送时的"通用预描述"不同，这里把主模型给出的、贴合当前对话的问题
    透传给视觉模型，从而获得有针对性的分析结果。
    """
    from app.vision import is_image, describe_image
    vc = vision_config or {}
    p = (path or "").strip()
    if not p:
        return "错误：未提供图片路径 path"
    if not Path(p).expanduser().exists():
        return f"错误：图片文件不存在 — {p}"
    if not is_image(p):
        return f"错误：'{p}' 不是受支持的图片格式（png/jpg/jpeg/gif/webp/bmp）"
    prompt = (question or "").strip() or "请详细描述这张图片的内容，包括文字、图表、场景、数据等所有细节。"
    return describe_image(
        p,
        prompt=prompt,
        api_key=vc.get("vision_api_key", ""),
        base_url=vc.get("vision_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        model=vc.get("vision_model", "qwen-vl-max"),
    )


def generate_image_tool(prompt: str, size: str = "1024x1024", vision_config: dict = None) -> str:
    """用外部生图模型（OpenAI 兼容中转）生成图片，保存到本地后返回路径标记。

    返回的 [图片: 名称 路径: ...] 标记会被前端识别并显示缩略图卡片。
    """
    from app.vision import generate_image
    vc = vision_config or {}
    r = generate_image(
        prompt=prompt,
        api_key=vc.get("imagegen_api_key", ""),
        base_url=vc.get("imagegen_base_url", ""),
        model=vc.get("imagegen_model", "gpt-image-2"),
        size=(size or "1024x1024").strip(),
        save_dir=vc.get("imagegen_save_dir", ""),
        fmt=vc.get("imagegen_format", "openai"),
    )
    if not r.get("ok"):
        return f"[图片生成失败：{r.get('error', '未知错误')}]"
    kb = r.get("size", 0) / 1024
    return (f"[图片: {r['filename']} 路径: {r['path']}]\n"
            f"已生成并保存（{kb:.0f} KB）：{r['path']}")


def grep_files(pattern: str, path: str = ".", file_type: str = "",
               multiline: bool = False, max_results: int = 50, cwd: str = "") -> str:
    """Search file contents by regex pattern."""
    import re as _re
    base = _resolve(path, cwd).resolve()
    if not base.exists():
        return f"错误：路径不存在 — {path}"

    flags = _re.MULTILINE
    if multiline:
        flags |= _re.DOTALL
    try:
        regex = _re.compile(pattern, flags)
    except _re.error as e:
        return f"正则表达式错误：{e}"

    # Determine file extensions to search
    ext_filter = set()
    if file_type:
        for t in file_type.split(","):
            t = t.strip().lstrip(".")
            ext_filter.add(f".{t}")

    results = []
    # Walk directory
    for fp in base.rglob("*"):
        if not fp.is_file():
            continue
        if ext_filter and fp.suffix.lower() not in ext_filter:
            continue
        # Skip binary/large files
        if fp.stat().st_size > 1_000_000:
            continue
        # Skip hidden/vendor dirs
        parts = fp.relative_to(base).parts
        if any(p.startswith('.') or p in ('node_modules', '__pycache__', 'venv', '.git') for p in parts):
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in regex.finditer(text):
            line_num = text[:m.start()].count('\n') + 1
            line = text.splitlines()[line_num - 1] if line_num <= len(text.splitlines()) else ""
            rel = str(fp.relative_to(base))
            results.append(f"{rel}:{line_num}: {line.strip()[:200]}")
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break

    if not results:
        return f"未找到匹配 '{pattern}' 的内容"
    output = "\n".join(results)
    if len(results) >= max_results:
        output += f"\n\n[结果已截断，仅显示前 {max_results} 条]"
    return output


def run_command(command: str, timeout: int = 30, stop_flag=None, cwd: str = "") -> str:
    import time, threading, platform

    try:
        creationflags = 0
        if platform.system() == "Windows":
            creationflags = subprocess.CREATE_NO_WINDOW
            shell_cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
        else:
            # macOS / Linux: use bash
            shell_cmd = ["/bin/bash", "-c", command]

        run_cwd = None
        if cwd:
            _b = Path(cwd).expanduser()
            if _b.is_dir():
                run_cwd = str(_b)

        proc = subprocess.Popen(
            shell_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            cwd=run_cwd,
        )

        result_holder = {}

        def _communicate():
            try:
                out, err = proc.communicate()
                result_holder['stdout'] = out
                result_holder['stderr'] = err
            except Exception as e:
                result_holder['error'] = str(e)

        t = threading.Thread(target=_communicate, daemon=True)
        t.start()

        elapsed = 0
        interval = 0.2
        while t.is_alive():
            if stop_flag and stop_flag.is_set():
                proc.kill()
                t.join(2)
                return "用户已停止命令执行"
            if elapsed >= timeout:
                proc.kill()
                t.join(2)
                return f"错误：命令超时（{timeout}s）"
            time.sleep(interval)
            elapsed += interval

        if 'error' in result_holder:
            return f"执行失败：{result_holder['error']}"

        def _decode(b: bytes) -> str:
            if not b:
                return ""
            # macOS/Linux: UTF-8 is standard; Windows may use GBK
            if platform.system() == "Windows":
                import locale
                encodings = (locale.getpreferredencoding(False), "utf-8", "gbk", "cp936")
            else:
                encodings = ("utf-8",)
            for enc in encodings:
                try:
                    return b.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    continue
            return b.decode("utf-8", errors="replace")

        stdout = _decode(result_holder.get('stdout', b''))
        stderr = _decode(result_holder.get('stderr', b''))
        output = stdout
        if stderr:
            output += f"\n[stderr]\n{stderr}"
        if proc.returncode != 0:
            output += f"\n[退出码: {proc.returncode}]"
        # conda activate 在此环境用不了：run_command 用 powershell -NoProfile，
        # 不加载 conda 的 shell 钩子（钩子在 profile 里注册）。提示模型改用环境
        # python 绝对路径，而非 conda activate。
        if "conda" in command and ("不是内部或外部命令" in stderr
                                   or "无法将" in stderr
                                   or "not recognized" in stderr
                                   or "CommandNotFoundError" in stderr
                                   or "conda activate" in command):
            output += ("\n[提示] 本环境的非交互 shell 未加载 conda 钩子，无法用 "
                       "`conda activate`。请直接用目标环境的 python 绝对路径执行，"
                       "例如 `D:/miniconda/envs/<env>/python.exe your_script.py`，"
                       "或 `D:/miniconda/envs/<env>/python.exe -m pip install ...`。")
        return output.strip() or f"（命令执行完毕，退出码 {proc.returncode}，无输出）"
    except Exception as e:
        return f"执行失败：{e}"


def web_search(query: str, max_results: int = 5, engine: str = "tavily",
               api_keys: dict = None, fallback: bool = True,
               auto_read: int = 5, read_chars: int = 8000) -> str:
    """统一搜索入口。engine 指定首选引擎，fallback=True 时失败自动降级。
    auto_read: 自动读取前 N 个结果的完整网页内容（0=不读取）。
    read_chars: 每个网页最多读取的字符数。
    """
    api_keys = api_keys or {}
    order = _build_engine_order(engine, api_keys)
    last_error = ""
    for eng in order:
        result = _search_by_engine(eng, query, max_results, api_keys)
        if not result.startswith("搜索失败") and not result.startswith("错误"):
            # Auto-read top results to provide full page content
            if auto_read > 0:
                result = _enrich_with_full_content(result, eng, query, max_results, api_keys, auto_read, read_chars)
            return f"[{eng}] {result}"
        last_error = result
        if not fallback:
            return result
    return last_error or "所有搜索引擎均失败"


def _enrich_with_full_content(search_result: str, engine: str, query: str,
                               max_results: int, api_keys: dict,
                               auto_read: int, read_chars: int) -> str:
    """Fetch full page content for top search results and append to output."""
    import re as _re
    from concurrent.futures import ThreadPoolExecutor, as_completed
    # Extract URLs from the formatted search result
    urls = _re.findall(r'URL: (https?://\S+)', search_result)
    if not urls:
        return search_result

    def _fetch(i_url):
        i, url = i_url
        try:
            content = web_read(url, max_chars=read_chars)
            if content and not content.startswith("读取失败"):
                return i, url, content
        except Exception:
            pass
        return i, url, None

    parts = [search_result, "\n\n--- 以下为搜索结果的完整网页内容 ---\n"]
    results = {}
    with ThreadPoolExecutor(max_workers=min(auto_read, 5)) as pool:
        futures = [pool.submit(_fetch, (i, url)) for i, url in enumerate(urls[:auto_read])]
        for fut in as_completed(futures):
            i, url, content = fut.result()
            if content:
                results[i] = (url, content)

    for i in sorted(results.keys()):
        url, content = results[i]
        parts.append(f"\n### [{i+1}] {url}\n{content}\n")
    return "\n".join(parts)


# ── 引擎降级顺序 ────────────────────────────────────────────────────

_ENGINE_PRIORITY = ["tavily", "brave", "firecrawl", "google", "searxng", "duckduckgo"]

def _engine_available(eng: str, api_keys: dict) -> bool:
    """Check if an engine has the required credentials configured."""
    if eng == "duckduckgo":
        return True
    if eng == "tavily":
        return bool(api_keys.get("tavily_api_key"))
    if eng == "brave":
        return bool(api_keys.get("brave_api_key"))
    if eng == "firecrawl":
        return bool(api_keys.get("firecrawl_api_key"))
    if eng == "google":
        return bool(api_keys.get("google_api_key")) and bool(api_keys.get("google_cx"))
    if eng == "searxng":
        return bool(api_keys.get("searxng_url"))
    # if eng == "bing":  # Bing Search API 即将关闭，已停用
    #     return bool(api_keys.get("bing_api_key"))
    return False


def _build_engine_order(preferred: str, api_keys: dict) -> list[str]:
    """Build fallback order: preferred first, then others with keys, DuckDuckGo last."""
    order = []
    if preferred and _engine_available(preferred, api_keys):
        order.append(preferred)
    for eng in _ENGINE_PRIORITY:
        if eng not in order and _engine_available(eng, api_keys):
            order.append(eng)
    if "duckduckgo" not in order:
        order.append("duckduckgo")
    return order


def _search_by_engine(engine: str, query: str, max_results: int, api_keys: dict) -> str:
    if engine == "tavily":
        return _search_tavily(query, max_results, api_keys.get("tavily_api_key", ""))
    elif engine == "duckduckgo":
        return _search_duckduckgo(query, max_results)
    elif engine == "brave":
        return _search_brave(query, max_results, api_keys.get("brave_api_key", ""))
    elif engine == "firecrawl":
        return _search_firecrawl(query, max_results, api_keys.get("firecrawl_api_key", ""))
    elif engine == "google":
        return _search_google(query, max_results,
                              api_keys.get("google_api_key", ""), api_keys.get("google_cx", ""))
    elif engine == "searxng":
        return _search_searxng(query, max_results, api_keys.get("searxng_url", ""))
    # elif engine == "bing":  # Bing Search API 即将关闭，已停用
    #     return _search_bing(query, max_results, api_keys.get("bing_api_key", ""))
    return f"错误：未知搜索引擎 {engine}"


def _format_results(results: list[dict]) -> str:
    """Format a list of {title, url, content} dicts into readable text."""
    if not results:
        return "未找到相关结果"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.get('title', '')}")
        lines.append(f"   URL: {r.get('url', '')}")
        lines.append(f"   {r.get('content', '')[:600]}")
        lines.append("")
    return "\n".join(lines)


# ── Tavily ───────────────────────────────────────────────────────────

def _search_tavily(query: str, max_results: int, api_key: str) -> str:
    if not api_key:
        return "错误：未配置 Tavily API Key"
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        resp = client.search(query=query, max_results=max_results)
        items = resp.get("results", [])
        return _format_results([
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
            for r in items
        ])
    except Exception as e:
        return f"搜索失败：{e}"


# ── DuckDuckGo ───────────────────────────────────────────────────────

def _search_duckduckgo(query: str, max_results: int) -> str:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
        if not raw:
            return "未找到相关结果"
        return _format_results([
            {"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")}
            for r in raw
        ])
    except ImportError:
        return "搜索失败：duckduckgo-search 未安装，请运行 pip install duckduckgo-search"
    except Exception as e:
        return f"搜索失败：{e}"


# ── Bing Search API（即将关闭，已停用）──────────────────────────────
# def _search_bing(query: str, max_results: int, api_key: str) -> str:
#     if not api_key:
#         return "错误：未配置 Bing API Key"
#     try:
#         import urllib.request
#         import urllib.parse
#         url = f"https://api.bing.microsoft.com/v7.0/search?q={urllib.parse.quote(query)}&count={max_results}"
#         req = urllib.request.Request(url, headers={
#             "Ocp-Apim-Subscription-Key": api_key,
#         })
#         with urllib.request.urlopen(req, timeout=10) as resp:
#             data = json.loads(resp.read().decode("utf-8"))
#         pages = data.get("webPages", {}).get("value", [])
#         return _format_results([
#             {"title": p.get("name", ""), "url": p.get("url", ""), "content": p.get("snippet", "")}
#             for p in pages
#         ])
#     except Exception as e:
#         return f"搜索失败：{e}"


# ── Brave Search ────────────────────────────────────────────────────

def _search_brave(query: str, max_results: int, api_key: str) -> str:
    if not api_key:
        return "错误：未配置 Brave Search API Key"
    try:
        import urllib.request
        import urllib.parse
        url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(query)}&count={max_results}"
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            # Handle gzip
            if resp.headers.get("Content-Encoding") == "gzip":
                import gzip
                raw = gzip.decompress(resp.read())
            else:
                raw = resp.read()
            data = json.loads(raw.decode("utf-8"))
        results = data.get("web", {}).get("results", [])[:max_results]
        return _format_results([
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("description", "")}
            for r in results
        ])
    except Exception as e:
        return f"搜索失败：{e}"


# ── Firecrawl ───────────────────────────────────────────────────────

def _search_firecrawl(query: str, max_results: int, api_key: str) -> str:
    if not api_key:
        return "错误：未配置 Firecrawl API Key"
    try:
        from firecrawl import Firecrawl
        app = Firecrawl(api_key=api_key)
        resp = app.search(query, limit=max_results)
        if not resp:
            return "未找到相关结果"
        # Firecrawl search returns list of results with markdown content
        items = resp if isinstance(resp, list) else resp.get("data", [])
        return _format_results([
            {
                "title": r.get("title", r.get("metadata", {}).get("title", "")),
                "url": r.get("url", r.get("metadata", {}).get("sourceURL", "")),
                "content": r.get("markdown", r.get("content", r.get("description", "")))[:1500],
            }
            for r in items[:max_results]
        ])
    except ImportError:
        return "搜索失败：firecrawl-py 未安装，请运行 pip install firecrawl-py"
    except Exception as e:
        return f"搜索失败：{e}"


# ── Google Custom Search ─────────────────────────────────────────────

def _search_google(query: str, max_results: int, api_key: str, cx: str) -> str:
    if not api_key or not cx:
        return "错误：未配置 Google API Key 或 CX ID"
    try:
        import urllib.request
        import urllib.parse
        num = min(max_results, 10)
        url = (f"https://www.googleapis.com/customsearch/v1"
               f"?key={api_key}&cx={cx}&q={urllib.parse.quote(query)}&num={num}")
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("items", [])
        return _format_results([
            {"title": it.get("title", ""), "url": it.get("link", ""), "content": it.get("snippet", "")}
            for it in items
        ])
    except Exception as e:
        return f"搜索失败：{e}"


# ── SearXNG ──────────────────────────────────────────────────────────

def _search_searxng(query: str, max_results: int, base_url: str) -> str:
    if not base_url:
        return "错误：未配置 SearXNG URL"
    try:
        import urllib.request
        import urllib.parse
        url = f"{base_url.rstrip('/')}/search?q={urllib.parse.quote(query)}&format=json&pageno=1"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results", [])[:max_results]
        return _format_results([
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
            for r in results
        ])
    except Exception as e:
        return f"搜索失败：{e}"


def web_read(url: str, max_chars: int = 20000) -> str:
    """Fetch a URL and return its text content (HTML stripped to readable text)."""
    try:
        import urllib.request
        import re as _re
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        # Try utf-8 first, then detect from headers
        charset = "utf-8"
        ct = resp.headers.get("Content-Type", "")
        if "charset=" in ct:
            charset = ct.split("charset=")[-1].strip().split(";")[0]
        try:
            html = raw.decode(charset)
        except Exception:
            html = raw.decode("utf-8", errors="replace")
        # Strip HTML tags, scripts, styles
        html = _re.sub(r'<script[^>]*>[\s\S]*?</script>', '', html, flags=_re.IGNORECASE)
        html = _re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html, flags=_re.IGNORECASE)
        html = _re.sub(r'<[^>]+>', ' ', html)
        # Collapse whitespace
        text = _re.sub(r'\s+', ' ', html).strip()
        # Decode HTML entities
        import html as _html_mod
        text = _html_mod.unescape(text)
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[内容已截断，共 {len(text)} 字符，显示前 {max_chars} 字符]"
        return text if text else "（页面无文本内容）"
    except Exception as e:
        return f"读取失败：{e}"


def write_file(path: str, content: str, cwd: str = "") -> str:
    _reset_file_op_log()
    try:
        p = _resolve(path, cwd).resolve()
        is_new = not p.exists()
        old_content = ""
        old_lines = 0
        if not is_new:
            try:
                old_content = p.read_text(encoding="utf-8", errors="replace")
                old_lines = len(old_content.splitlines())
            except Exception:
                pass
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        _record_file_op(str(p), old_content, content)
        new_lines = len(content.splitlines())
        if is_new:
            return (f"✅ 文件已创建：{p}\n"
                    f"   📁 目录：{p.parent}\n"
                    f"   📄 大小：{len(content)} 字符，{new_lines} 行")
        else:
            diff = new_lines - old_lines
            diff_str = f"+{diff}" if diff > 0 else str(diff) if diff < 0 else "±0"
            return (f"✅ 文件已覆盖：{p}\n"
                    f"   📁 目录：{p.parent}\n"
                    f"   📄 {old_lines} 行 → {new_lines} 行（{diff_str} 行），{len(content)} 字符")
    except Exception as e:
        return f"写入失败：{e}"


def apply_patch(edits=None, cwd: str = "", patch: str = "") -> str:
    """基于精确字符串替换修改文件（取代旧的 unified-diff 实现）。

    旧实现按 diff 行号盲切片、不校验上下文，模型行号稍错就会静默写坏文件却返回成功，
    逼得它整文件重写。新实现要求模型提供「原文片段 old_string → 新内容 new_string」，
    做精确匹配替换：匹配不到、或多处匹配又没开 replace_all，都明确报错而非乱写。

    参数：
      edits: 列表，每项 {path, old_string, new_string, replace_all?}
        - old_string 为空串 ⇒ 新建文件（或覆盖空文件），内容为 new_string。
        - old_string 非空 ⇒ 必须在文件中唯一出现；多处出现需置 replace_all=True 才会全替。
      patch: 兼容旧调用签名的占位参数，已不支持 diff，传入时返回明确提示。
    """
    if patch and not edits:
        return ("apply_patch 已改为精确字符串替换，不再支持 unified diff。"
                "请改用 edits 参数：[{path, old_string, new_string, replace_all?}]。"
                "old_string 需与文件中的原文逐字符一致（含缩进），且唯一定位。")

    if not edits:
        return "apply_patch：未提供 edits，未做任何修改。"
    if isinstance(edits, dict):
        edits = [edits]
    if not isinstance(edits, list):
        return "apply_patch：edits 必须是对象或对象列表。"

    _reset_file_op_log()
    results = []
    for i, ed in enumerate(edits):
        if not isinstance(ed, dict):
            results.append(f"❌ 第 {i + 1} 项编辑格式错误（应为对象）")
            continue
        path = (ed.get("path") or "").strip()
        old_string = ed.get("old_string", "")
        new_string = ed.get("new_string", "")
        replace_all = bool(ed.get("replace_all", False))

        if not path:
            results.append(f"❌ 第 {i + 1} 项缺少 path")
            continue

        target = _resolve(path, cwd)

        # 新建文件：old_string 为空
        if old_string == "":
            if target.exists() and target.read_text(encoding="utf-8", errors="replace").strip():
                results.append(
                    f"❌ {target}: old_string 为空表示新建文件，但该文件已存在且非空。"
                    f"若要修改已有文件，请提供要替换的原文片段作为 old_string。"
                )
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(new_string, encoding="utf-8")
                _record_file_op(str(target.resolve()), "", new_string)
                results.append(f"✅ {target.resolve()}\n   📁 目录：{target.resolve().parent}\n   📝 新建文件 | {len(new_string.splitlines())} 行")
            except Exception as e:
                results.append(f"❌ {target}: 写入失败 - {e}")
            continue

        # 修改已有文件
        if not target.exists():
            results.append(f"❌ {target}: 文件不存在，无法替换。新建文件请将 old_string 留空。")
            continue

        content = target.read_text(encoding="utf-8", errors="replace")
        count = content.count(old_string)
        if count == 0:
            results.append(
                f"❌ {target}: 未找到 old_string，未修改。"
                f"old_string 必须与文件原文逐字符一致（含空格/缩进/换行）。"
                f"建议先 read_file 复制准确原文再重试。"
            )
            continue
        if count > 1 and not replace_all:
            results.append(
                f"❌ {target}: old_string 在文件中出现 {count} 次，定位不唯一，未修改。"
                f"请扩充 old_string 上下文使其唯一，或设 replace_all=true 全部替换。"
            )
            continue

        if old_string == new_string:
            results.append(f"⚠ {target}: old_string 与 new_string 相同，未做改动。")
            continue

        new_content = content.replace(old_string, new_string) if replace_all \
            else content.replace(old_string, new_string, 1)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new_content, encoding="utf-8")
            _record_file_op(str(target.resolve()), content, new_content)
            n = count if replace_all else 1
            results.append(
                f"✅ {target.resolve()}\n"
                f"   📁 目录：{target.resolve().parent}\n"
                f"   📝 替换 {n} 处"
            )
        except Exception as e:
            results.append(f"❌ {target}: 写入失败 - {e}")

    return '\n'.join(results) if results else "apply_patch：未做任何修改。"


# ── 工具 Schema（供 OpenAI Function Calling 使用）────────────────────

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取本地文件内容，支持 txt/md/py/json/csv/pdf/docx/xlsx 等格式",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件的绝对或相对路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出指定目录下的文件和子目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob_files",
            "description": "按文件名模式匹配搜索文件（如 **/*.py、src/**/*.ts）。结果按修改时间排序（最新在前）。用于快速定位文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "glob 模式，如 **/*.py、*.md、src/**/*.ts"},
                    "path": {"type": "string", "description": "搜索起始目录，默认当前目录", "default": "."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": "用视觉模型针对具体问题分析一张本地图片。当用户消息中附带了图片（形如 [图片: 文件名 路径: ...]）且需要了解图片内容时调用。\n注意：视觉模型是独立、无记忆的——每次调用它只能看到你这次传入的 question，看不到本对话的任何上下文、也记不住上一次调用。因此你必须在 question 里把必要的背景补全：当前在讨论什么、要它聚焦图中哪个区域/对象、需要什么粒度的信息。\n若你对同一张图有多个问题，尽量合并进一次调用（在 question 里编号列出 ①②③），而不是拆成多次互不相通的调用。\n请根据用户的实际问题撰写贴合的 question，而不是泛泛地要求描述。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "图片的本地绝对路径（取自用户消息中标注的图片路径）"},
                    "question": {"type": "string", "description": "给视觉模型的完整提问，需自带背景。推荐结构：①一句话交代当前讨论的背景/任务；②明确要它看图中的哪个区域或对象；③具体要回答的问题（多个问题用 ①②③ 编号）。例：『用户在排查这张电路图左上角电源模块的接线。请只看左上角电源部分，回答：① 二极管 D1 的极性方向；② 是否存在明显接反或短路。』"},
                },
                "required": ["path", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "用外部生图模型生成图片（调用 OpenAI 兼容的图片生成接口）。当用户要求生成/绘制/画一张图、设计图标、做插画等时调用。生成的图片会保存到本地并在对话中显示。请把用户的需求转写成清晰、具体的英文或中文 prompt（描述主体、风格、配色、构图等）以获得更好效果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "图片生成提示词，尽量具体（主体、风格、配色、构图、背景等）"},
                    "size": {"type": "string", "description": "图片尺寸，如 1024x1024、1024x1536、1536x1024", "default": "1024x1024"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_files",
            "description": "在文件内容中搜索正则表达式。支持文件类型过滤和多行模式。返回匹配的文件路径、行号和内容。用于在代码库中查找特定函数、变量、字符串等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "正则表达式搜索模式"},
                    "path": {"type": "string", "description": "搜索起始目录，默认当前目录", "default": "."},
                    "file_type": {"type": "string", "description": "限定文件类型，如 py,ts,js（逗号分隔，可选）"},
                    "multiline": {"type": "boolean", "description": "是否启用多行模式（. 匹配换行符）", "default": False},
                    "max_results": {"type": "integer", "description": "最大返回结果数，默认 50", "default": 50},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "使用 Tavily 搜索互联网获取实时信息。每次搜索消耗 API 配额，请高效使用：先用一个精准的关键词搜索，根据结果判断是否需要补充搜索。通常 1-5 次搜索即可满足需求，避免对同一主题反复搜索。如果搜索结果的摘要不够详细，请使用 web_read 工具读取具体网页的完整内容，而不是继续搜索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "max_results": {"type": "integer", "description": "返回结果数量，默认 5", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_read",
            "description": "读取指定 URL 的网页完整内容（HTML 转纯文本）。当 web_search 的摘要不够详细时，用此工具获取完整页面。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要读取的网页 URL"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "在 PowerShell 中执行命令，返回输出结果。支持 PowerShell 语法，包括 &&、$ENV:VAR、管道等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "timeout": {"type": "integer", "description": "超时秒数，默认 30", "default": 30},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将内容写入本地文件（会覆盖已有文件）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目标文件路径"},
                    "content": {"type": "string", "description": "要写入的文本内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": "精确修改文件：用「原文片段 old_string → 新内容 new_string」做字符串替换，比 write_file 安全（只改指定片段，不覆盖整文件），比行号 diff 可靠（不会因行号算错而写坏文件）。修改前务必先 read_file 拿到准确原文。支持一次多处编辑、多文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "edits": {
                        "type": "array",
                        "description": "编辑列表，按顺序应用。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "目标文件路径（相对路径以项目目录为基准）"},
                                "old_string": {"type": "string", "description": "要被替换的原文片段，必须与文件中逐字符一致（含空格、缩进、换行），并能唯一定位。留空串表示新建文件。"},
                                "new_string": {"type": "string", "description": "替换后的新内容。"},
                                "replace_all": {"type": "boolean", "description": "old_string 在文件中多处出现时，是否全部替换。默认 false（要求唯一匹配）。"},
                            },
                            "required": ["path", "old_string", "new_string"],
                        },
                    },
                },
                "required": ["edits"],
            },
        },
    },
]

# 需要用户确认的工具
CONFIRM_REQUIRED = {"run_command", "write_file", "apply_patch"}


def dispatch(tool_name: str, args: dict, search_config: dict = None, timeout: int = 30, stop_flag=None, vision_config: dict = None, cwd: str = "") -> str:
    """执行工具调用，返回字符串结果。cwd 为项目目录，相对路径以此为基准。"""
    if tool_name == "read_file":
        return read_file(args.get("path", ""), cwd=cwd)
    elif tool_name == "analyze_image":
        return analyze_image(args.get("path", ""), args.get("question", ""), vision_config=vision_config)
    elif tool_name == "generate_image":
        return generate_image_tool(args.get("prompt", ""), args.get("size", "1024x1024"), vision_config=vision_config)
    elif tool_name == "list_directory":
        return list_directory(args.get("path", ""), cwd=cwd)
    elif tool_name == "glob_files":
        return glob_files(args.get("pattern", ""), args.get("path", "."), cwd=cwd)
    elif tool_name == "grep_files":
        return grep_files(
            args.get("pattern", ""), args.get("path", "."),
            file_type=args.get("file_type", ""),
            multiline=args.get("multiline", False),
            max_results=args.get("max_results", 50),
            cwd=cwd,
        )
    elif tool_name == "web_search":
        sc = search_config or {}
        return web_search(
            args.get("query", ""), args.get("max_results", 5),
            engine=sc.get("engine", "tavily"),
            api_keys=sc,
            fallback=sc.get("fallback", True),
        )
    elif tool_name == "web_read":
        return web_read(args.get("url", ""))
    elif tool_name == "run_command":
        return run_command(args.get("command", ""), args.get("timeout", timeout), stop_flag=stop_flag, cwd=cwd)
    elif tool_name == "write_file":
        return write_file(args.get("path", ""), args.get("content", ""), cwd=cwd)
    elif tool_name == "apply_patch":
        return apply_patch(edits=args.get("edits"), cwd=cwd, patch=args.get("patch", ""))
    else:
        return f"未知工具：{tool_name}"
