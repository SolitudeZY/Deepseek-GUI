import unittest
import time
from tempfile import TemporaryDirectory
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

    def test_summarizer_has_hard_timeout(self):
        def slow_complete(*args, **kwargs):
            time.sleep(0.2)
            return "late"

        started = time.monotonic()
        with patch("app.model_protocol.complete_text", side_effect=slow_complete):
            with self.assertRaises(TimeoutError):
                advanced_tools._summarize_text(
                    MODEL_CONFIG, "source", timeout_seconds=0.03,
                )
        self.assertLess(time.monotonic() - started, 0.15)

    def test_auto_compact_shrinks_large_recent_tail_and_reports_success(self):
        messages = [{"role": "system", "content": "system"}]
        messages.extend(
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 4000}
            for i in range(8)
        )
        statuses = []
        with TemporaryDirectory() as temp_dir:
            with patch("app.advanced_tools.get_app_data_dir", return_value=Path(temp_dir)):
                with patch("app.advanced_tools._summarize_text", return_value="summary"):
                    compacted = advanced_tools.auto_compact(
                        messages,
                        MODEL_CONFIG,
                        target_tokens=1000,
                        on_status=lambda state, detail="": statuses.append((state, detail)),
                    )
        self.assertIsNot(compacted, messages)
        self.assertLess(len(compacted), len(messages))
        self.assertEqual(statuses[-1][0], "completed")

    def test_auto_compact_reports_failure_and_preserves_messages(self):
        messages = [{"role": "system", "content": "system"}] + [
            {"role": "user", "content": "x" * 4000},
            {"role": "assistant", "content": "latest"},
        ]
        statuses = []
        with TemporaryDirectory() as temp_dir:
            with patch("app.advanced_tools.get_app_data_dir", return_value=Path(temp_dir)):
                with patch("app.advanced_tools._summarize_text", side_effect=TimeoutError("slow")):
                    compacted = advanced_tools.auto_compact(
                        messages,
                        MODEL_CONFIG,
                        target_tokens=100,
                        on_status=lambda state, detail="": statuses.append((state, detail)),
                    )
        self.assertIs(compacted, messages)
        self.assertEqual(statuses[-1], ("failed", "slow"))

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

    def test_subagent_complete_task_returns_without_waiting_for_round_limit(self):
        calls = []

        def stream_round(messages, tools, **kwargs):
            calls.append(messages)
            return SimpleNamespace(
                tool_calls=[{
                    "id": "done-1",
                    "function": {
                        "name": "complete_task",
                        "arguments": '{"summary":"analysis complete"}',
                    },
                }],
                assistant_message={"role": "assistant", "content": ""},
            )

        adapter = SimpleNamespace(stream_round=stream_round, complete_text=lambda messages: "unexpected")
        with patch("app.model_protocol.create_model_adapter", return_value=adapter):
            result = advanced_tools.run_subagent("inspect", MODEL_CONFIG)

        self.assertEqual(result, "analysis complete")
        self.assertEqual(len(calls), 1)

    def test_subagent_repeated_tool_calls_force_early_summary(self):
        stream_calls = []
        summary_calls = []

        def stream_round(messages, tools, **kwargs):
            stream_calls.append(messages)
            return SimpleNamespace(
                tool_calls=[{
                    "id": f"read-{len(stream_calls)}",
                    "function": {"name": "read_file", "arguments": '{"path":"same.txt"}'},
                }],
                assistant_message={"role": "assistant", "content": ""},
            )

        def complete_text(messages):
            summary_calls.append(messages)
            return "forced summary"

        adapter = SimpleNamespace(stream_round=stream_round, complete_text=complete_text)
        with patch("app.model_protocol.create_model_adapter", return_value=adapter), \
                patch("app.tools.read_file", return_value="content") as read_file:
            result = advanced_tools.run_subagent("inspect", MODEL_CONFIG)

        self.assertEqual(result, "forced summary")
        self.assertEqual(read_file.call_count, 1)
        self.assertEqual(len(stream_calls), 4)
        self.assertEqual(len(summary_calls), 1)

    def test_subagent_unique_calls_stop_at_independent_round_budget(self):
        stream_calls = []

        def stream_round(messages, tools, **kwargs):
            stream_calls.append(messages)
            index = len(stream_calls)
            return SimpleNamespace(
                tool_calls=[{
                    "id": f"read-{index}",
                    "function": {"name": "read_file", "arguments": f'{{"path":"file-{index}.txt"}}'},
                }],
                assistant_message={"role": "assistant", "content": ""},
            )

        adapter = SimpleNamespace(
            stream_round=stream_round,
            complete_text=lambda messages: "budget summary",
        )
        with patch("app.model_protocol.create_model_adapter", return_value=adapter), \
                patch("app.tools.read_file", return_value="content"), \
                patch.object(advanced_tools, "SUBAGENT_MAX_ROUNDS", 3):
            result = advanced_tools.run_subagent("inspect", MODEL_CONFIG)

        self.assertIn("budget summary", result)
        self.assertEqual(len(stream_calls), 3)

    def test_subagent_empty_forced_summary_returns_collected_evidence(self):
        summary_messages = []

        def stream_round(messages, tools, **kwargs):
            return SimpleNamespace(
                tool_calls=[{
                    "id": "read-1",
                    "function": {"name": "read_file", "arguments": '{"path":"app/config.py"}'},
                }],
                assistant_message={"role": "assistant", "content": "checking version"},
            )

        def complete_text(messages):
            summary_messages.extend(messages)
            return ""

        adapter = SimpleNamespace(stream_round=stream_round, complete_text=complete_text)
        with patch("app.model_protocol.create_model_adapter", return_value=adapter), \
                patch("app.tools.read_file", return_value='APP_VERSION = "1.9.10"'), \
                patch.object(advanced_tools, "SUBAGENT_MAX_ROUNDS", 1):
            result = advanced_tools.run_subagent("find version", MODEL_CONFIG, cwd="E:/repo")

        self.assertIn('APP_VERSION = "1.9.10"', result)
        self.assertIn("app/config.py", result)
        self.assertNotIn("未返回摘要", result)
        self.assertEqual([message["role"] for message in summary_messages], ["system", "user"])
        self.assertTrue(all("tool_calls" not in message for message in summary_messages))

    def test_agent_reuses_duplicate_subagent_result_within_run(self):
        agent = object.__new__(Agent)
        agent.model_config = dict(MODEL_CONFIG)
        agent.project_path = "E:/repo"
        agent._subagent_results = {}
        args = {"prompt": "inspect module", "agent_type": "Explore"}

        with patch("app.agent.run_subagent", return_value="first result") as run_subagent:
            first = agent._handle_subagent(args)
            second = agent._handle_subagent(args)

        self.assertEqual(first, "first result")
        self.assertIn("first result", second)
        self.assertEqual(run_subagent.call_count, 1)
        self.assertEqual(run_subagent.call_args.kwargs["cwd"], "E:/repo")

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
