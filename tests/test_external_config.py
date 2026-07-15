import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.external_config import (
    discover_external_mcp_configs,
    discover_external_model_configs,
    import_external_mcp_configs,
    import_external_model_configs,
)
from app import external_config
from app.webview_app import API


class ExternalConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.project = self.root / "project"
        self.home.mkdir()
        self.project.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_toml_backend_uses_stdlib_when_available(self):
        expected = "tomllib" if sys.version_info >= (3, 11) else "tomli"
        self.assertEqual(external_config._toml.__name__, expected)

    @staticmethod
    def _write_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _write_text(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def test_mcp_discovery_precedence_mapping_and_secret_safe_summary(self):
        self._write_json(self.home / ".claude.json", {
            "mcpServers": {
                "files": {
                    "type": "stdio",
                    "command": "global-secret-command",
                    "args": ["global-secret-arg"],
                    "env": {"TOKEN": "claude-secret"},
                }
            },
            "projects": {
                str(self.project): {
                    "mcpServers": {
                        "project-only": {
                            "command": "project-command",
                            "args": ["--serve"],
                        }
                    }
                }
            },
        })
        self._write_json(self.project / ".mcp.json", {
            "mcpServers": {
                "files": {
                    "command": "project-command",
                    "args": ["project-arg"],
                    "env": {"TOKEN": "project-secret"},
                }
            }
        })
        self._write_text(self.home / ".codex" / "config.toml", """
[mcp_servers.remote]
url = "https://example.test/mcp"
bearer_token_env_var = "REMOTE_TOKEN"
env_http_headers = { X-Api-Key = "REMOTE_KEY" }
startup_timeout_sec = 12
tool_timeout_sec = 34

[mcp_servers.restricted]
command = "restricted-command"
disabled_tools = ["write"]
""")

        discovered = discover_external_mcp_configs(str(self.project), self.home)
        rendered = json.dumps(discovered, ensure_ascii=False)
        for secret in ("claude-secret", "project-secret", "global-secret-command", "project-arg"):
            self.assertNotIn(secret, rendered)

        candidates = {item["name"]: item for item in discovered["candidates"]}
        self.assertEqual(candidates["files"]["source_label"], "Claude 当前项目 .mcp.json")
        self.assertEqual(candidates["remote"]["transport"], "http")

        selected = [candidates[name]["id"] for name in ("files", "remote", "restricted")]
        imported = import_external_mcp_configs(selected, str(self.project), self.home)
        configs = {item["config"]["name"]: item["config"] for item in imported["items"]}
        self.assertEqual(configs["files"]["stdio"]["command"], "project-command")
        self.assertEqual(configs["files"]["stdio"]["env"]["TOKEN"], "project-secret")
        self.assertEqual(configs["remote"]["http"]["headers"]["Authorization"], "Bearer ${REMOTE_TOKEN}")
        self.assertEqual(configs["remote"]["http"]["headers"]["X-Api-Key"], "${REMOTE_KEY}")
        self.assertEqual(configs["remote"]["connect_timeout"], 12)
        self.assertEqual(configs["remote"]["call_timeout"], 34)
        self.assertFalse(configs["restricted"]["enabled"])
        self.assertFalse(any(config["trusted"] for config in configs.values()))

    def test_mcp_ids_are_deterministic_and_malformed_source_isolated(self):
        self._write_json(self.home / ".claude.json", {
            "mcpServers": {"demo": {"command": "python", "args": []}}
        })
        first = discover_external_mcp_configs("", self.home)
        second = discover_external_mcp_configs("", self.home)
        self.assertEqual(first["candidates"][0]["id"], second["candidates"][0]["id"])

        self._write_text(self.project / ".codex" / "config.toml", 'token = "do-not-echo"\ninvalid = [')
        result = discover_external_mcp_configs(str(self.project), self.home)
        rendered = json.dumps(result, ensure_ascii=False)
        self.assertIn("demo", rendered)
        self.assertIn("TOML 配置格式无效", rendered)
        self.assertNotIn("do-not-echo", rendered)

    def test_model_discovery_masks_secrets_and_selected_import_copies_api_keys(self):
        self._write_json(self.home / ".claude" / "settings.json", {
            "env": {
                "ANTHROPIC_AUTH_TOKEN": "claude-model-secret",
                "ANTHROPIC_BASE_URL": "https://user:password@claude.example/v1?token=query-secret",
                "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-test",
            }
        })
        self._write_text(self.home / ".codex" / "config.toml", """
model = "gpt-test"
model_provider = "custom"

[model_providers.custom]
name = "Custom Provider"
base_url = "https://codex.example/v1"
wire_api = "chat"
requires_openai_auth = true
""")
        self._write_json(self.home / ".codex" / "auth.json", {
            "OPENAI_API_KEY": "codex-api-secret",
            "tokens": {
                "access_token": "oauth-access-secret",
                "refresh_token": "oauth-refresh-secret",
            },
        })

        discovered = discover_external_model_configs("", self.home)
        rendered = json.dumps(discovered, ensure_ascii=False)
        for secret in (
            "claude-model-secret", "codex-api-secret", "oauth-access-secret",
            "oauth-refresh-secret", "password", "query-secret",
        ):
            self.assertNotIn(secret, rendered)
        self.assertIn("https://claude.example/v1", rendered)
        self.assertTrue(all(item["has_api_key"] for item in discovered["candidates"]))

        selected = [item["id"] for item in discovered["candidates"]]
        imported = import_external_model_configs(selected, "", self.home)
        configs = {item["config"]["name"]: item["config"] for item in imported["items"]}
        claude = next(config for name, config in configs.items() if name.startswith("Claude"))
        codex = next(config for name, config in configs.items() if name.startswith("Codex"))
        self.assertEqual(claude["api_key"], "claude-model-secret")
        self.assertEqual(codex["api_key"], "codex-api-secret")
        imported_text = json.dumps(imported, ensure_ascii=False)
        self.assertNotIn("oauth-access-secret", imported_text)
        self.assertNotIn("oauth-refresh-secret", imported_text)

    def test_codex_env_key_is_used_without_exposing_value_in_discovery(self):
        self._write_text(self.home / ".codex" / "config.toml", """
model = "env-model"
model_provider = "env-provider"

[model_providers.env-provider]
base_url = "https://env.example/v1"
wire_api = "responses"
env_key = "LOCAL_PROVIDER_KEY"
""")
        with patch.dict(os.environ, {"LOCAL_PROVIDER_KEY": "environment-secret"}, clear=False):
            discovered = discover_external_model_configs("", self.home)
            self.assertNotIn("environment-secret", json.dumps(discovered, ensure_ascii=False))
            candidate = discovered["candidates"][0]
            self.assertEqual(candidate["protocol"], "openai_responses")
            imported = import_external_model_configs([candidate["id"]], "", self.home)
        self.assertEqual(imported["items"][0]["config"]["api_key"], "environment-secret")

    def test_unrelated_project_settings_do_not_change_model_source_labels(self):
        self._write_json(self.home / ".claude" / "settings.json", {
            "env": {"ANTHROPIC_MODEL": "global-claude-model"}
        })
        self._write_json(self.project / ".claude" / "settings.json", {
            "permissions": {"allow": ["Read"]}
        })
        self._write_text(self.home / ".codex" / "config.toml", """
model = "global-codex-model"
model_provider = "global-provider"

[model_providers.global-provider]
base_url = "https://global.example/v1"
wire_api = "chat"
""")
        self._write_text(self.project / ".codex" / "config.toml", """
[model_providers.unused-provider]
base_url = "https://unused.example/v1"
""")

        discovered = discover_external_model_configs(str(self.project), self.home)
        by_source = {item["source"]: item for item in discovered["candidates"]}
        self.assertEqual(by_source["claude"]["source_label"], "Claude 全局 settings.json")
        self.assertEqual(by_source["codex"]["source_label"], "Codex 全局 config.toml")

    def test_webview_bridge_forwards_selection_and_project_path(self):
        api = API.__new__(API)
        project_path = str(self.project)
        with patch("app.webview_app.discover_external_mcp_configs", return_value={"candidates": []}) as discover_mcp, \
                patch("app.webview_app.import_external_mcp_configs", return_value={"items": []}) as import_mcp, \
                patch("app.webview_app.discover_external_model_configs", return_value={"candidates": []}) as discover_models, \
                patch("app.webview_app.import_external_model_configs", return_value={"items": []}) as import_models:
            self.assertEqual(api.discover_external_mcp_configs(project_path), {"candidates": []})
            self.assertEqual(api.import_external_mcp_configs(["mcp-id"], project_path), {"items": []})
            self.assertEqual(api.discover_external_model_configs(project_path), {"candidates": []})
            self.assertEqual(api.import_external_model_configs(["model-id"], project_path), {"items": []})

        discover_mcp.assert_called_once_with(project_path)
        import_mcp.assert_called_once_with(["mcp-id"], project_path)
        discover_models.assert_called_once_with(project_path)
        import_models.assert_called_once_with(["model-id"], project_path)


if __name__ == "__main__":
    unittest.main()
