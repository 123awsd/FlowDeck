import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_control_tower.ai_client import AIConfig, chat_completion, load_ai_config
from codex_control_tower.selection_assistant import request_ai


class _Response:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self): return json.dumps(self.payload).encode("utf-8")


class AIClientTests(unittest.TestCase):
    def test_provider_switch_only_changes_one_env_line(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            template = "AI_PROVIDER={provider}\nDEEPSEEK_API_KEY=deepseek-secret\nDASHSCOPE_API_KEY=qwen-secret\n"
            env_file.write_text(template.format(provider="deepseek"), encoding="utf-8")
            deepseek = load_ai_config(env_file, environment={}, legacy_key_file=Path(directory) / "missing")
            env_file.write_text(template.format(provider="qwen"), encoding="utf-8")
            qwen = load_ai_config(env_file, environment={}, legacy_key_file=Path(directory) / "missing")
            self.assertEqual((deepseek.provider, deepseek.api_key), ("deepseek", "deepseek-secret"))
            self.assertEqual((qwen.provider, qwen.api_key), ("qwen", "qwen-secret"))

    def test_missing_selected_provider_key_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("AI_PROVIDER=qwen\nDEEPSEEK_API_KEY=unused\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "DASHSCOPE_API_KEY"):
                load_ai_config(env_file, environment={})

    @patch("codex_control_tower.ai_client.urlopen")
    def test_provider_specific_payloads(self, mocked_urlopen):
        mocked_urlopen.return_value = _Response({"choices": [{"message": {"content": "完成"}}]})
        qwen = AIConfig("qwen", "千问", "https://example.test/v1/chat/completions", "qwen-test", "secret")
        self.assertEqual(chat_completion([{"role":"user","content":"你好"}], temperature=.2, max_tokens=100, json_object=True, config=qwen), "完成")
        payload = json.loads(mocked_urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertFalse(payload["enable_thinking"]); self.assertNotIn("thinking", payload)
        deepseek = AIConfig("deepseek", "DeepSeek", "https://example.test/chat/completions", "deepseek-test", "secret")
        chat_completion([{"role":"user","content":"你好"}], temperature=0, max_tokens=100, config=deepseek)
        payload = json.loads(mocked_urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload["thinking"], {"type":"disabled"})

    @patch("codex_control_tower.selection_assistant.chat_completion")
    def test_selection_assistant_uses_shared_client(self, mocked_chat):
        mocked_chat.return_value = "译文"
        self.assertEqual(request_ai("translate", "hello"), "译文")
        self.assertEqual(mocked_chat.call_args.args[0][-1], {"role":"user","content":"hello"})


if __name__ == "__main__": unittest.main()
