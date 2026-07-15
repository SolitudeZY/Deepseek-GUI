"""Read-only import adapters for local Claude and Codex configuration."""

from __future__ import annotations

import copy
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

import tomli


_IMPORT_NAMESPACE = uuid.UUID("62d1f0d9-e641-46d8-bad2-b554e9a55528")
_CLAUDE_MODEL_ENV_KEYS = {
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
}


@dataclass
class _Candidate:
    candidate_id: str
    kind: str
    source: str
    source_label: str
    name: str
    payload: dict
    transport: str = ""
    protocol: str = ""
    importable: bool = True
    has_api_key: bool = False
    warnings: list[str] = field(default_factory=list)

    def public(self) -> dict:
        item = {
            "id": self.candidate_id,
            "kind": self.kind,
            "source": self.source,
            "source_label": self.source_label,
            "name": self.name,
            "importable": self.importable,
            "warnings": list(self.warnings),
        }
        if self.kind == "mcp":
            item["transport"] = self.transport
        else:
            item.update({
                "protocol": self.protocol,
                "model": self.payload.get("model", ""),
                "base_url": _safe_url(self.payload.get("base_url", "")),
                "has_api_key": self.has_api_key,
            })
        return item


def _candidate_id(kind: str, source: str, identity: str) -> str:
    return str(uuid.uuid5(_IMPORT_NAMESPACE, f"{kind}:{source}:{identity.casefold()}"))


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if str(key).strip()}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _timeout(value: Any, default: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(1, min(600, parsed))


def _safe_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except Exception:
        return "（已配置）"


def _path_key(path: Any) -> str:
    try:
        return os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))
    except Exception:
        return str(path).casefold()


def _read_json(path: Path, errors: list[dict]) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("root is not an object")
        return data
    except Exception:
        errors.append({"source": str(path), "error": "JSON 配置格式无效或无法读取"})
        return None


def _read_toml(path: Path, errors: list[dict]) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            data = tomli.load(handle)
        if not isinstance(data, dict):
            raise ValueError("root is not a table")
        return data
    except Exception:
        errors.append({"source": str(path), "error": "TOML 配置格式无效或无法读取"})
        return None


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _claude_server(name: str, raw: Any, source_label: str) -> _Candidate:
    candidate_id = _candidate_id("mcp", "claude", name)
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return _Candidate(
            candidate_id, "mcp", "claude", source_label, name, {},
            importable=False, warnings=["Server 配置不是对象"],
        )

    server_type = str(raw.get("type", "")).strip().lower()
    if server_type == "sse":
        return _Candidate(
            candidate_id, "mcp", "claude", source_label, name, {},
            transport="sse", importable=False,
            warnings=["QuickModel 不支持旧版 SSE 传输"],
        )

    if raw.get("command"):
        transport = "stdio"
    elif raw.get("url"):
        transport = "http"
    else:
        return _Candidate(
            candidate_id, "mcp", "claude", source_label, name, {},
            importable=False, warnings=["缺少 command 或 URL"],
        )

    payload = {
        "id": candidate_id,
        "name": name,
        "enabled": raw.get("enabled", True) is not False and raw.get("disabled", False) is not True,
        "transport": transport,
        "trusted": False,
        "connect_timeout": _timeout(raw.get("connect_timeout"), 15),
        "call_timeout": _timeout(raw.get("call_timeout"), 60),
        "tool_policy": "all",
        "enabled_tools": [],
        "stdio": {
            "command": str(raw.get("command", "")).strip(),
            "args": _string_list(raw.get("args")),
            "cwd": str(raw.get("cwd", "")).strip(),
            "env": _string_map(raw.get("env")),
        },
        "http": {
            "url": str(raw.get("url", "")).strip(),
            "headers": _string_map(raw.get("headers")),
        },
    }
    return _Candidate(
        candidate_id, "mcp", "claude", source_label, name, payload,
        transport=transport, warnings=warnings,
    )


def _codex_server(name: str, raw: Any, source_label: str) -> _Candidate:
    candidate_id = _candidate_id("mcp", "codex", name)
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return _Candidate(
            candidate_id, "mcp", "codex", source_label, name, {},
            importable=False, warnings=["Server 配置不是 TOML table"],
        )

    if raw.get("command"):
        transport = "stdio"
    elif raw.get("url"):
        transport = "http"
    else:
        return _Candidate(
            candidate_id, "mcp", "codex", source_label, name, {},
            importable=False, warnings=["缺少 command 或 URL"],
        )

    headers = _string_map(raw.get("http_headers"))
    env_headers = _string_map(raw.get("env_http_headers"))
    for header, env_name in env_headers.items():
        headers[header] = f"${{{env_name}}}"
    bearer_env = str(raw.get("bearer_token_env_var", "")).strip()
    if bearer_env and not any(key.casefold() == "authorization" for key in headers):
        headers["Authorization"] = f"Bearer ${{{bearer_env}}}"

    enabled_tools = _string_list(raw.get("enabled_tools"))
    disabled_tools = set(_string_list(raw.get("disabled_tools")))
    enabled = raw.get("enabled", True) is not False
    tool_policy = "all"
    if enabled_tools:
        tool_policy = "allowlist"
        enabled_tools = [item for item in enabled_tools if item not in disabled_tools]
    elif disabled_tools:
        enabled = False
        warnings.append("Codex disabled_tools 无法在发现工具前精确转换，已保持禁用，请测试并复核工具权限")

    payload = {
        "id": candidate_id,
        "name": name,
        "enabled": enabled,
        "transport": transport,
        "trusted": False,
        "connect_timeout": _timeout(raw.get("startup_timeout_sec"), 15),
        "call_timeout": _timeout(raw.get("tool_timeout_sec"), 60),
        "tool_policy": tool_policy,
        "enabled_tools": enabled_tools,
        "stdio": {
            "command": str(raw.get("command", "")).strip(),
            "args": _string_list(raw.get("args")),
            "cwd": str(raw.get("cwd", "")).strip(),
            "env": _string_map(raw.get("env")),
        },
        "http": {
            "url": str(raw.get("url", "")).strip(),
            "headers": headers,
        },
    }
    return _Candidate(
        candidate_id, "mcp", "codex", source_label, name, payload,
        transport=transport, warnings=warnings,
    )


def _matching_claude_project(data: dict, project_path: Optional[Path]) -> Optional[dict]:
    if not project_path:
        return None
    projects = data.get("projects")
    if not isinstance(projects, dict):
        return None
    target = _path_key(project_path)
    for path, config in projects.items():
        if _path_key(path) == target and isinstance(config, dict):
            return config
    return None


def _collect_mcp(project_path: str = "", home_dir: Optional[Path] = None) -> tuple[list[_Candidate], list[dict]]:
    home = Path(home_dir) if home_dir else Path.home()
    project = Path(project_path).expanduser() if str(project_path or "").strip() else None
    errors: list[dict] = []
    candidates: dict[tuple[str, str], _Candidate] = {}

    def add_many(source: str, label: str, servers: Any) -> None:
        if not isinstance(servers, dict):
            return
        parser = _claude_server if source == "claude" else _codex_server
        for name, raw in servers.items():
            candidate = parser(str(name), raw, label)
            candidates[(source, str(name).casefold())] = candidate

    claude_root = _read_json(home / ".claude.json", errors) or {}
    add_many("claude", "Claude 全局 (~/.claude.json)", claude_root.get("mcpServers"))
    claude_settings = _read_json(home / ".claude" / "settings.json", errors) or {}
    add_many("claude", "Claude 全局 settings.json", claude_settings.get("mcpServers"))
    project_entry = _matching_claude_project(claude_root, project)
    if project_entry:
        add_many("claude", "Claude 当前项目 (~/.claude.json)", project_entry.get("mcpServers"))
    if project:
        for filename in ("settings.json", "settings.local.json"):
            data = _read_json(project / ".claude" / filename, errors) or {}
            add_many("claude", f"Claude 当前项目 {filename}", data.get("mcpServers"))
        project_mcp = _read_json(project / ".mcp.json", errors) or {}
        add_many("claude", "Claude 当前项目 .mcp.json", project_mcp.get("mcpServers"))

    global_codex = _read_toml(home / ".codex" / "config.toml", errors) or {}
    project_codex = _read_toml(project / ".codex" / "config.toml", errors) if project else None
    merged_codex = _deep_merge(global_codex, project_codex or {})
    global_servers = global_codex.get("mcp_servers") if isinstance(global_codex.get("mcp_servers"), dict) else {}
    project_servers = (project_codex or {}).get("mcp_servers") if isinstance((project_codex or {}).get("mcp_servers"), dict) else {}
    for name, raw in (merged_codex.get("mcp_servers") or {}).items():
        label = "Codex 当前项目 config.toml" if name in project_servers else "Codex 全局 config.toml"
        candidate = _codex_server(str(name), raw, label)
        candidates[("codex", str(name).casefold())] = candidate

    ordered = sorted(candidates.values(), key=lambda item: (item.source, item.name.casefold()))
    return ordered, errors


def _has_claude_model_settings(config: dict) -> bool:
    if "model" in config:
        return True
    env = config.get("env")
    return isinstance(env, dict) and any(key in env for key in _CLAUDE_MODEL_ENV_KEYS)


def _claude_model_candidates(
    project: Optional[Path],
    home: Path,
    errors: list[dict],
    include_secrets: bool,
) -> list[_Candidate]:
    global_settings = _read_json(home / ".claude" / "settings.json", errors) or {}
    merged = copy.deepcopy(global_settings)
    source_label = "Claude 全局 settings.json"
    if project:
        for filename in ("settings.json", "settings.local.json"):
            project_settings = _read_json(project / ".claude" / filename, errors)
            if project_settings:
                merged = _deep_merge(merged, project_settings)
                if _has_claude_model_settings(project_settings):
                    source_label = f"Claude 当前项目 {filename}"

    env = _string_map(merged.get("env"))
    detected_api_key = env.get("ANTHROPIC_API_KEY") or env.get("ANTHROPIC_AUTH_TOKEN") or ""
    api_key = detected_api_key if include_secrets else ""
    base_url = env.get("ANTHROPIC_BASE_URL", "")
    slots = [
        ("default", env.get("ANTHROPIC_MODEL") or merged.get("model")),
        ("opus", env.get("ANTHROPIC_DEFAULT_OPUS_MODEL")),
        ("sonnet", env.get("ANTHROPIC_DEFAULT_SONNET_MODEL")),
        ("haiku", env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL")),
    ]
    candidates: list[_Candidate] = []
    seen_models: set[str] = set()
    for slot, model_value in slots:
        model = str(model_value or "").strip()
        if not model or model in seen_models:
            continue
        seen_models.add(model)
        candidate_id = _candidate_id("model", "claude", slot)
        name = f"Claude · {slot.capitalize()}"
        warnings = ["检测到 Anthropic Messages 配置；QuickModel 当前仅支持 OpenAI Chat Completions，请确认中转兼容"]
        payload = {
            "_import_id": candidate_id,
            "name": name,
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "system_prompt": "You are a helpful assistant.",
            "context_length": 1_000_000,
            "compact_threshold": 600_000,
            "use_full_url": False,
        }
        candidates.append(_Candidate(
            candidate_id, "model", "claude", source_label, name, payload,
            protocol="anthropic_messages", has_api_key=bool(detected_api_key), warnings=warnings,
        ))
    if not candidates and (detected_api_key or base_url):
        candidate_id = _candidate_id("model", "claude", "default")
        warnings = ["未检测到模型名，导入后需要手动填写", "Claude 配置可能使用 Anthropic Messages 协议"]
        candidates.append(_Candidate(
            candidate_id, "model", "claude", source_label, "Claude 本地配置",
            {
                "_import_id": candidate_id,
                "name": "Claude 本地配置",
                "api_key": api_key,
                "base_url": base_url,
                "model": "",
                "system_prompt": "You are a helpful assistant.",
                "context_length": 1_000_000,
                "compact_threshold": 600_000,
                "use_full_url": False,
            },
            protocol="anthropic_messages", has_api_key=bool(detected_api_key), warnings=warnings,
        ))
    return candidates


def _codex_api_key(
    home: Path,
    provider_name: str,
    provider: dict,
    errors: list[dict],
    include_secret: bool,
) -> tuple[bool, str]:
    env_key = str(provider.get("env_key", "")).strip()
    if env_key:
        if not include_secret:
            return env_key in os.environ, ""
        value = os.environ.get(env_key, "")
        return bool(value), value
    requires_auth = provider.get("requires_openai_auth") is True or provider_name in ("", "openai")
    if not requires_auth:
        return False, ""
    auth = _read_json(home / ".codex" / "auth.json", errors) or {}
    value = auth.get("OPENAI_API_KEY")
    detected = isinstance(value, str) and bool(value)
    return detected, value if detected and include_secret else ""


def _codex_model_candidates(
    project: Optional[Path],
    home: Path,
    errors: list[dict],
    include_secrets: bool,
) -> list[_Candidate]:
    global_config = _read_toml(home / ".codex" / "config.toml", errors) or {}
    project_config = _read_toml(project / ".codex" / "config.toml", errors) if project else None
    merged = _deep_merge(global_config, project_config or {})
    model = str(merged.get("model", "")).strip()
    provider_name = str(merged.get("model_provider", "openai")).strip() or "openai"
    providers = merged.get("model_providers") if isinstance(merged.get("model_providers"), dict) else {}
    provider = providers.get(provider_name) if isinstance(providers.get(provider_name), dict) else {}
    if not model and not provider:
        return []

    base_url = str(provider.get("base_url", "")).strip()
    if provider_name == "openai" and not base_url:
        base_url = "https://api.openai.com/v1"
    wire_api = str(provider.get("wire_api", "responses")).strip().lower() or "responses"
    protocol = "openai_chat" if wire_api in ("chat", "chat_completions", "chat-completions") else "openai_responses"
    warnings: list[str] = []
    if protocol != "openai_chat":
        warnings.append("检测到 Codex Responses API 配置；QuickModel 当前使用 Chat Completions，请确认服务端兼容")
    if not model:
        warnings.append("未检测到模型名，导入后需要手动填写")
    has_api_key, api_key = _codex_api_key(home, provider_name, provider, errors, include_secrets)
    if str(provider.get("env_key", "")).strip() and not has_api_key:
        warnings.append(f"当前进程未读取到环境变量 {provider.get('env_key')}")

    candidate_id = _candidate_id("model", "codex", provider_name)
    display_provider = str(provider.get("name", provider_name)).strip() or provider_name
    name = f"Codex · {display_provider}"
    project_providers = (project_config or {}).get("model_providers")
    project_has_active_provider = (
        isinstance(project_providers, dict) and provider_name in project_providers
    )
    project_has_model_selection = bool(project_config) and any(
        key in project_config for key in ("model", "model_provider")
    )
    source_label = (
        "Codex 当前项目 config.toml"
        if project_has_model_selection or project_has_active_provider
        else "Codex 全局 config.toml"
    )
    payload = {
        "_import_id": candidate_id,
        "name": name,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "system_prompt": "You are a helpful assistant.",
        "context_length": 1_000_000,
        "compact_threshold": 600_000,
        "use_full_url": False,
    }
    return [_Candidate(
        candidate_id, "model", "codex", source_label, name, payload,
        protocol=protocol, has_api_key=has_api_key, warnings=warnings,
    )]


def _collect_models(
    project_path: str = "",
    home_dir: Optional[Path] = None,
    include_secrets: bool = False,
) -> tuple[list[_Candidate], list[dict]]:
    home = Path(home_dir) if home_dir else Path.home()
    project = Path(project_path).expanduser() if str(project_path or "").strip() else None
    errors: list[dict] = []
    candidates = _claude_model_candidates(project, home, errors, include_secrets)
    candidates.extend(_codex_model_candidates(project, home, errors, include_secrets))
    candidates.sort(key=lambda item: (item.source, item.name.casefold()))
    return candidates, errors


def discover_external_mcp_configs(project_path: str = "", home_dir: Optional[Path] = None) -> dict:
    candidates, errors = _collect_mcp(project_path, home_dir)
    return {"candidates": [item.public() for item in candidates], "errors": errors}


def import_external_mcp_configs(
    candidate_ids: Any,
    project_path: str = "",
    home_dir: Optional[Path] = None,
) -> dict:
    selected = {str(item) for item in candidate_ids} if isinstance(candidate_ids, list) else set()
    candidates, errors = _collect_mcp(project_path, home_dir)
    items = [{
        "id": item.candidate_id,
        "config": copy.deepcopy(item.payload),
        "warnings": list(item.warnings),
    } for item in candidates if item.importable and item.candidate_id in selected]
    return {"items": items, "errors": errors}


def discover_external_model_configs(project_path: str = "", home_dir: Optional[Path] = None) -> dict:
    candidates, errors = _collect_models(project_path, home_dir, include_secrets=False)
    return {"candidates": [item.public() for item in candidates], "errors": errors}


def import_external_model_configs(
    candidate_ids: Any,
    project_path: str = "",
    home_dir: Optional[Path] = None,
) -> dict:
    selected = {str(item) for item in candidate_ids} if isinstance(candidate_ids, list) else set()
    candidates, errors = _collect_models(project_path, home_dir, include_secrets=True)
    items = [{
        "id": item.candidate_id,
        "config": copy.deepcopy(item.payload),
        "warnings": list(item.warnings),
    } for item in candidates if item.importable and item.candidate_id in selected]
    return {"items": items, "errors": errors}
