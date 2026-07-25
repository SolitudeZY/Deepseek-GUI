import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.vision import describe_image


class VisionRequestTests(unittest.TestCase):
    @patch("app.vision._encode_image", return_value=("aW1hZ2U=", "image/png"))
    @patch("openai.OpenAI")
    def test_request_disables_retries_and_bounds_timeout(self, openai_cls, _encode):
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="识别结果"))]
        )
        openai_cls.return_value.chat.completions.create.return_value = completion

        result = describe_image("sample.png", api_key="test-key", timeout=999)

        self.assertEqual(result, "识别结果")
        openai_cls.assert_called_once_with(
            api_key="test-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=300,
            max_retries=0,
        )

    @patch("openai.OpenAI", side_effect=TimeoutError("timed out"))
    def test_timeout_returns_ocr_fallback_hint(self, _openai_cls):
        result = describe_image("sample.png", api_key="test-key", timeout=17)

        self.assertIn("超过 17 秒", result)
        self.assertIn("ocr_image", result)


if __name__ == "__main__":
    unittest.main()
