import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from codex_control_tower.conversation_metrics import compact_tokens, daily_token_usage, session_metrics


class ConversationMetricsTests(unittest.TestCase):
    def test_reads_latest_token_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            rows = [
                {"timestamp": "2026-09-08T01:00:00Z", "type": "session_meta", "payload": {"cwd": "/tmp/project"}},
                {"timestamp": "2026-09-08T01:01:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 1000, "cached_input_tokens": 600, "output_tokens": 100, "reasoning_output_tokens": 20, "total_tokens": 1100}, "last_token_usage": {"input_tokens": 500, "cached_input_tokens": 300, "output_tokens": 50, "total_tokens": 550}, "model_context_window": 2000}}},
                {"timestamp": "2026-09-08T01:01:01Z", "type": "token_usage_record", "payload": {"turn_token_usage": {"input_tokens": 900, "cached_input_tokens": 500, "output_tokens": 180, "total_tokens": 1080}}},
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            result = session_metrics(path)
            self.assertEqual(result["context_percent"], 25)
            self.assertEqual(result["cache_percent"], 60)
            self.assertEqual(result["last"]["total_tokens"], 550)
            self.assertEqual(result["turn"]["output_tokens"], 180)

    def test_compact_token_labels(self):
        self.assertEqual(compact_tokens(1200), "1.2K")
        self.assertEqual(compact_tokens(2_300_000), "2.3M")

    def test_daily_usage_sums_only_requests_after_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            rows = [
                {"timestamp": "2026-09-07T23:59:00Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 90, "cached_input_tokens": 50, "output_tokens": 10, "total_tokens": 100}}}},
                {"timestamp": "2026-09-08T00:01:00Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 180, "cached_input_tokens": 120, "output_tokens": 20, "total_tokens": 200}}}},
                {"timestamp": "2026-09-08T00:02:00Z", "payload": {"type": "token_count", "info": None}},
                {"timestamp": "2026-09-08T00:03:00Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 270, "cached_input_tokens": 200, "output_tokens": 30, "total_tokens": 300}}}},
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            result = daily_token_usage([Path(directory)], datetime.fromisoformat("2026-09-08T00:00:00+00:00").timestamp())
            self.assertEqual(result["total_tokens"], 500)
            self.assertEqual(result["input_tokens"], 450)
            self.assertEqual(result["cached_input_tokens"], 320)


if __name__ == "__main__":
    unittest.main()
