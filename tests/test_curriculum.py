import json
import tempfile
import unittest
from pathlib import Path

from codex_control_tower.curriculum import CURRICULUM_ROOT, CurriculumLibrary, CurriculumStore, validate_bundle
from codex_control_tower.lessons import LessonChatStore, LessonStore, validate_lesson


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

    def test_reviewed_lesson_is_real_teaching_content(self):
        bundle = CurriculumLibrary().get("vla")
        with tempfile.TemporaryDirectory() as directory:
            store = LessonStore(Path(directory) / "lessons.json")
            flow = store.get(bundle, "flow_matching_action_generation")
            lora = store.get(bundle, "downstream_finetuning_and_peft")
            self.assertTrue(validate_lesson(flow))
            self.assertIn("速度场", flow["one_liner"])
            self.assertIn("LoRA", lora["one_liner"])
            self.assertGreaterEqual(len(flow.get("comparisons", [])), 2)

    def test_outline_only_progress_is_archived_and_reset(self):
        bundle = CurriculumLibrary().get("vla")
        with tempfile.TemporaryDirectory() as directory:
            progress = Path(directory) / "progress.json"
            key = "vla:v1"
            progress.write_text(json.dumps({
                "schema_version": 1,
                "selected_domain": "vla",
                "curricula": {key: {
                    "approved_at": "2026-09-06T12:00:00",
                    "path": "standard_path",
                    "current": "behavior_cloning_for_vla",
                    "concepts": {"vla_problem_formulation": {"state": "understood"}},
                }},
            }), encoding="utf-8")
            store = CurriculumStore(progress)
            record = store.record(bundle)
            self.assertEqual(record["concepts"], {})
            self.assertIn("vla_problem_formulation", record["legacy_outline_progress"]["concepts"])
            self.assertTrue(record["approved_at"])

    def test_lesson_chat_history_is_local_and_bounded(self):
        bundle = CurriculumLibrary().get("vla")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chats.json"
            store = LessonChatStore(path)
            for index in range(45):
                store.append(bundle, "flow_matching_action_generation", "user", f"问题 {index}")
            rows = store.messages(bundle, "flow_matching_action_generation")
            self.assertEqual(len(rows), 40)
            self.assertEqual(rows[0]["content"], "问题 5")
            reloaded = LessonChatStore(path)
            self.assertEqual(reloaded.messages(bundle, "flow_matching_action_generation")[-1]["content"], "问题 44")
            reloaded.clear(bundle, "flow_matching_action_generation")
            self.assertEqual(reloaded.messages(bundle, "flow_matching_action_generation"), [])


if __name__ == "__main__":
    unittest.main()
