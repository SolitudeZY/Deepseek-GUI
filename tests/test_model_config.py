import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import config as config_module


class ModelConfigTests(unittest.TestCase):
    def test_legacy_config_migrates_once_and_preserves_values(self):
        legacy = {
            "name": "Legacy DeepSeek",
            "api_key": "secret-value",
            "base_url": "https://api.deepseek.com/v1",
            "model": "custom-model",
            "system_prompt": "keep me",
            "context_length": 123456,
        }
        normalized = config_module.normalize_model_config(legacy)
        self.assertEqual(normalized["api_type"], "deepseek")
        self.assertEqual(normalized["api_protocol"], "openai_chat")
        self.assertEqual(normalized["provider_profile"], "deepseek")
        self.assertEqual(normalized["auth_mode"], "api_key")
        self.assertEqual(normalized["client_profile"], "generic")
        self.assertFalse(normalized["responses_server_state"])
        self.assertEqual(normalized["api_key"], "secret-value")
        self.assertEqual(normalized["system_prompt"], "keep me")
        self.assertEqual(normalized["context_length"], 123456)
        self.assertNotIn("use_full_url", normalized)
        self.assertEqual(config_module.normalize_model_config(normalized), normalized)
        self.assertNotIn("api_protocol", legacy)

    def test_existing_profile_is_authoritative_and_invalid_values_are_safe(self):
        config = {
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_protocol": "unknown",
            "provider_profile": "generic",
            "auth_mode": "unknown",
            "client_profile": "unknown",
            "responses_server_state": "true",
        }
        normalized = config_module.normalize_model_config(config)
        self.assertEqual(normalized["api_type"], "openai_chat")
        self.assertEqual(normalized["api_protocol"], "openai_chat")
        self.assertEqual(normalized["provider_profile"], "generic")
        self.assertEqual(normalized["auth_mode"], "api_key")
        self.assertEqual(normalized["client_profile"], "generic")
        self.assertFalse(normalized["responses_server_state"])

    def test_single_api_type_controls_internal_compatibility_fields(self):
        cases = {
            "openai_chat": ("openai_chat", "generic", "generic"),
            "openai_responses": ("openai_responses", "generic", "generic"),
            "anthropic": ("anthropic_messages", "generic", "generic"),
            "deepseek": ("openai_chat", "deepseek", "generic"),
            "qwen": ("openai_chat", "qwen", "generic"),
            "glm": ("openai_chat", "glm", "generic"),
            "codex_chat": ("openai_chat", "generic", "codex"),
            "codex_responses": ("openai_responses", "generic", "codex"),
        }
        for api_type, expected in cases.items():
            with self.subTest(api_type=api_type):
                normalized = config_module.normalize_model_config({
                    "api_type": api_type,
                    "base_url": "https://proxy.example/v1",
                    "model": "custom-model",
                    "provider_profile": "deepseek",
                    "client_profile": "codex",
                })
                self.assertEqual(
                    (
                        normalized["api_protocol"],
                        normalized["provider_profile"],
                        normalized["client_profile"],
                    ),
                    expected,
                )

    def test_legacy_protocol_combinations_migrate_to_api_type(self):
        cases = [
            ({"api_protocol": "anthropic_messages"}, "anthropic"),
            ({"api_protocol": "openai_responses"}, "openai_responses"),
            ({"api_protocol": "openai_responses", "client_profile": "codex"}, "codex_responses"),
            ({"api_protocol": "openai_chat", "client_profile": "codex"}, "codex_chat"),
            ({"api_protocol": "openai_chat", "provider_profile": "qwen"}, "qwen"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(config_module.normalize_model_config(raw)["api_type"], expected)

    def test_official_profile_migration_matrix(self):
        cases = [
            ({"base_url": "https://api.deepseek.com/v1"}, "deepseek"),
            ({"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}, "qwen"),
            ({"base_url": "https://open.bigmodel.cn/api/paas/v4"}, "glm"),
            ({"model": "qwen-max"}, "qwen"),
            ({"model": "glm-4.5"}, "glm"),
            ({"base_url": "https://proxy.example/v1", "model": "custom"}, "generic"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(config_module.infer_provider_profile(raw), expected)

    def test_load_persists_migration_without_mutating_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            original_defaults = copy.deepcopy(config_module.DEFAULT_CONFIG)
            path.write_text(json.dumps({
                "model_configs": [{
                    "name": "Old Qwen",
                    "api_key": "key",
                    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "model": "qwen-plus",
                }],
                "active_model_config": "Old Qwen",
            }), encoding="utf-8")
            with patch.object(config_module, "CONFIG_PATH", path):
                first = config_module.load_config()
                second = config_module.load_config()
            self.assertEqual(first, second)
            self.assertEqual(first["active_model_config"], "Old Qwen")
            self.assertEqual(first["model_configs"][0]["api_type"], "qwen")
            self.assertEqual(first["model_configs"][0]["provider_profile"], "qwen")
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["model_configs"][0]["api_protocol"], "openai_chat")
            self.assertEqual(config_module.DEFAULT_CONFIG, original_defaults)

    def test_migration_write_failure_does_not_discard_loaded_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(json.dumps({
                "model_configs": [{"name": "Keep Me", "model": "legacy"}],
                "active_model_config": "Keep Me",
            }), encoding="utf-8")
            with patch.object(config_module, "CONFIG_PATH", path), \
                    patch.object(config_module.json, "dump", side_effect=OSError("read only")):
                loaded = config_module.load_config()
            self.assertEqual(loaded["active_model_config"], "Keep Me")
            self.assertEqual(loaded["model_configs"][0]["name"], "Keep Me")


if __name__ == "__main__":
    unittest.main()
