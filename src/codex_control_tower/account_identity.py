"""Read a display-only identity from the official Codex local login."""

import base64
import binascii
import json
from pathlib import Path


NATIVE_AUTH_FILE = Path.home() / ".codex" / "auth.json"
PROFILE_CLAIM = "https://api.openai.com/profile"


def _jwt_claims(token):
    """Decode local JWT claims without treating them as verified authorization."""
    try:
        payload = str(token).split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        return claims if isinstance(claims, dict) else {}
    except (IndexError, TypeError, ValueError, UnicodeError, binascii.Error, json.JSONDecodeError):
        return {}


def _display_value(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:120]


def native_codex_account(auth_file=None):
    """Return the local ChatGPT login name/email, or an empty string."""
    path = Path(auth_file) if auth_file is not None else NATIVE_AUTH_FILE
    try:
        auth = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return ""
    if not isinstance(auth, dict) or str(auth.get("auth_mode", "")).lower() != "chatgpt":
        return ""
    tokens = auth.get("tokens")
    if not isinstance(tokens, dict):
        return ""
    claims = [_jwt_claims(tokens.get("id_token")), _jwt_claims(tokens.get("access_token"))]
    for key in ("name", "email"):
        for claim in claims:
            value = _display_value(claim.get(key))
            if value:
                return value
    for key in ("name", "email"):
        for claim in claims:
            profile = claim.get(PROFILE_CLAIM)
            if isinstance(profile, dict):
                value = _display_value(profile.get(key))
                if value:
                    return value
    return ""


def subscription_identity(session_account, switch_name, native_account, workspace_selected=False):
    """Resolve the subscription display value and explain which source won."""
    if session_account:
        return session_account, "最近请求"
    if switch_name:
        return switch_name, "工作区" if workspace_selected else "插件当前"
    if native_account:
        return native_account, "本机登录"
    return "未知账号", "插件当前"


def _session_rate_limits(path, tail_bytes=512 * 1024):
    """Read the newest rate-limit snapshot without loading conversation content."""
    try:
        with Path(path).open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - tail_bytes))
            data = stream.read()
    except OSError:
        return {}
    for raw in reversed(data.splitlines()):
        try:
            payload = json.loads(raw).get("payload", {})
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        limits = payload.get("rate_limits") if payload.get("type") == "token_count" else None
        if isinstance(limits, dict):
            return limits
    return {}


def _quota_window(window):
    if not isinstance(window, dict) or not isinstance(window.get("used_percent"), (int, float)):
        return {}
    remaining = round(max(0, min(100, 100 - window["used_percent"])))
    return {
        "remainingPercent": remaining,
        "resetsAt": window.get("resets_at"),
        "windowMinutes": window.get("window_minutes"),
    }


def native_codex_quota_profile(auth_file=None, session_root=None, max_files=20):
    """Build a display-only Plus quota profile from recent official sessions."""
    account = native_codex_account(auth_file)
    if not account:
        return {}
    root = Path(session_root) if session_root is not None else Path.home() / ".codex" / "sessions"
    files = []
    try:
        for path in root.glob("**/*.jsonl"):
            try:
                files.append((path.stat().st_mtime_ns, path))
            except OSError:
                pass
    except OSError:
        pass
    files.sort(reverse=True)
    limits = {}
    for _, path in files[:max_files]:
        snapshot = _session_rate_limits(path)
        if snapshot:
            limits = {
                "primary": _quota_window(snapshot.get("primary")),
                "secondary": _quota_window(snapshot.get("secondary")),
            }
            break
    return {"id": "native:official", "name": account, "kind": "native", "limits": limits}
