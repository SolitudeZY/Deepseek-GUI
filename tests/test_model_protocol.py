import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from app.model_protocol import (
    AnthropicMessagesAdapter,
    OpenAIChatAdapter,
    OpenAIResponsesAdapter,
    ProviderCapabilityError,
    ProviderRequestError,
    _anthropic_messages,
    _responses_input,
    create_model_adapter,
    model_config_fingerprint,
    normalize_base_url,
)


def config(protocol="openai_chat", profile="generic", **overrides):
    result = {
        "name": "Test model",
        "api_key": "sentinel-secret-key",
        "base_url": "https://provider.example/v1",
        "model": "test-model",
        "api_protocol": protocol,
        "provider_profile": profile,
        "auth_mode": "api_key",
        "responses_server_state": False,
    }
    result.update(overrides)
    return result


class FakeStream:
    def __init__(self, events, final_error=None):
        self.events = list(events)
        self.final_error = final_error
        self.closed = False

    def __iter__(self):
        yield from self.events
        if self.final_error:
            raise self.final_error

    def close(self):
        self.closed = True


class FakeCreate:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def chat_client(*results):
    create = FakeCreate(*results)
    return NS(chat=NS(completions=create)), create


def responses_client(*results):
    create = FakeCreate(*results)
    return NS(responses=create), create


def anthropic_client(*results):
    create = FakeCreate(*results)
    return NS(messages=create), create


TOOLS = [{
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a file",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}]


class ConfigurationTests(unittest.TestCase):
    def test_root_and_complete_endpoint_normalize_to_same_sdk_base_url(self):
        cases = [
            (
                "openai_chat",
                "https://provider.example/v1",
                "https://provider.example/v1/chat/completions/",
            ),
            (
                "openai_responses",
                "https://provider.example/v1",
                "https://provider.example/v1/responses",
            ),
            (
                "anthropic_messages",
                "https://provider.example",
                "https://provider.example/v1/messages",
            ),
        ]
        for protocol, root, endpoint in cases:
            with self.subTest(protocol=protocol):
                self.assertEqual(normalize_base_url(root, protocol), root)
                self.assertEqual(normalize_base_url(endpoint, protocol), root)
        self.assertEqual(
            normalize_base_url("https://provider.example/v1", "anthropic_messages"),
            "https://provider.example",
        )

    def test_legacy_full_url_flag_no_longer_changes_url_semantics(self):
        endpoint = "https://provider.example/v1/chat/completions"
        self.assertEqual(
            normalize_base_url(endpoint, "openai_chat", use_full_url=True),
            "https://provider.example/v1",
        )

    def test_adapter_factory_and_profile_protocol_validation(self):
        self.assertIsInstance(create_model_adapter(config()), OpenAIChatAdapter)
        self.assertIsInstance(
            create_model_adapter(config("openai_responses")), OpenAIResponsesAdapter
        )
        self.assertIsInstance(
            create_model_adapter(config("anthropic_messages")), AnthropicMessagesAdapter
        )
        normalized = create_model_adapter(config("anthropic_messages", "deepseek"))
        self.assertIsInstance(normalized, AnthropicMessagesAdapter)
        self.assertEqual(normalized.config.provider_profile, "generic")

    def test_fingerprint_excludes_secrets_and_tracks_semantics(self):
        first = config(api_key="first-secret")
        second = config(api_key="second-secret")
        self.assertEqual(model_config_fingerprint(first), model_config_fingerprint(second))
        second["model"] = "different-model"
        self.assertNotEqual(model_config_fingerprint(first), model_config_fingerprint(second))


class ChatAdapterTests(unittest.TestCase):
    def test_stream_normalizes_text_reasoning_tools_and_usage(self):
        events = [
            NS(choices=[NS(delta=NS(content=None, reasoning_content="think ", tool_calls=None))], usage=None),
            NS(choices=[NS(delta=NS(content="hello", reasoning_content=None, tool_calls=None))], usage=None),
            NS(choices=[NS(delta=NS(content=None, reasoning_content=None, tool_calls=[
                NS(index=0, id="call_", function=NS(name="read_", arguments='{"pa')),
            ]))], usage=None),
            NS(choices=[NS(delta=NS(content=None, reasoning_content=None, tool_calls=[
                NS(index=0, id="1", function=NS(name="file", arguments='th":"a"}')),
            ]))], usage=None),
            NS(choices=[], usage=NS(prompt_tokens=12, completion_tokens=4)),
        ]
        client, create = chat_client(FakeStream(events))
        text_deltas, thinking_deltas = [], []
        result = OpenAIChatAdapter(config(), client).stream_round(
            [{"role": "user", "content": "hi"}], TOOLS, thinking="high",
            on_text=text_deltas.append, on_thinking=thinking_deltas.append,
        )
        self.assertEqual(result.assistant_message["content"], "hello")
        self.assertEqual(result.assistant_message["reasoning_content"], "think ")
        self.assertEqual(result.tool_calls[0]["id"], "call_1")
        self.assertEqual(result.tool_calls[0]["function"]["name"], "read_file")
        self.assertEqual(json.loads(result.tool_calls[0]["function"]["arguments"]), {"path": "a"})
        self.assertEqual(result.usage.prompt_tokens, 12)
        self.assertEqual(result.usage.completion_tokens, 4)
        self.assertEqual(text_deltas, ["hello"])
        self.assertEqual(thinking_deltas, ["think "])
        self.assertEqual(create.calls[0]["reasoning_effort"], "high")

    def test_provider_private_options_are_isolated(self):
        expected = {
            "generic": {"reasoning_effort": "high"},
            "deepseek": {
                "reasoning_effort": "high",
                "extra_body": {"thinking": {"type": "enabled"}},
            },
            "qwen": {"extra_body": {"enable_thinking": True}},
            "glm": {"extra_body": {"thinking": {"type": "enabled"}}},
        }
        for profile, options in expected.items():
            with self.subTest(profile=profile):
                adapter = OpenAIChatAdapter(config(profile=profile), NS())
                self.assertEqual(adapter._request_options("high"), options)
                self.assertEqual(adapter._request_options("off"), {})

    def test_explicit_tool_rejection_retries_once_without_tools(self):
        failure = RuntimeError("invalid_request: tools are not supported")
        success = FakeStream([NS(choices=[NS(delta=NS(
            content="fallback", reasoning_content=None, tool_calls=None,
        ))], usage=None)])
        client, create = chat_client(failure, success)
        result = OpenAIChatAdapter(config(), client).stream_round(
            [{"role": "user", "content": "hi"}], TOOLS
        )
        self.assertEqual(result.assistant_message["content"], "fallback")
        self.assertTrue(result.downgrade_notice)
        self.assertEqual(len(create.calls), 2)
        self.assertIn("tools", create.calls[0])
        self.assertNotIn("tools", create.calls[1])

    def test_tool_required_and_partial_stream_never_fallback(self):
        failure = RuntimeError("tools are not supported")
        client, create = chat_client(failure)
        with self.assertRaises(ProviderCapabilityError):
            OpenAIChatAdapter(config(), client).stream_round(
                [{"role": "user", "content": "hi"}], TOOLS, tools_required=True
            )
        self.assertEqual(len(create.calls), 1)

        partial = FakeStream([
            NS(choices=[NS(delta=NS(content="partial", reasoning_content=None, tool_calls=None))], usage=None)
        ], final_error=failure)
        client, create = chat_client(partial)
        with self.assertRaises(ProviderRequestError):
            OpenAIChatAdapter(config(), client).stream_round(
                [{"role": "user", "content": "hi"}], TOOLS
            )
        self.assertEqual(len(create.calls), 1)

    def test_errors_redact_credentials(self):
        client, _ = chat_client(RuntimeError("bad sentinel-secret-key Authorization: bearer-value"))
        with self.assertRaises(ProviderRequestError) as raised:
            OpenAIChatAdapter(config(), client).stream_round([{"role": "user", "content": "hi"}])
        rendered = str(raised.exception)
        self.assertNotIn("sentinel-secret-key", rendered)
        self.assertNotIn("bearer-value", rendered)


class ResponsesAdapterTests(unittest.TestCase):
    def test_codex_client_profile_sets_explicit_compatibility_headers(self):
        fake = NS(responses=NS(create=lambda **kwargs: FakeStream([])))
        with patch("openai.OpenAI", return_value=fake) as constructor:
            adapter = OpenAIResponsesAdapter(config(
                "openai_responses", client_profile="codex"
            ))
            self.assertIs(adapter._get_client(), fake)
        headers = constructor.call_args.kwargs["default_headers"]
        self.assertEqual(headers["originator"], "Codex Desktop")
        self.assertTrue(headers["User-Agent"].startswith("Codex Desktop/"))
        self.assertEqual(headers["Accept"], "text/event-stream")
        self.assertNotIn("sentinel-secret-key", json.dumps(headers))

    def test_message_conversion_and_streamed_tool_round(self):
        instructions, items = _responses_input([
            {"role": "system", "content": "system"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"a"}'},
            }]},
            {"role": "tool", "tool_call_id": "call_1", "content": "result"},
        ])
        self.assertEqual(instructions, "system")
        self.assertEqual(items[-2]["type"], "function_call")
        self.assertEqual(items[-1]["type"], "function_call_output")

        output_call = NS(
            type="function_call", id="fc_1", call_id="call_1",
            name="read_file", arguments='{"path":"a"}',
        )
        response = NS(
            id="resp_1", output=[output_call],
            usage=NS(input_tokens=20, output_tokens=5, input_tokens_details=NS(cached_tokens=3)),
        )
        events = [
            NS(type="response.output_text.delta", delta="hello"),
            NS(type="response.output_item.added", output_index=0, item=output_call),
            NS(type="response.function_call_arguments.done", output_index=0,
               item_id="fc_1", name="read_file", arguments='{"path":"a"}'),
            NS(type="response.completed", response=response),
        ]
        client, create = responses_client(FakeStream(events))
        cfg = config("openai_responses", responses_server_state=True)
        result = OpenAIResponsesAdapter(cfg, client).stream_round(
            [{"role": "system", "content": "system"}, {"role": "user", "content": "hi"}], TOOLS
        )
        self.assertEqual(result.assistant_message["content"], "hello")
        self.assertEqual(result.tool_calls[0]["id"], "call_1")
        self.assertEqual(result.usage.cache_hit_tokens, 3)
        self.assertEqual(result.provider_state_update.response_id, "resp_1")
        self.assertTrue(create.calls[0]["store"])
        self.assertEqual(create.calls[0]["tools"][0]["name"], "read_file")
        self.assertNotIn("function", create.calls[0]["tools"][0])

    def test_previous_response_uses_incremental_input_and_stale_id_rebuilds(self):
        stale = RuntimeError("previous_response_id not found")
        completed = NS(type="response.completed", response=NS(
            id="resp_new", output=[], usage=NS(input_tokens=2, output_tokens=1),
        ))
        client, create = responses_client(stale, FakeStream([completed]))
        cfg = config("openai_responses", responses_server_state=True)
        full = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old answer"},
            {"role": "user", "content": "new"},
        ]
        result = OpenAIResponsesAdapter(cfg, client).stream_round(
            full,
            previous_response_id="resp_old",
            incremental_messages=[{"role": "user", "content": "new"}],
        )
        self.assertEqual(create.calls[0]["input"], [{"role": "user", "content": "new"}])
        self.assertEqual(create.calls[0]["previous_response_id"], "resp_old")
        self.assertNotIn("previous_response_id", create.calls[1])
        self.assertEqual(len(create.calls[1]["input"]), 3)
        self.assertEqual(result.provider_state_update.response_id, "resp_new")

    def test_one_shot_completion_is_stateless_even_when_model_toggle_is_on(self):
        completed = NS(type="response.completed", response=NS(
            id="resp_unused", output=[], usage=NS(input_tokens=1, output_tokens=1),
        ))
        client, create = responses_client(FakeStream([
            NS(type="response.output_text.delta", delta="ok"), completed,
        ]))
        cfg = config("openai_responses", responses_server_state=True)
        text = OpenAIResponsesAdapter(cfg, client).complete_text([
            {"role": "user", "content": "short"},
        ])
        self.assertEqual(text, "ok")
        self.assertFalse(create.calls[0]["store"])


class AnthropicAdapterTests(unittest.TestCase):
    def test_history_conversion_streaming_tools_thinking_and_usage(self):
        system, messages = _anthropic_messages([
            {"role": "system", "content": "system"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": "tool_1", "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"a"}'},
            }]},
            {"role": "tool", "tool_call_id": "tool_1", "content": "result"},
        ])
        self.assertEqual(system, "system")
        self.assertEqual(messages[1]["content"][0]["type"], "tool_use")
        self.assertEqual(messages[2]["content"][0]["type"], "tool_result")

        events = [
            NS(type="message_start", message=NS(usage=NS(
                input_tokens=30, output_tokens=0,
                cache_read_input_tokens=7, cache_creation_input_tokens=2,
            ))),
            NS(type="content_block_delta", index=0, delta=NS(type="thinking_delta", thinking="think")),
            NS(type="content_block_delta", index=1, delta=NS(type="text_delta", text="hello")),
            NS(type="content_block_start", index=2, content_block=NS(
                type="tool_use", id="tool_2", name="read_file", input={},
            )),
            NS(type="content_block_delta", index=2, delta=NS(
                type="input_json_delta", partial_json='{"path":"b"}',
            )),
            NS(type="message_delta", usage=NS(output_tokens=9)),
        ]
        client, create = anthropic_client(FakeStream(events))
        result = AnthropicMessagesAdapter(config("anthropic_messages"), client).stream_round(
            [{"role": "system", "content": "system"}, {"role": "user", "content": "hi"}],
            TOOLS, thinking="high",
        )
        self.assertEqual(result.assistant_message["content"], "hello")
        self.assertEqual(result.assistant_message["reasoning_content"], "think")
        self.assertEqual(json.loads(result.tool_calls[0]["function"]["arguments"]), {"path": "b"})
        self.assertEqual(result.usage.prompt_tokens, 30)
        self.assertEqual(result.usage.completion_tokens, 9)
        self.assertEqual(result.usage.cache_hit_tokens, 7)
        self.assertEqual(create.calls[0]["tools"][0]["input_schema"]["type"], "object")
        self.assertEqual(create.calls[0]["thinking"]["budget_tokens"], 8000)
        self.assertGreater(create.calls[0]["max_tokens"], 8000)

    def test_auth_mode_selects_exact_sdk_credential_parameter(self):
        fake = NS(messages=NS(create=lambda **kwargs: FakeStream([])))
        with patch("anthropic.Anthropic", return_value=fake) as constructor:
            adapter = AnthropicMessagesAdapter(config("anthropic_messages", auth_mode="auth_token"))
            self.assertIs(adapter._get_client(), fake)
        kwargs = constructor.call_args.kwargs
        self.assertEqual(kwargs["auth_token"], "sentinel-secret-key")
        self.assertNotIn("api_key", kwargs)
        self.assertEqual(kwargs["max_retries"], 0)


if __name__ == "__main__":
    unittest.main()
