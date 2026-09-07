import tempfile
import unittest
from pathlib import Path

from codex_control_tower.provider_routing import assert_independent_provider_home


class ProviderHomeSafetyTests(unittest.TestCase):
    def test_accepts_complete_independent_home(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.toml").write_text('model = "test"', encoding="utf-8")
            (root / "auth.json").write_text(
                '{"auth_mode":"apikey","OPENAI_API_KEY":"sk-test"}', encoding="utf-8"
            )
            (root / "sessions").mkdir()
            self.assertEqual(assert_independent_provider_home(root), (True, ""))

    def test_rejects_any_shared_symbolic_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.toml").write_text('', encoding="utf-8")
            (root / "auth.json").write_text(
                '{"auth_mode":"apikey","OPENAI_API_KEY":"sk-test"}', encoding="utf-8"
            )
            external = root / "external"
            external.mkdir()
            (root / "sessions").symlink_to(external, target_is_directory=True)
            safe, message = assert_independent_provider_home(root)
            self.assertFalse(safe)
            self.assertIn("sessions", message)

    def test_requires_provider_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            safe, message = assert_independent_provider_home(directory)
            self.assertFalse(safe)
            self.assertIn("config.toml", message)

    def test_rejects_chatgpt_auth_without_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.toml").write_text('model_provider = "test"', encoding="utf-8")
            (root / "auth.json").write_text(
                '{"auth_mode":"chatgpt","tokens":{"access_token":"secret"}}', encoding="utf-8"
            )
            safe, message = assert_independent_provider_home(root)
            self.assertFalse(safe)
            self.assertIn("API Key", message)


if __name__ == "__main__":
    unittest.main()
