import json
import os
import platform
from pathlib import Path
from typing import Optional

APP_NAME = "AIDesktopAssistant"
APP_VERSION = "1.6.0"
GITHUB_REPO = "SolitudeZY/Deepseek-GUI"

IS_MAC = platform.system() == "Darwin"
IS_WIN = platform.system() == "Windows"


def get_app_data_dir() -> Path:
    if IS_MAC:
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_conversations_dir() -> Path:
    d = get_app_data_dir() / "conversations"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = get_app_data_dir() / "config.json"

DEFAULT_MODEL_CONFIGS = [
    {
        "name": "DeepSeek V4 Pro",
        "api_key": "",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-v4-pro",
        "system_prompt": "You are a helpful assistant.",
        "context_length": 1000000,
        "compact_threshold": 600000,
        "use_full_url": False,
    },
    {
        "name": "DeepSeek V4 Flash",
        "api_key": "",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-v4-flash",
        "system_prompt": "You are a helpful assistant.",
        "context_length": 1000000,
        "compact_threshold": 600000,
        "use_full_url": False,
    },
    {
        "name": "DeepSeek V3.2",
        "api_key": "",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "system_prompt": "You are a helpful assistant.",
        "context_length": 128000,
        "compact_threshold": 80000,
        "use_full_url": False,
    },
    {
        "name": "OpenAI",
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "system_prompt": "You are a helpful assistant.",
        "context_length": 128000,
        "compact_threshold": 80000,
        "use_full_url": False,
    },
    {
        "name": "本地 Ollama",
        "api_key": "ollama",
        "base_url": "https://ollama.api.com/v1",
        "model": "llama3",
        "system_prompt": "You are a helpful assistant.",
        "context_length": 128000,
        "compact_threshold": 80000,
        "use_full_url": False,
    },
]

DEFAULT_CONFIG = {
    "model_configs": DEFAULT_MODEL_CONFIGS,
    "active_model_config": "DeepSeek 官方",
    "tavily_api_key": "",
    "search_engine": "tavily",         # tavily | brave | firecrawl | duckduckgo | google | searxng
    "search_fallback": True,           # 失败时自动降级到其他引擎
    "bing_api_key": "",                # 已停用，保留兼容
    "brave_api_key": "",
    "firecrawl_api_key": "",
    "google_api_key": "",
    "google_cx": "",                   # Google Custom Search Engine ID
    "searxng_url": "",                 # 如 http://localhost:8888
    "command_safety": "confirm",   # confirm | auto | disabled
    "command_timeout": 30,
    "max_rounds": 50,
    "theme": "dark",               # dark | light | system
    "font_size": 13,
    "sidebar_width": 220,
    "vision_api_key": "",
    "vision_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "vision_model": "qwen-vl-max",
    "imagegen_api_key": "",
    "imagegen_base_url": "",
    "imagegen_use_full_url": False,
    "imagegen_model": "gpt-image-2",
    "imagegen_format": "openai",  # openai | dashscope
    "thinking": "high",             # off | high | max
    "search_mode": "auto",         # auto | manual
    "search_enabled": True,        # manual mode: whether search tool is active
    "sync_folder": "",             # 云同步文件夹路径（如坚果云同步目录）
    "sync_auto_upload": True,      # 对话保存时自动上传到同步文件夹
    "recent_projects": [],         # 最近使用的项目目录 [{path, name, last_used}]，倒序，上限 ~12
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 补全缺失的顶层 key
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_active_model_config(config: dict) -> Optional[dict]:
    name = config.get("active_model_config")
    for mc in config.get("model_configs", []):
        if mc["name"] == name:
            return mc
    configs = config.get("model_configs", [])
    return configs[0] if configs else None


def get_allowed_commands_path() -> Path:
    return get_app_data_dir() / "allowed_commands.json"


def load_allowed_commands() -> list:
    p = get_allowed_commands_path()
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_allowed_commands(commands: list) -> None:
    with open(get_allowed_commands_path(), "w", encoding="utf-8") as f:
        json.dump(commands, f, ensure_ascii=False, indent=2)


def is_command_allowed(command: str) -> bool:
    import fnmatch
    cmd = command.strip()
    for pattern in load_allowed_commands():
        if fnmatch.fnmatch(cmd, pattern) or cmd == pattern:
            return True
    return False


def add_allowed_command(command: str) -> None:
    cmds = load_allowed_commands()
    cmd = command.strip()
    if cmd and cmd not in cmds:
        cmds.append(cmd)
        save_allowed_commands(cmds)
