import json
import tempfile
import unittest
from pathlib import Path

from codex_control_tower.conversation_ownership import discover_conversation_owners


class ConversationOwnershipTests(unittest.TestCase):
    def test_detects_owner_and_ignores_latest_follower_role(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logs = root / "logs" / "20260923"
            storage = root / "workspaceStorage"
            for window, workspace_id, path in (("window1", "aaa", "/work/owner"), ("window2", "bbb", "/work/follower")):
                exthost = logs / window / "exthost"
                codex = exthost / "openai.chatgpt"
                codex.mkdir(parents=True)
                (exthost / "exthost.log").write_text(f"lock {storage}/{workspace_id}/state.vscdb\n")
                record = storage / workspace_id
                record.mkdir(parents=True)
                (record / "workspace.json").write_text(json.dumps({"folder": "file://" + path}))
            (logs / "window1/exthost/openai.chatgpt/Codex.log").write_text(
                "2026-09-23T10:00:00.000Z [info] thread_stream_role_changed conversationId=thread-1 ownerClientId=null role=owner\n"
            )
            (logs / "window2/exthost/openai.chatgpt/Codex.log").write_text(
                "2026-09-23T10:01:00.000Z [info] thread_stream_role_changed conversationId=thread-1 ownerClientId=x role=follower\n"
            )
            result = discover_conversation_owners({"thread-1"}, root / "logs", storage, {"/work/owner", "/work/follower"})
            self.assertEqual(result["thread-1"]["path"], "/work/owner")

    def test_drops_window_whose_latest_role_is_follower(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); logs = root / "logs/now/window1/exthost"; logs.mkdir(parents=True)
            storage = root / "storage/aaa"; storage.mkdir(parents=True)
            (logs / "exthost.log").write_text(f"workspaceStorage/aaa\n")
            (storage / "workspace.json").write_text(json.dumps({"folder": "file:///work/a"}))
            codex = logs / "openai.chatgpt"; codex.mkdir()
            (codex / "Codex.log").write_text(
                "2026-09-23T10:00:00Z [info] thread_stream_role_changed conversationId=t role=owner\n"
                "2026-09-23T10:01:00Z [info] thread_stream_role_changed conversationId=t role=follower\n"
            )
            self.assertEqual(discover_conversation_owners({"t"}, root / "logs", root / "storage", {"/work/a"}), {})
