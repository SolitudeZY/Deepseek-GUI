import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import advanced_tools
from app.agent import Agent


MODEL_CONFIG = {
    "name": "Native",
    "api_key": "key",
    "base_url": "https://provider.example/v1",
    "model": "native-model",
    "api_protocol": "anthropic_messages",
    "provider_profile": "generic",
    "auth_mode": "auth_token",
    "responses_server_state": False,
}


class ModelCallerTests(unittest.TestCase):
    def test_summarizer_passes_complete_model_config(self):
        with patch("app.model_protocol.complete_text", return_value="summary") as complete:
            result = advanced_tools._summarize_text(MODEL_CONFIG, "source")
        self.assertEqual(result, "summary")
        self.assertEqual(complete.call_args.args[0], MODEL_CONFIG)

    def test_rlm_and_subagent_use_adapter_factory(self):
        adapter = SimpleNamespace(
            complete_text=lambda messages: "result",
            stream_round=lambda messages, tools, **kwargs: SimpleNamespace(
                tool_calls=[], assistant_message={"role": "assistant", "content": "sub-result"}
            ),
        )
        with patch("app.model_protocol.create_model_adapter", return_value=adapter) as factory:
            rlm = advanced_tools.run_rlm(["one"], MODEL_CONFIG)
            subagent = advanced_tools.run_subagent("inspect", MODEL_CONFIG)
        self.assertIn("result", rlm)
        self.assertEqual(subagent, "sub-result")
        self.assertTrue(all(call.args[0] == MODEL_CONFIG for call in factory.call_args_list))

    def test_team_spawn_receives_selected_complete_config(self):
        agent = object.__new__(Agent)
        agent.model_config = dict(MODEL_CONFIG)
        agent._model_configs = [dict(MODEL_CONFIG, name="Selected")]
        with patch("app.agent.TEAM.spawn", return_value="started") as spawn:
            result = agent._handle_team_spawn({
                "name": "worker", "role": "review", "prompt": "go", "model_config": "Selected",
            })
        self.assertEqual(result, "started")
        self.assertEqual(spawn.call_args.kwargs["model_config"]["api_protocol"], "anthropic_messages")
        self.assertEqual(spawn.call_args.kwargs["model_config"]["auth_mode"], "auth_token")

    def test_no_model_config_text_caller_bypasses_adapter(self):
        app_dir = Path(__file__).resolve().parents[1] / "app"
        offenders = []
        for path in app_dir.glob("*.py"):
            if path.name in {"model_protocol.py", "vision.py"}:
                continue
            text = path.read_text(encoding="utf-8")
            if "chat.completions.create" in text or ".responses.create(" in text or ".messages.create(" in text:
                offenders.append(path.name)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
