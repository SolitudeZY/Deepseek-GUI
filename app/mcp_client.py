"""Persistent MCP client manager for stdio and Streamable HTTP servers."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import re
import threading
import tempfile
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Optional


MCP_TOOL_PREFIX = "mcp__"
DEFAULT_CONNECT_TIMEOUT = 15
DEFAULT_CALL_TIMEOUT = 60
MAX_RESULT_CHARS = 60_000
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_TOOL_CHAR_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")


class MCPConfigError(ValueError):
    pass


def _bounded_int(value: Any, default: int, minimum: int = 1, maximum: int = 600) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k).strip(): str(v) for k, v in value.items() if str(k).strip()}


def normalize_server_config(raw: Any, *, require_connection: bool = False) -> dict:
    if not isinstance(raw, dict):
        raise MCPConfigError("MCP 服务器配置必须是对象")

    transport = str(raw.get("transport", "stdio")).strip().lower()
    if transport not in ("stdio", "http"):
        raise MCPConfigError("MCP transport 仅支持 stdio 或 http")

    name = str(raw.get("name", "")).strip()
    if not name:
        raise MCPConfigError("MCP 服务器名称不能为空")

    server_id = str(raw.get("id", "")).strip() or str(uuid.uuid4())
    tool_policy = str(raw.get("tool_policy", "all")).strip().lower()
    if tool_policy not in ("all", "allowlist"):
        tool_policy = "all"

    enabled_tools = raw.get("enabled_tools", [])
    if not isinstance(enabled_tools, list):
        enabled_tools = []
    enabled_tools = list(dict.fromkeys(str(item) for item in enabled_tools if str(item)))

    stdio_raw = raw.get("stdio") if isinstance(raw.get("stdio"), dict) else {}
    http_raw = raw.get("http") if isinstance(raw.get("http"), dict) else {}
    args = stdio_raw.get("args", [])
    if isinstance(args, str):
        args = [line.strip() for line in args.splitlines() if line.strip()]
    elif isinstance(args, list):
        args = [str(item) for item in args]
    else:
        args = []

    config = {
        "id": server_id,
        "name": name,
        "enabled": bool(raw.get("enabled", True)),
        "transport": transport,
        "trusted": bool(raw.get("trusted", False)),
        "connect_timeout": _bounded_int(raw.get("connect_timeout"), DEFAULT_CONNECT_TIMEOUT),
        "call_timeout": _bounded_int(raw.get("call_timeout"), DEFAULT_CALL_TIMEOUT),
        "tool_policy": tool_policy,
        "enabled_tools": enabled_tools,
        "stdio": {
            "command": str(stdio_raw.get("command", "")).strip(),
            "args": args,
            "cwd": str(stdio_raw.get("cwd", "")).strip(),
            "env": _string_map(stdio_raw.get("env")),
        },
        "http": {
            "url": str(http_raw.get("url", "")).strip(),
            "headers": _string_map(http_raw.get("headers")),
        },
    }

    if require_connection or config["enabled"]:
        if transport == "stdio" and not config["stdio"]["command"]:
            raise MCPConfigError(f"MCP 服务器「{name}」缺少 stdio command")
        if transport == "http":
            url = config["http"]["url"]
            if not url:
                raise MCPConfigError(f"MCP 服务器「{name}」缺少 HTTP URL")
            if not url.lower().startswith(("http://", "https://")):
                raise MCPConfigError(f"MCP 服务器「{name}」的 URL 必须以 http:// 或 https:// 开头")
    return config


def normalize_server_configs(raw_servers: Any) -> list[dict]:
    if raw_servers in (None, ""):
        return []
    if not isinstance(raw_servers, list):
        raise MCPConfigError("mcp_servers 必须是数组")
    normalized = [normalize_server_config(item) for item in raw_servers]
    ids: set[str] = set()
    names: set[str] = set()
    for server in normalized:
        name_key = server["name"].casefold()
        if server["id"] in ids:
            raise MCPConfigError(f"MCP 服务器 ID 重复：{server['id']}")
        if name_key in names:
            raise MCPConfigError(f"MCP 服务器名称重复：{server['name']}")
        ids.add(server["id"])
        names.add(name_key)
    return normalized


def expand_environment_map(values: dict[str, str]) -> tuple[dict[str, str], set[str]]:
    expanded: dict[str, str] = {}
    secrets: set[str] = set()
    for key, raw_value in values.items():
        missing: set[str] = set()

        def replace(match: re.Match) -> str:
            env_name = match.group(1)
            env_value = os.environ.get(env_name)
            if env_value is None:
                missing.add(env_name)
                return ""
            return env_value

        value = _ENV_PATTERN.sub(replace, raw_value)
        if missing:
            names = ", ".join(sorted(missing))
            raise MCPConfigError(f"缺少环境变量：{names}")
        expanded[key] = value
        if len(value) >= 4:
            secrets.add(value)
        if any(marker in key.casefold() for marker in ("authorization", "token", "secret", "password", "api_key", "apikey")):
            for part in re.split(r"[\s:=]+", value):
                if len(part) >= 4:
                    secrets.add(part)
    return expanded, secrets


def redact_text(value: Any, secrets: set[str]) -> str:
    text = str(value or "")
    for secret in sorted((item for item in secrets if len(item) >= 4), key=len, reverse=True):
        text = text.replace(secret, "***")
    text = re.sub(r"(?i)(authorization\s*[:=]\s*)([^\r\n]+)", r"\1***", text)
    return text


def redact_value(value: Any, secrets: set[str]) -> Any:
    """Redact strings recursively while preserving JSON-compatible shapes."""
    if isinstance(value, dict):
        return {
            redact_text(key, secrets): redact_value(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item, secrets) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item, secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, secrets)
    return value


def exception_text(exc: Any, secrets: set[str]) -> str:
    messages: list[str] = []

    def collect(item: Any) -> None:
        nested = getattr(item, "exceptions", None)
        if nested:
            for child in nested:
                collect(child)
            return
        message = redact_text(item, secrets).strip()
        if message and message not in messages:
            messages.append(message)

    collect(exc)
    return "; ".join(messages) or type(exc).__name__


def _slug(value: str, fallback: str) -> str:
    cleaned = _TOOL_CHAR_PATTERN.sub("_", value.strip()).strip("_")
    return cleaned or fallback


def build_tool_name(server_name: str, tool_name: str, used: Optional[set[str]] = None, route_key: str = "") -> str:
    server_slug = _slug(server_name, "server")
    tool_slug = _slug(tool_name, "tool")
    base = f"{MCP_TOOL_PREFIX}{server_slug}__{tool_slug}"
    used = used if used is not None else set()
    needs_hash = len(base) > 64 or base in used
    if needs_hash:
        seed = route_key or f"{server_name}\0{tool_name}"
        salt = 0
        while True:
            digest_seed = seed if salt == 0 else f"{seed}\0{salt}"
            digest = hashlib.sha256(digest_seed.encode("utf-8")).hexdigest()[:8]
            suffix = f"__{digest}"
            candidate = base[: 64 - len(suffix)].rstrip("_") + suffix
            if candidate not in used:
                base = candidate
                break
            salt += 1
    used.add(base)
    return base


def normalize_tool_input_schema(schema: Any, secrets: set[str]) -> dict:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return {"type": "object", "properties": {}}
    normalized = redact_value(schema, secrets)
    if not isinstance(normalized.get("properties"), dict):
        normalized["properties"] = {}
    return normalized


def _image_extension(mime_type: str) -> str:
    common = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }
    return common.get(mime_type.lower(), mimetypes.guess_extension(mime_type) or ".bin")


def _save_image_block(data: str, mime_type: str) -> str:
    from app.config import get_app_data_dir

    uploads = get_app_data_dir() / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    filename = f"mcp_{uuid.uuid4().hex}{_image_extension(mime_type)}"
    path = uploads / filename
    path.write_bytes(base64.b64decode(data, validate=True))
    return f"[图片: {filename} 路径: {path}]"


def format_mcp_result(result: Any, max_chars: int = MAX_RESULT_CHARS) -> str:
    parts: list[str] = []
    for block in getattr(result, "content", []) or []:
        block_type = getattr(block, "type", "")
        if block_type == "text":
            parts.append(str(getattr(block, "text", "")))
        elif block_type == "image":
            try:
                parts.append(_save_image_block(getattr(block, "data", ""), getattr(block, "mimeType", "image/png")))
            except Exception as exc:
                parts.append(f"[MCP 图片保存失败：{exc}]")
        elif block_type == "audio":
            parts.append(f"[MCP 音频内容：{getattr(block, 'mimeType', 'application/octet-stream')}]" )
        elif block_type == "resource_link":
            parts.append(f"[MCP 资源：{getattr(block, 'name', '')} {getattr(block, 'uri', '')}]".strip())
        elif block_type == "resource":
            resource = getattr(block, "resource", None)
            text = getattr(resource, "text", None)
            if text is not None:
                parts.append(str(text))
            else:
                parts.append(f"[MCP 嵌入资源：{getattr(resource, 'uri', '')}]".strip())
        else:
            parts.append(f"[MCP 不支持的内容类型：{block_type or type(block).__name__}]")

    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        rendered = json.dumps(structured, ensure_ascii=False, indent=2, default=str)
        if rendered not in parts:
            parts.append(f"[structured]\n{rendered}")

    output = "\n\n".join(part for part in parts if part).strip() or "（MCP 工具执行完成，无输出）"
    if getattr(result, "isError", False):
        output = f"MCP 工具返回错误：\n{output}"
    if len(output) > max_chars:
        output = output[:max_chars] + f"\n\n[结果已截断，原始长度 {len(output)} 字符]"
    return output


@dataclass
class _Command:
    action: str
    future: asyncio.Future
    tool_name: str = ""
    arguments: dict = field(default_factory=dict)


@dataclass
class _Worker:
    key: str
    config: dict
    fingerprint: str
    queue: asyncio.Queue
    ready: asyncio.Future
    task: Optional[asyncio.Task] = None
    tools: list[Any] = field(default_factory=list)
    protocol_version: str = ""
    server_info: str = ""
    secrets: set[str] = field(default_factory=set)
    stderr: Any = None
    report_status: bool = True


class MCPManager:
    def __init__(self, servers: Any = None):
        self._lock = threading.RLock()
        self._configs = {item["id"]: item for item in normalize_server_configs(servers or [])}
        self._statuses: dict[str, dict] = {}
        self._routes: dict[str, dict] = {}
        self._workers: dict[str, _Worker] = {}
        self._closed = False
        self._loop = asyncio.new_event_loop()
        self._started = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, name="QuickModel-MCP", daemon=True)
        self._thread.start()
        self._started.wait(5)
        self._reset_statuses()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self._loop.close()

    def _reset_statuses(self) -> None:
        with self._lock:
            current = self._statuses
            self._statuses = {}
            for server_id, config in self._configs.items():
                previous = current.get(server_id, {})
                self._statuses[server_id] = {
                    "id": server_id,
                    "name": config["name"],
                    "transport": config["transport"],
                    "enabled": config["enabled"],
                    "state": previous.get("state", "disconnected") if config["enabled"] else "disconnected",
                    "protocol_version": previous.get("protocol_version", ""),
                    "server_info": previous.get("server_info", ""),
                    "tool_count": previous.get("tool_count", 0),
                    "last_error": previous.get("last_error", ""),
                }

    def _set_status(self, server_id: str, **updates: Any) -> None:
        with self._lock:
            status = self._statuses.get(server_id)
            if status is None:
                config = self._configs.get(server_id, {})
                status = {
                    "id": server_id,
                    "name": config.get("name", server_id),
                    "transport": config.get("transport", ""),
                    "enabled": config.get("enabled", True),
                    "state": "disconnected",
                    "protocol_version": "",
                    "server_info": "",
                    "tool_count": 0,
                    "last_error": "",
                }
                self._statuses[server_id] = status
            status.update(updates)

    @staticmethod
    def _fingerprint(config: dict) -> str:
        return hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _submit(self, coroutine, timeout: float):
        if self._closed:
            raise RuntimeError("MCP 管理器已关闭")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result(timeout=timeout)

    async def _open_transport(self, stack: AsyncExitStack, worker: _Worker):
        import httpx
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp.client.streamable_http import streamable_http_client

        config = worker.config
        if config["transport"] == "stdio":
            env, secrets = expand_environment_map(config["stdio"]["env"])
            worker.secrets.update(secrets)
            worker.stderr = tempfile.SpooledTemporaryFile(
                max_size=1_000_000, mode="w+", encoding="utf-8", errors="replace"
            )
            params = StdioServerParameters(
                command=config["stdio"]["command"],
                args=config["stdio"]["args"],
                env={**os.environ, **env} if env else None,
                cwd=config["stdio"]["cwd"] or None,
            )
            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(params, errlog=worker.stderr)
            )
        else:
            headers, secrets = expand_environment_map(config["http"]["headers"])
            worker.secrets.update(secrets)
            http_client = await stack.enter_async_context(
                httpx.AsyncClient(
                    headers=headers,
                    timeout=httpx.Timeout(max(config["connect_timeout"], config["call_timeout"])),
                )
            )
            read_stream, write_stream, _ = await stack.enter_async_context(
                streamable_http_client(config["http"]["url"], http_client=http_client)
            )
        return read_stream, write_stream

    async def _worker_main(self, worker: _Worker) -> None:
        import anyio
        from mcp.client.session import ClientSession

        server_id = worker.config["id"]
        if worker.report_status:
            self._set_status(server_id, state="connecting", last_error="")
        try:
            async with AsyncExitStack() as stack:
                read_stream, write_stream = await self._open_transport(stack, worker)
                session = await stack.enter_async_context(
                    ClientSession(
                        read_stream,
                        write_stream,
                        read_timeout_seconds=timedelta(seconds=max(
                            worker.config["connect_timeout"],
                            worker.config["call_timeout"],
                        )),
                    )
                )
                with anyio.fail_after(worker.config["connect_timeout"]):
                    initialized = await session.initialize()
                    listed = await session.list_tools()
                worker.tools = list(listed.tools)
                worker.protocol_version = str(getattr(initialized, "protocolVersion", "") or "")
                info = getattr(initialized, "serverInfo", None)
                if info is not None:
                    info_name = getattr(info, "name", "")
                    info_version = getattr(info, "version", "")
                    worker.server_info = redact_text(
                        " ".join(part for part in (str(info_name), str(info_version)) if part).strip(),
                        worker.secrets,
                    )
                if worker.report_status:
                    self._set_status(
                        server_id,
                        state="connected",
                        protocol_version=worker.protocol_version,
                        server_info=worker.server_info,
                        tool_count=len(worker.tools),
                        last_error="",
                    )
                if not worker.ready.done():
                    worker.ready.set_result(True)

                while True:
                    command: _Command = await worker.queue.get()
                    if command.action == "close":
                        if not command.future.done():
                            command.future.set_result(True)
                        break
                    try:
                        if command.action == "list":
                            with anyio.fail_after(worker.config["call_timeout"]):
                                listed = await session.list_tools()
                            worker.tools = list(listed.tools)
                            if worker.report_status:
                                self._set_status(server_id, tool_count=len(worker.tools), state="connected", last_error="")
                            result = worker.tools
                        elif command.action == "call":
                            with anyio.fail_after(worker.config["call_timeout"]):
                                result = await session.call_tool(command.tool_name, command.arguments)
                        else:
                            raise RuntimeError(f"未知 MCP worker 指令：{command.action}")
                        if not command.future.done():
                            command.future.set_result(result)
                    except Exception as exc:
                        message = exception_text(exc, worker.secrets)
                        if worker.report_status:
                            self._set_status(server_id, state="error", last_error=message)
                        if not command.future.done():
                            command.future.set_exception(RuntimeError(message))
                        break
        except asyncio.CancelledError:
            if not worker.ready.done():
                worker.ready.cancel()
            raise
        except Exception as exc:
            message = exception_text(exc, worker.secrets)
            stderr = ""
            if worker.stderr:
                try:
                    worker.stderr.flush()
                    worker.stderr.seek(0, os.SEEK_END)
                    size = worker.stderr.tell()
                    worker.stderr.seek(max(0, size - 12_000))
                    stderr = redact_text(worker.stderr.read(), worker.secrets).strip()
                except Exception:
                    stderr = ""
            if stderr and stderr not in message:
                message = f"{message}\n{stderr}".strip()
            if worker.report_status:
                self._set_status(server_id, state="error", last_error=message, tool_count=0)
            if not worker.ready.done():
                worker.ready.set_exception(RuntimeError(message))
        finally:
            while not worker.queue.empty():
                command = worker.queue.get_nowait()
                if not command.future.done():
                    command.future.set_exception(RuntimeError("MCP 连接已关闭"))
            if self._workers.get(worker.key) is worker:
                self._workers.pop(worker.key, None)
            if worker.report_status:
                status = self._statuses.get(server_id, {})
                if status.get("state") != "error":
                    self._set_status(server_id, state="disconnected")
            if worker.stderr:
                try:
                    worker.stderr.close()
                except Exception:
                    pass

    async def _ensure_worker(self, config: dict, key: Optional[str] = None, report_status: bool = True) -> _Worker:
        key = key or config["id"]
        fingerprint = self._fingerprint(config)
        worker = self._workers.get(key)
        if worker and worker.fingerprint == fingerprint and worker.task and not worker.task.done():
            await worker.ready
            return worker
        if worker:
            await self._close_worker(worker)
        loop = asyncio.get_running_loop()
        worker = _Worker(
            key=key,
            config=config,
            fingerprint=fingerprint,
            queue=asyncio.Queue(),
            ready=loop.create_future(),
            report_status=report_status,
        )
        self._workers[key] = worker
        worker.task = asyncio.create_task(self._worker_main(worker), name=f"mcp:{config['name']}")
        await worker.ready
        return worker

    async def _send(self, worker: _Worker, action: str, tool_name: str = "", arguments: Optional[dict] = None):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await worker.queue.put(_Command(action, future, tool_name, arguments or {}))
        return await future

    async def _close_worker(self, worker: _Worker) -> None:
        if not worker.task or worker.task.done():
            return
        if not worker.ready.done():
            worker.task.cancel()
        else:
            try:
                await self._send(worker, "close")
            except Exception:
                worker.task.cancel()
        await asyncio.gather(worker.task, return_exceptions=True)

    async def _get_tools_for_server(self, config: dict) -> tuple[list[Any], set[str]]:
        try:
            worker = await self._ensure_worker(config)
            return worker.tools, set(worker.secrets)
        except Exception as exc:
            self._set_status(config["id"], state="error", last_error=exception_text(exc, set()), tool_count=0)
            return [], set()

    async def _get_tool_schemas_async(self) -> list[dict]:
        with self._lock:
            configs = [dict(item) for item in self._configs.values() if item["enabled"]]
        tool_sets = await asyncio.gather(*(self._get_tools_for_server(config) for config in configs))
        records: list[tuple[dict, Any, set[str]]] = []
        for config, (tools, secrets) in zip(configs, tool_sets):
            allowlist = set(config["enabled_tools"])
            for tool in tools:
                if config["tool_policy"] == "allowlist" and tool.name not in allowlist:
                    continue
                records.append((config, tool, secrets))
        records.sort(key=lambda item: (item[0]["name"].casefold(), item[1].name.casefold()))

        used: set[str] = set()
        schemas: list[dict] = []
        routes: dict[str, dict] = {}
        for config, tool, secrets in records:
            generated = build_tool_name(
                config["name"], tool.name, used, route_key=f"{config['id']}\0{tool.name}"
            )
            input_schema = normalize_tool_input_schema(tool.inputSchema, secrets)
            description = redact_text(tool.description or tool.title or f"MCP tool {tool.name}", secrets)
            schemas.append({
                "type": "function",
                "function": {
                    "name": generated,
                    "description": f"[MCP: {config['name']}] {description}",
                    "parameters": input_schema,
                },
            })
            routes[generated] = {
                "server_id": config["id"],
                "server": config["name"],
                "tool": tool.name,
                "trusted": config["trusted"],
            }
        with self._lock:
            self._routes.update(routes)
        return schemas

    def get_tool_schemas(self) -> list[dict]:
        with self._lock:
            timeouts = [item["connect_timeout"] for item in self._configs.values() if item["enabled"]]
        if not timeouts:
            return []
        return self._submit(self._get_tool_schemas_async(), max(timeouts) + 10)

    def is_mcp_tool(self, tool_name: str) -> bool:
        return str(tool_name).startswith(MCP_TOOL_PREFIX)

    def get_call_info(self, tool_name: str) -> Optional[dict]:
        with self._lock:
            route = self._routes.get(tool_name)
            return dict(route) if route else None

    async def _call_tool_async(self, route: dict, arguments: dict):
        with self._lock:
            config = self._configs.get(route["server_id"])
        if not config or not config["enabled"]:
            raise RuntimeError("对应 MCP 服务器已禁用或删除")
        if config["tool_policy"] == "allowlist" and route["tool"] not in set(config["enabled_tools"]):
            raise RuntimeError("该 MCP 工具未启用")

        try:
            worker = await self._ensure_worker(config)
        except Exception:
            stale_worker = self._workers.get(config["id"])
            if stale_worker:
                await self._close_worker(stale_worker)
            worker = await self._ensure_worker(config)

        try:
            result = await self._send(worker, "call", route["tool"], arguments)
            return result, set(worker.secrets)
        except Exception:
            failed_worker = self._workers.get(config["id"])
            if failed_worker:
                await self._close_worker(failed_worker)
            # Do not retry an ambiguous tools/call response: the remote tool may
            # already have produced side effects before the transport failed.
            raise

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        route = self.get_call_info(tool_name)
        if not route:
            return f"MCP 工具不可用或已刷新：{tool_name}"
        with self._lock:
            config = self._configs.get(route["server_id"])
        if not config:
            return f"MCP 服务器已删除：{route['server']}"
        try:
            result, secrets = self._submit(
                self._call_tool_async(route, arguments if isinstance(arguments, dict) else {}),
                config["call_timeout"] + config["connect_timeout"] * 2 + 10,
            )
            return redact_text(format_mcp_result(result), secrets)
        except Exception as exc:
            return f"MCP 调用失败（{route['server']}/{route['tool']}）：{exception_text(exc, set())}"

    async def _test_server_async(self, config: dict) -> dict:
        key = f"test:{uuid.uuid4().hex}"
        try:
            worker = await self._ensure_worker(config, key=key, report_status=False)
            tools = [{
                "name": tool.name,
                "description": redact_text(tool.description or tool.title or "", worker.secrets),
            } for tool in worker.tools]
            return {
                "ok": True,
                "state": "connected",
                "protocol_version": worker.protocol_version,
                "server_info": worker.server_info,
                "tool_count": len(tools),
                "tools": tools,
            }
        except Exception as exc:
            return {"ok": False, "state": "error", "error": exception_text(exc, set()), "tools": []}
        finally:
            worker = self._workers.get(key)
            if worker:
                await self._close_worker(worker)

    def test_server(self, raw_config: dict) -> dict:
        try:
            config = normalize_server_config(raw_config, require_connection=True)
            config["enabled"] = True
            return self._submit(self._test_server_async(config), config["connect_timeout"] + 10)
        except Exception as exc:
            return {"ok": False, "state": "error", "error": exception_text(exc, set()), "tools": []}

    async def _reconnect_async(self, server_id: str) -> dict:
        with self._lock:
            config = self._configs.get(server_id)
        if not config:
            return {"ok": False, "error": "MCP 服务器不存在"}
        worker = self._workers.get(server_id)
        if worker:
            await self._close_worker(worker)
        try:
            worker = await self._ensure_worker(config)
            return {
                "ok": True,
                "state": "connected",
                "protocol_version": worker.protocol_version,
                "server_info": worker.server_info,
                "tool_count": len(worker.tools),
            }
        except Exception as exc:
            return {"ok": False, "state": "error", "error": exception_text(exc, set())}

    def reconnect(self, server_id: str) -> dict:
        with self._lock:
            config = self._configs.get(server_id)
        timeout = (config or {}).get("connect_timeout", DEFAULT_CONNECT_TIMEOUT) + 10
        return self._submit(self._reconnect_async(server_id), timeout)

    async def _apply_config_async(self, configs: dict[str, dict]) -> None:
        for key, worker in list(self._workers.items()):
            if key.startswith("test:"):
                continue
            config = configs.get(key)
            if not config or not config["enabled"] or self._fingerprint(config) != worker.fingerprint:
                await self._close_worker(worker)

    def apply_config(self, raw_servers: Any) -> list[dict]:
        normalized = normalize_server_configs(raw_servers)
        new_configs = {item["id"]: item for item in normalized}
        self._submit(self._apply_config_async(new_configs), 30)
        with self._lock:
            self._configs = new_configs
            active_ids = set(new_configs)
            self._routes = {
                name: route for name, route in self._routes.items()
                if route["server_id"] in active_ids
            }
        self._reset_statuses()
        return normalized

    def get_statuses(self) -> list[dict]:
        with self._lock:
            return [dict(self._statuses[key]) for key in self._configs if key in self._statuses]

    async def _shutdown_async(self) -> None:
        for worker in list(self._workers.values()):
            await self._close_worker(worker)

    def shutdown(self) -> None:
        if self._closed:
            return
        try:
            self._submit(self._shutdown_async(), 30)
        except Exception:
            pass
        finally:
            self._closed = True
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
