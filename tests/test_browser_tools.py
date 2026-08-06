import unittest
from unittest.mock import patch

from app import browser_tools
from app.tools import CONFIRM_REQUIRED, dispatch


class BrowserToolsTests(unittest.TestCase):
    def test_normalize_url_adds_https(self):
        self.assertEqual(
            browser_tools._normalize_url("example.com/path"),
            "https://example.com/path",
        )

    def test_normalize_url_rejects_non_http_scheme(self):
        with self.assertRaises(ValueError):
            browser_tools._normalize_url("file:///tmp/secret.txt")

    def test_target_ref_accepts_snapshot_formats(self):
        self.assertEqual(browser_tools._target_ref("12"), "12")
        self.assertEqual(browser_tools._target_ref("ref=12"), "12")
        self.assertIsNone(browser_tools._target_ref("button.primary"))

    def test_locator_rejects_ambiguous_selector(self):
        class Locator:
            def count(self):
                return 2

        class Page:
            def locator(self, _selector):
                return Locator()

        with self.assertRaisesRegex(ValueError, "匹配到 2 个元素"):
            browser_tools._BrowserController._locator(Page(), "button")

    def test_open_rejects_unknown_browser_before_worker_call(self):
        with patch.object(browser_tools._controller, "request") as request:
            result = browser_tools.browser_open("https://example.com", "firefox")
        self.assertIn("只支持 edge 或 chrome", result)
        request.assert_not_called()

    def test_dispatch_routes_browser_snapshot(self):
        with patch("app.tools.browser_snapshot", return_value="snapshot") as snapshot:
            self.assertEqual(dispatch("browser_snapshot", {}), "snapshot")
        snapshot.assert_called_once_with()

    def test_browser_mutations_require_confirmation(self):
        self.assertTrue(
            {"browser_open", "browser_click", "browser_type"}.issubset(
                CONFIRM_REQUIRED
            )
        )


if __name__ == "__main__":
    unittest.main()
