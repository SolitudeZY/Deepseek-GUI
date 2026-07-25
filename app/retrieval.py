"""Web/document retrieval helpers used by the agent tools.

This module keeps binary downloads and media extraction out of tools.py so the
tool registry remains small. All remote payloads are size-limited and cached in
the application data directory.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urljoin, urlparse


MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class RemoteContent:
    data: bytes
    content_type: str
    final_url: str
    encoding: str


def fetch_remote(url: str, max_bytes: int = MAX_DOWNLOAD_BYTES,
                 referer: str = "") -> RemoteContent:
    """Download an HTTP(S) resource with redirects and a hard size limit."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("仅支持 http:// 或 https:// URL")

    import requests

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    if referer:
        headers["Referer"] = referer
    with requests.get(url, headers=headers, timeout=(10, 35), stream=True) as resp:
        resp.raise_for_status()
        raw_content_type = resp.headers.get("Content-Type") or ""
        charset_match = re.search(r"charset\s*=\s*['\"]?([^;'\"\s]+)", raw_content_type, re.I)
        encoding = charset_match.group(1) if charset_match else ""
        length = int(resp.headers.get("Content-Length") or 0)
        if length > max_bytes:
            raise ValueError(f"远程内容过大（{length:,} bytes，上限 {max_bytes:,} bytes）")
        chunks = []
        size = 0
        for chunk in resp.iter_content(64 * 1024):
            if not chunk:
                continue
            size += len(chunk)
            if size > max_bytes:
                raise ValueError(f"远程内容超过下载上限 {max_bytes:,} bytes")
            chunks.append(chunk)
        data = b"".join(chunks)
        content_type = raw_content_type.split(";", 1)[0].lower()
        if not encoding and (content_type.startswith("text/") or "html" in content_type):
            try:
                from charset_normalizer import from_bytes
                best = from_bytes(data[:250_000]).best()
                encoding = best.encoding if best else ""
            except Exception:
                pass
        return RemoteContent(data, content_type, resp.url, encoding or "utf-8")


def source_kind(data: bytes, content_type: str = "", name: str = "") -> str:
    """Return one of html/pdf/docx/image/text/binary using MIME, suffix, and magic."""
    ct = (content_type or "").lower()
    suffix = Path(urlparse(name).path).suffix.lower()
    head = data[:512].lstrip().lower()
    if data.startswith(b"%PDF-") or "application/pdf" in ct or suffix == ".pdf":
        return "pdf"
    if (
        "wordprocessingml.document" in ct
        or suffix == ".docx"
        or (data.startswith(b"PK") and b"word/" in data[:8192])
    ):
        return "docx"
    if ct.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return "image"
    if "html" in ct or suffix in {".html", ".htm"} or b"<html" in head or b"<!doctype html" in head:
        return "html"
    if ct.startswith("text/") or suffix in {".txt", ".md", ".csv", ".json", ".xml"}:
        return "text"
    return "binary"


def decode_text(data: bytes, encoding: str = "utf-8") -> str:
    for candidate in (encoding, "utf-8", "gb18030", "big5", "windows-1252"):
        try:
            return data.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _clean_label(value: str, max_len: int = 240) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:max_len]


def extract_html_images(html: str, base_url: str, max_images: int = 20) -> list[dict]:
    """Find useful normal and lazy-loaded images, preserving captions/alt text."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    seen = set()
    for img in soup.find_all("img"):
        raw_url = ""
        for attr in ("data-original", "data-src", "data-lazy-src", "data-url"):
            value = img.get(attr)
            if value and not str(value).lower().startswith(("data:", "javascript:")):
                raw_url = str(value).strip()
                break
        if not raw_url:
            srcset = img.get("srcset") or img.get("data-srcset") or ""
            choices = [part.strip().split()[0] for part in str(srcset).split(",") if part.strip()]
            if choices:
                raw_url = choices[-1]
        if not raw_url:
            value = img.get("src")
            if value and not str(value).lower().startswith(("data:", "javascript:")):
                raw_url = str(value).strip()
        if not raw_url:
            continue
        image_url = urljoin(base_url, raw_url)
        if urlparse(image_url).scheme not in ("http", "https") or image_url in seen:
            continue
        width = str(img.get("width") or "")
        height = str(img.get("height") or "")
        if width.isdigit() and height.isdigit() and (int(width) <= 2 or int(height) <= 2):
            continue
        lowered = image_url.lower()
        if any(token in lowered for token in ("spacer.gif", "pixel.gif", "tracking", "favicon", "avatar")):
            continue
        figure = img.find_parent("figure")
        figcaption = figure.find("figcaption") if figure else None
        caption = _clean_label(
            (figcaption.get_text(" ", strip=True) if figcaption else "")
            or img.get("alt")
            or img.get("title")
        )
        seen.add(image_url)
        candidates.append({"url": image_url, "caption": caption})
        if len(candidates) >= max_images:
            break
    return candidates


def html_to_readable(html: str, base_url: str, max_chars: int = 20_000,
                     include_images: bool = True, max_images: int = 12,
                     include_links: bool = True, max_links: int = 20) -> str:
    """Extract forum/article-friendly readable text and an image inventory."""
    images = extract_html_images(html, base_url, max_images=max_images) if include_images else []
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # Graceful fallback for partially installed source checkouts.
        import html as html_module
        text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
        text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "\n", text)
        return _truncate_text(html_module.unescape(text), max_chars)

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, noscript, template, svg, canvas, nav, footer, header, aside, form"):
        tag.decompose()

    body = soup.body or soup
    candidates = soup.select(
        "main, [role=main], article, #content, #main-content, .main-content, .thread, .post-list"
    )
    root = body
    if candidates:
        best = max(candidates, key=lambda node: len(node.get_text(" ", strip=True)))
        body_length = len(body.get_text(" ", strip=True))
        best_length = len(best.get_text(" ", strip=True))
        if best_length >= min(200, max(40, body_length // 4)):
            root = best

    links = []
    if include_links:
        seen_links = set()
        for anchor in root.find_all("a", href=True):
            target = urljoin(base_url, str(anchor.get("href") or "").strip())
            parsed = urlparse(target)
            if parsed.scheme not in ("http", "https") or target in seen_links:
                continue
            label = _clean_label(anchor.get_text(" ", strip=True)) or Path(parsed.path).name
            if not label:
                continue
            seen_links.add(target)
            links.append({"url": target, "label": label})
            if len(links) >= max_links:
                break

    lines = []
    previous = None
    for raw_line in root.get_text("\n").splitlines():
        line = _clean_label(raw_line, max_len=4000)
        if not line or line == previous:
            continue
        lines.append(line)
        previous = line
    text = "\n".join(lines).strip()
    text = _truncate_text(text, max_chars)

    if images:
        inventory = ["", "## 页面图片候选（优先用 extract_images(ocr=true) 提取文字，需要视觉语义时再用 analyze_image）"]
        for index, item in enumerate(images, 1):
            label = f" - {item['caption']}" if item["caption"] else ""
            inventory.append(f"{index}. {item['url']}{label}")
        text += "\n" + "\n".join(inventory)
    if links:
        inventory = ["", "## 正文链接候选（可继续用 web_read 读取）"]
        for index, item in enumerate(links, 1):
            inventory.append(f"{index}. {item['label']} - {item['url']}")
        text += "\n" + "\n".join(inventory)
    return text or "（页面无可读文本）"


def _truncate_text(text: str, max_chars: int) -> str:
    text = re.sub(r"[ \t]+", " ", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_chars:
        return text[:max_chars] + f"\n\n[内容已截断，共 {len(text)} 字符，显示前 {max_chars} 字符]"
    return text


def _extension(content_type: str, fallback: str = "") -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    }
    if content_type in mapping:
        return mapping[content_type]
    suffix = Path(urlparse(fallback).path).suffix.lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix) else ""


def cache_bytes(data: bytes, source: str, content_type: str, output_dir: Path,
                preferred_name: str = "") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = unquote(urlparse(source).path)
    base = preferred_name or Path(source_path).name or "download"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(base).stem).strip("._") or "download"
    ext = _extension(content_type, base or source)
    digest = hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()[:12]
    path = output_dir / f"{stem[:60]}_{digest}{ext}"
    path.write_bytes(data)
    return path.resolve()


def parse_pages(spec: str, total: int, limit: int) -> list[int]:
    if total <= 0:
        return []
    if not (spec or "").strip():
        return list(range(min(total, limit)))
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_raw, end_raw = part.split("-", 1)
            start, end = int(start_raw), int(end_raw)
            if start > end:
                start, end = end, start
            values = range(start, end + 1)
        else:
            values = (int(part),)
        for page in values:
            index = page - 1
            if 0 <= index < total and index not in pages:
                pages.append(index)
            if len(pages) >= limit:
                return pages
    return pages


def _render_pdf(data: bytes, source: str, output_dir: Path, pages: str,
                max_images: int, mode: str) -> list[tuple[Path, str]]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF 未安装，无法提取 PDF 图片；请运行 pip install PyMuPDF") from exc

    doc = fitz.open(stream=data, filetype="pdf")
    selected = parse_pages(pages, doc.page_count, max_images)
    results = []
    digest = hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()[:10]
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if mode == "embedded":
            for page_index in selected:
                page = doc[page_index]
                for image_index, image in enumerate(page.get_images(full=True), 1):
                    extracted = doc.extract_image(image[0])
                    ext = extracted.get("ext", "png")
                    path = output_dir / f"pdf_{digest}_p{page_index + 1}_img{image_index}.{ext}"
                    path.write_bytes(extracted["image"])
                    results.append((path.resolve(), f"PDF 第 {page_index + 1} 页内嵌图片 {image_index}"))
                    if len(results) >= max_images:
                        return results
        else:
            matrix = fitz.Matrix(2, 2)
            for page_index in selected:
                path = output_dir / f"pdf_{digest}_page_{page_index + 1}.png"
                doc[page_index].get_pixmap(matrix=matrix, alpha=False).save(str(path))
                results.append((path.resolve(), f"PDF 第 {page_index + 1} 页（整页渲染）"))
    finally:
        doc.close()
    return results


def _extract_docx(data: bytes, source: str, output_dir: Path,
                  max_images: int) -> list[tuple[Path, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()[:10]
    results = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        media = sorted(name for name in archive.namelist() if name.startswith("word/media/") and not name.endswith("/"))
        for index, name in enumerate(media[:max_images], 1):
            payload = archive.read(name)
            ext = Path(name).suffix.lower() or ".bin"
            path = output_dir / f"docx_{digest}_{index}{ext}"
            path.write_bytes(payload)
            results.append((path.resolve(), f"Word 内嵌图片 {index}（{Path(name).name}）"))
    return results


def extract_images(source: str, output_dir: Path, pages: str = "",
                   max_images: int = 6, mode: str = "page",
                   use_ocr: bool = False) -> str:
    """Extract images/page renders and optionally run the bundled local OCR."""
    source = (source or "").strip()
    max_images = max(1, min(int(max_images or 6), 12))
    mode = "embedded" if mode == "embedded" else "page"
    remote = urlparse(source).scheme in ("http", "https")

    try:
        if remote:
            payload = fetch_remote(source)
            data, content_type, resolved_source = payload.data, payload.content_type, payload.final_url
        else:
            path = Path(source).expanduser()
            if not path.exists() or not path.is_file():
                return f"提取失败：文件不存在 — {source}"
            data, content_type, resolved_source = path.read_bytes(), "", str(path.resolve())

        kind = source_kind(data, content_type, resolved_source)
        results: list[tuple[Path, str]] = []
        if kind == "html":
            html = decode_text(data, payload.encoding if remote else "utf-8")
            candidates = extract_html_images(html, resolved_source, max_images=max_images)
            for item in candidates:
                try:
                    image = fetch_remote(
                        item["url"], max_bytes=MAX_IMAGE_BYTES,
                        referer=resolved_source,
                    )
                    if source_kind(image.data, image.content_type, image.final_url) != "image":
                        continue
                    cached = cache_bytes(image.data, image.final_url, image.content_type, output_dir)
                    results.append((cached, item["caption"] or f"网页图片 {len(results) + 1}"))
                except Exception:
                    continue
        elif kind == "pdf":
            results = _render_pdf(data, resolved_source, output_dir, pages, max_images, mode)
        elif kind == "docx":
            results = _extract_docx(data, resolved_source, output_dir, max_images)
        elif kind == "image":
            path = cache_bytes(data, resolved_source, content_type, output_dir)
            results = [(path, "原始图片")]
        else:
            return f"提取失败：不支持的来源类型（{content_type or Path(resolved_source).suffix or '未知'}）"

        if not results:
            return "未找到可提取的图片。网页可能使用脚本动态加载，或指定的 PDF 页面没有内嵌图片。"
        if use_ocr:
            try:
                from app.vision import ocr_image
                ocr_outputs = {str(path): ocr_image(str(path)) for path, _label in results}
            except Exception as exc:
                ocr_outputs = {str(path): f"错误：本地 OCR 执行失败 — {exc}" for path, _label in results}
        else:
            ocr_outputs = {}

        guidance = (
            "已同时运行本地 OCR；请优先根据正文、图注和 OCR 文字回答。只有问题涉及场景、布局、"
            "曲线趋势或空间关系时，才对相关图片调用 analyze_image。"
            if use_ocr else
            "文字型图片可再次调用本工具并设置 ocr=true，或调用 ocr_image；只有需要视觉语义时才调用 analyze_image。"
        )
        blocks = [f"已提取 {len(results)} 张图片。{guidance}"]
        for path, label in results:
            block = f"[图片: {path.name} 路径: {path}]\n\n来源说明：{label}\n来源：{resolved_source}"
            if use_ocr:
                ocr_text = ocr_outputs.get(str(path), "（未识别到文字）")
                if len(ocr_text) > 12_000:
                    ocr_text = ocr_text[:12_000] + "\n[OCR 结果已截断]"
                block += f"\n本地 OCR：\n{ocr_text}"
            blocks.append(block)
        return "\n\n".join(blocks)
    except Exception as exc:
        return f"提取失败：{exc}"
