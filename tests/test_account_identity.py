import base64
import json
import tempfile
import unittest
from pathlib import Path

from codex_control_tower.account_identity import native_codex_account, native_codex_quota_profile, subscription_identity


def token(claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


class NativeCodexAccountTests(unittest.TestCase):
    def write_auth(self, directory, payload):
        path = Path(directory) / "auth.json"; path.write_text(json.dumps(payload), encoding="utf-8"); return path

    def test_prefers_name_then_falls_back_to_email(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_auth(directory, {"auth_mode":"chatgpt","tokens":{"id_token":token({"name":"  Ada   Lovelace ","email":"ada@example.com"})}})
            self.assertEqual(native_codex_account(path), "Ada Lovelace")
            path = self.write_auth(directory, {"auth_mode":"chatgpt","tokens":{"id_token":token({"email":"ada@example.com"})}})
            self.assertEqual(native_codex_account(path), "ada@example.com")

    def test_ignores_api_key_and_preserves_source_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_auth(directory, {"auth_mode":"apikey","tokens":{"id_token":token({"email":"hidden@example.com"})}})
            self.assertEqual(native_codex_account(path), "")
        self.assertEqual(subscription_identity("最近账号", "Switch 账号", "本机账号", True), ("最近账号", "最近请求"))
        self.assertEqual(subscription_identity("", "", "本机账号", True), ("本机账号", "本机登录"))

    def test_native_quota_comes_from_latest_local_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            auth = self.write_auth(directory, {"auth_mode":"chatgpt","tokens":{"id_token":token({"email":"user@example.com"})}})
            session = root / "sessions" / "2026" / "09"; session.mkdir(parents=True)
            (session / "rollout.jsonl").write_text(json.dumps({"payload":{"type":"token_count","rate_limits":{"primary":{"used_percent":12,"window_minutes":300,"resets_at":1234},"secondary":{"used_percent":22,"window_minutes":10080,"resets_at":5678}}}})+"\n", encoding="utf-8")
            profile = native_codex_quota_profile(auth, root / "sessions")
            self.assertEqual(profile["limits"]["primary"]["remainingPercent"], 88)
            self.assertEqual(profile["limits"]["secondary"]["remainingPercent"], 78)


if __name__ == "__main__": unittest.main()
