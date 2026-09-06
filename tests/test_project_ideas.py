import tempfile
import unittest
from pathlib import Path

from codex_control_tower.project_ideas import ProjectIdeaStore


class ProjectIdeaStoreTests(unittest.TestCase):
    def test_project_isolation_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ideas.json"
            store = ProjectIdeaStore(path)
            first = store.add("/work/a", "A", "尝试新的数据采样策略")
            store.add("/work/b", "B", "另一个项目的想法")
            self.assertEqual([row["text"] for row in store.list("/work/a")], ["尝试新的数据采样策略"])
            self.assertTrue(store.update(first["id"], "尝试主动采样"))
            self.assertTrue(store.toggle(first["id"], True))
            self.assertEqual(store.list("/work/a", include_done=False), [])
            self.assertEqual(ProjectIdeaStore(path).list("/work/a")[0]["text"], "尝试主动采样")
            self.assertTrue(store.delete(first["id"]))
            self.assertEqual(store.list("/work/a"), [])

    def test_empty_ideas_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectIdeaStore(Path(directory) / "ideas.json")
            self.assertIsNone(store.add("/work/a", "A", "   "))


if __name__ == "__main__":
    unittest.main()
