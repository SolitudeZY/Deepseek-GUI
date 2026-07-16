import unittest
from unittest.mock import patch

from app.agent import Agent
from app.conversation import export_conversation_md


def responses_config(model="gpt-test"):
    return {
        "name": "Responses",
        "api_key": "secret",
        "base_url": "https://provider.example/v1",
        "model": model,
        "api_protocol": "openai_responses",
        "provider_profile": "generic",
        "auth_mode": "api_key",
        "responses_server_state": True,
    }


class ResponsesStateTests(unittest.TestCase):
    def test_agent_rejects_state_with_different_fingerprint(self):
        adapter = type("Adapter", (), {
            "config": type("Config", (), {"base_url": "https://provider.example/v1"})(),
        })()
        with patch("app.agent.create_model_adapter", return_value=adapter):
            agent = Agent(
                api_key="secret", base_url="https://provider.example/v1", model="gpt-test",
                model_config=responses_config(),
                provider_state={"response_id": "resp_old", "config_fingerprint": "sha256:wrong"},
            )
        self.assertEqual(agent.provider_state, {})

    def test_incremental_suffix_and_export_exclude_provider_state(self):
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "new"},
        ]
        self.assertEqual(Agent._messages_after_latest_assistant(messages), [messages[-1]])
        conv = {
            "title": "State test",
            "messages": messages[1:],
            "provider_state": {"openai_responses": {
                "response_id": "resp_secretish",
                "config_fingerprint": "sha256:value",
                "updated_at": "now",
            }},
        }
        exported = export_conversation_md(conv)
        self.assertNotIn("resp_secretish", exported)
        self.assertNotIn("provider_state", exported)


if __name__ == "__main__":
    unittest.main()
