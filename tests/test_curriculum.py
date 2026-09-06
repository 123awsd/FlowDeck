import json
import tempfile
import unittest
from pathlib import Path

from codex_control_tower.curriculum import CURRICULUM_ROOT, CurriculumLibrary, CurriculumStore, validate_bundle


class CurriculumTests(unittest.TestCase):
    def test_imported_vla_bundle_is_valid(self):
        report = validate_bundle(CURRICULUM_ROOT / "vla")
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["counts"], {"modules": 7, "concepts": 39, "sources": 18})

    def test_recommended_path_and_progress_are_reusable(self):
        library = CurriculumLibrary()
        bundle = library.get("vla")
        path = library.path(bundle, "standard_path")
        with tempfile.TemporaryDirectory() as directory:
            store = CurriculumStore(Path(directory) / "progress.json")
            first = store.current(bundle, path)
            store.set_state(bundle, first, "understood")
            next_item = store.advance(bundle, path, first)
            self.assertNotEqual(first, next_item)
            self.assertEqual(store.stats(bundle, path)["mastered"], 1)
            reloaded = CurriculumStore(Path(directory) / "progress.json")
            self.assertEqual(reloaded.state(bundle, first), "understood")

    def test_dependency_cycle_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = {"sources": [{"id": "s1", "url": "https://example.test"}]}
            curriculum = {
                "domain": {"id": "sample", "version": "v1"},
                "source_ids": ["s1"],
                "modules": [{"id": "m1", "concept_ids": ["a", "b"]}],
                "concepts": [
                    {"id": "a", "module_id": "m1", "priority": "P0", "stability": "foundation", "source_ids": ["s1"], "prerequisites": ["b"], "related_concepts": []},
                    {"id": "b", "module_id": "m1", "priority": "P0", "stability": "foundation", "source_ids": ["s1"], "prerequisites": ["a"], "related_concepts": []},
                ],
                "recommended_paths": {"standard_path": ["a", "b"]},
            }
            (root / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
            (root / "curriculum_v1.json").write_text(json.dumps(curriculum), encoding="utf-8")
            report = validate_bundle(root)
            self.assertFalse(report["ok"])
            self.assertTrue(any("存在环" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
