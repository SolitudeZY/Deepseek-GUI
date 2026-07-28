import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.conversation import (
    list_conversations,
    new_conversation,
    save_conversation,
    search_conversations,
    set_conversation_archived,
    set_project_archived,
)


class ConversationManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.dir_patch = patch(
            "app.conversation.get_conversations_dir", return_value=self.root
        )
        self.dir_patch.start()

    def tearDown(self):
        self.dir_patch.stop()
        self.temp_dir.cleanup()

    def _conversation(self, title, project_path="", messages=None):
        conv = new_conversation("Test", project_path=project_path)
        conv["title"] = title
        conv["messages"] = list(messages or [])
        save_conversation(conv)
        return conv

    def test_conversation_and_project_archive_round_trip(self):
        first = self._conversation("first", "E:/project-a")
        second = self._conversation("second", "E:/project-a")
        other = self._conversation("other", "E:/project-b")

        self.assertTrue(set_conversation_archived(first["id"], True))
        summaries = {item["id"]: item for item in list_conversations()}
        self.assertTrue(summaries[first["id"]]["archived"])
        self.assertFalse(summaries[second["id"]]["archived"])

        self.assertEqual(set_project_archived("E:/project-a", True), 2)
        summaries = {item["id"]: item for item in list_conversations()}
        self.assertTrue(summaries[first["id"]]["archived"])
        self.assertTrue(summaries[second["id"]]["archived"])
        self.assertFalse(summaries[other["id"]]["archived"])

        self.assertEqual(set_project_archived("E:/project-a", False), 2)
        summaries = {item["id"]: item for item in list_conversations()}
        self.assertFalse(summaries[first["id"]]["archived"])
        self.assertFalse(summaries[second["id"]]["archived"])

    def test_search_only_matches_visible_user_and_assistant_content(self):
        visible = self._conversation("visible", messages=[
            {"role": "user", "content": "alpha question"},
            {"role": "assistant", "content": "beta answer"},
        ])
        self._conversation("tool-only", messages=[
            {"role": "assistant", "content": "calling a tool"},
            {"role": "tool", "content": "hidden-sentinel-keyword"},
        ])

        self.assertEqual(
            [item["id"] for item in search_conversations("alpha")],
            [visible["id"]],
        )
        self.assertEqual(search_conversations("hidden-sentinel-keyword"), [])
        self.assertEqual(search_conversations("does-not-exist"), [])


if __name__ == "__main__":
    unittest.main()
