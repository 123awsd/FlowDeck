import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_control_tower.ai_client import AIConfig, chat_completion, load_ai_config
from codex_control_tower.selection_assistant import request_ai


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class AIClientTests(unittest.TestCase):
    def test_provider_switch_only_changes_one_env_line(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            template = """AI_PROVIDER={provider}
DEEPSEEK_API_KEY=deepseek-secret
DASHSCOPE_API_KEY=qwen-secret
"""
            env_file.write_text(template.format(provider="deepseek"), encoding="utf-8")
            deepseek = load_ai_config(env_file, environment={}, legacy_key_file=Path(directory) / "missing")
            env_file.write_text(template.format(provider="qwen"), encoding="utf-8")
            qwen = load_ai_config(env_file, environment={}, legacy_key_file=Path(directory) / "missing")
            self.assertEqual((deepseek.provider, deepseek.api_key), ("deepseek", "deepseek-secret"))
            self.assertEqual((qwen.provider, qwen.api_key), ("qwen", "qwen-secret"))
            self.assertIn("dashscope.aliyuncs.com", qwen.api_url)
            self.assertEqual(qwen.model, "qwen3.6-flash")

    def test_qwen_workspace_base_and_model_can_be_overridden(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("""AI_PROVIDER=qwen
DASHSCOPE_API_KEY=qwen-secret
QWEN_BASE_URL=https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-custom
""", encoding="utf-8")
            config = load_ai_config(env_file, environment={})
            self.assertEqual(config.api_url, "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions")
            self.assertEqual(config.model, "qwen-custom")

    def test_missing_selected_provider_key_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("AI_PROVIDER=qwen\nDEEPSEEK_API_KEY=unused\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "DASHSCOPE_API_KEY"):
                load_ai_config(env_file, environment={})

    @patch("codex_control_tower.ai_client.urlopen")
    def test_qwen_request_uses_compatible_payload(self, mocked_urlopen):
        mocked_urlopen.return_value = _Response({"choices": [{"message": {"content": "完成"}}]})
        config = AIConfig("qwen", "千问", "https://example.test/v1/chat/completions", "qwen-test", "secret")
        result = chat_completion(
            [{"role": "user", "content": "你好"}],
            temperature=0.2,
            max_tokens=100,
            json_object=True,
            config=config,
        )
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(result, "完成")
        self.assertEqual(payload["model"], "qwen-test")
        self.assertFalse(payload["enable_thinking"])
        self.assertNotIn("thinking", payload)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")

    @patch("codex_control_tower.ai_client.urlopen")
    def test_deepseek_request_keeps_provider_specific_payload(self, mocked_urlopen):
        mocked_urlopen.return_value = _Response({"choices": [{"message": {"content": "完成"}}]})
        config = AIConfig("deepseek", "DeepSeek", "https://example.test/chat/completions", "deepseek-test", "secret")
        chat_completion(
            [{"role": "user", "content": "你好"}],
            temperature=0,
            max_tokens=100,
            config=config,
        )
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertNotIn("enable_thinking", payload)

    @patch("codex_control_tower.selection_assistant.chat_completion")
    def test_selection_assistant_uses_shared_client(self, mocked_chat):
        mocked_chat.return_value = "译文"
        self.assertEqual(request_ai("translate", "hello"), "译文")
        messages = mocked_chat.call_args.args[0]
        self.assertEqual(messages[-1], {"role": "user", "content": "hello"})
        self.assertEqual(mocked_chat.call_args.kwargs["temperature"], 0)


if __name__ == "__main__":
    unittest.main()
