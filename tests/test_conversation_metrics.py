import json
import tempfile
import unittest
from pathlib import Path

from codex_control_tower.conversation_metrics import compact_tokens, session_metrics


class ConversationMetricsTests(unittest.TestCase):
    def test_reads_latest_token_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            rows = [
                {"timestamp": "2026-09-08T01:00:00Z", "type": "session_meta", "payload": {"cwd": "/tmp/project"}},
                {"timestamp": "2026-09-08T01:01:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 1000, "cached_input_tokens": 600, "output_tokens": 100, "reasoning_output_tokens": 20, "total_tokens": 1100}, "last_token_usage": {"input_tokens": 500, "cached_input_tokens": 300, "output_tokens": 50, "total_tokens": 550}, "model_context_window": 2000}}},
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            result = session_metrics(path)
            self.assertEqual(result["context_percent"], 25)
            self.assertEqual(result["cache_percent"], 60)
            self.assertEqual(result["last"]["total_tokens"], 550)

    def test_compact_token_labels(self):
        self.assertEqual(compact_tokens(1200), "1.2K")
        self.assertEqual(compact_tokens(2_300_000), "2.3M")


if __name__ == "__main__":
    unittest.main()
