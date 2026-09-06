import json
import tempfile
import unittest
from pathlib import Path

from codex_control_tower.paths import ASSETS_DIR
from codex_control_tower.vocabulary import VocabularyLibrary, VocabularyStore, parse_vocabulary


class VocabularyTests(unittest.TestCase):
    def test_supported_lexicon_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.txt"
            path.write_text(
                "基础词\n"
                "policy\t策略\n"
                "robust|adj.|鲁棒的|The controller is robust.|robustness n.\n"
                "flow matching\tn.\t流匹配\tFlow matching generates actions.\tFM\tVLA\n",
                encoding="utf-8",
            )
            rows = parse_vocabulary(path)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["category"], "基础词")
            self.assertEqual(rows[1]["pos"], "adj.")
            self.assertEqual(rows[2]["example"], "Flow matching generates actions.")

    def test_review_ratings_persist_intervals_and_daily_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = VocabularyStore(path)
            store.rate("word-a", "forgot")
            store.rate("word-b", "fuzzy")
            store.rate("word-c", "remembered")
            self.assertEqual(store.state("word-a")["interval_days"], 1)
            self.assertEqual(store.state("word-b")["interval_days"], 2)
            self.assertEqual(store.state("word-c")["interval_days"], 3)
            self.assertEqual(store.data["daily"]["reviewed"], 3)
            self.assertEqual(VocabularyStore(path).data["daily"]["remembered"], 1)

    def test_bundled_words_and_cats_are_available(self):
        lexicons = VocabularyLibrary().lexicons()
        counts = {row["id"]: row["count"] for row in lexicons}
        self.assertGreater(counts.get("文献术语精选_280", 0), 100)
        self.assertGreater(counts.get("雅思词汇真经_扩展", 0), 3000)
        self.assertGreater(counts.get("高考3500词汇表", 0), 3000)
        self.assertGreaterEqual(len(list((ASSETS_DIR / "vocab-cats").glob("*.png"))), 30)


if __name__ == "__main__":
    unittest.main()
