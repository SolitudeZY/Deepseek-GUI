import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.conversation import (
    delete_conversations,
    load_conversation,
    list_conversations,
    new_conversation,
    save_conversation,
    search_conversations,
    set_conversation_archived,
    set_conversations_archived,
    set_project_archived,
)
from app.webview_app import API


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

    def test_missing_windows_project_path_matches_synced_path_variants(self):
        first = self._conversation("first", "E:\\Missing Project\\repo")
        second = self._conversation("second", "e:/missing project/repo")

        self.assertEqual(set_project_archived("E:/Missing Project/repo/", True), 2)
        summaries = {item["id"]: item for item in list_conversations()}
        self.assertTrue(summaries[first["id"]]["archived"])
        self.assertTrue(summaries[second["id"]]["archived"])

        api = API.__new__(API)
        api._config = {
            "recent_projects": [{"path": "e:/missing project/repo/", "name": "repo"}],
        }
        projects = api.list_recent_projects()
        self.assertEqual(len(projects), 1)
        self.assertTrue(projects[0]["archived"])

    def test_bulk_archive_and_delete_ignore_duplicates_and_missing_ids(self):
        first = self._conversation("first")
        second = self._conversation("second")

        self.assertEqual(
            set_conversations_archived([first["id"], first["id"], "missing"], True),
            1,
        )
        self.assertEqual(
            delete_conversations([first["id"], second["id"], second["id"], "missing"]),
            2,
        )
        self.assertEqual(list_conversations(), [])

    def test_bulk_operations_reject_the_active_generating_conversation(self):
        conv = self._conversation("active")
        api = API.__new__(API)
        api._temporary_conversations = {}
        api._running = True
        api._current_conv_id = conv["id"]

        archived = api.bulk_archive_conversations([conv["id"]])
        deleted = api.bulk_delete_conversations([conv["id"]])

        self.assertFalse(archived["ok"])
        self.assertFalse(deleted["ok"])
        self.assertIsNotNone(load_conversation(conv["id"]))
        self.assertFalse(bool(load_conversation(conv["id"]).get("archived_at")))

    def test_project_archive_api_uses_conversation_ids_without_local_directory(self):
        conv = self._conversation("synced", "E:/computer-a/project")
        api = API.__new__(API)
        api._running = False

        result = api.set_project_archived("e:/computer-a/project/", True)

        self.assertEqual(result, {"ok": True, "updated": 1, "error": ""})
        self.assertTrue(api.open_conversation(conv["id"])["project_exists"] is False)

    def test_temporary_completion_stays_in_memory_and_skips_sync(self):
        api = API.__new__(API)
        api._config = {}
        api._agent = None
        api._window = None
        api._window_visible = True
        api._running = True
        temporary = new_conversation("Test")
        temporary["temporary"] = True
        api._temporary_conversations = {temporary["id"]: temporary}

        with patch.object(api, "_auto_title"), patch(
            "app.webview_app.upload_conversation"
        ) as upload:
            api._on_done(temporary, [{"role": "assistant", "content": "ephemeral"}])

        self.assertFalse(upload.called)
        self.assertEqual(list_conversations(), [])
        self.assertEqual(
            api._temporary_conversations[temporary["id"]]["messages"][0]["content"],
            "ephemeral",
        )
        self.assertFalse(api.sync_upload_current(temporary["id"]))

    def test_temporary_conversation_stays_in_memory_and_is_discarded(self):
        api = API.__new__(API)
        api._config = {
            "active_model_config": "Test",
            "model_configs": [{"name": "Test", "model": "test-model"}],
        }
        api._temporary_conversations = {}
        api._running = False

        temporary = api.new_temporary_conversation()
        self.assertTrue(temporary["temporary"])
        self.assertEqual(list_conversations(), [])
        opened = api.open_conversation(temporary["id"])
        self.assertTrue(opened["temporary"])

        in_memory = api._load_conversation(temporary["id"])
        in_memory["messages"].append({"role": "user", "content": "ephemeral"})
        api._save_conversation(in_memory)
        self.assertEqual(list_conversations(), [])

        regular = api.new_conversation("")
        self.assertNotIn(temporary["id"], api._temporary_conversations)
        self.assertIsNotNone(api.open_conversation(regular["id"]))

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
