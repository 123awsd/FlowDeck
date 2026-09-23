"""Read-only detection of which live VS Code window owns a Codex thread."""

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse


WORKSPACE_RE = re.compile(r"workspaceStorage/([0-9a-f]+)")
ROLE_RE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2}(?:T|\s)\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?) .*thread_stream_role_changed .*conversationId=(?P<id>\S+) .*role=(?P<role>owner|follower)(?:\s|$)"
)


def _tail_text(path, limit=2 * 1024 * 1024):
    try:
        with path.open("rb") as stream:
            size = path.stat().st_size
            stream.seek(max(0, size - limit))
            data = stream.read()
        if size > limit:
            data = data.split(b"\n", 1)[-1]
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _workspace_path(codex_log, workspace_storage):
    exthost_log = codex_log.parent.parent / "exthost.log"
    matches = WORKSPACE_RE.findall(_tail_text(exthost_log, 512 * 1024))
    if not matches:
        return ""
    record = workspace_storage / matches[-1] / "workspace.json"
    try:
        value = json.loads(record.read_text(encoding="utf-8")).get("folder", "")
    except (OSError, ValueError):
        return ""
    parsed = urlparse(value)
    if parsed.scheme == "file":
        return unquote(parsed.path)
    if parsed.scheme == "vscode-remote":
        return unquote(parsed.path)
    return value.removeprefix("file://")


def discover_conversation_owners(conversation_ids, logs_root=None, workspace_storage=None, live_paths=None):
    """Return the latest live owner workspace for each requested thread ID.

    Only the tail of current VS Code logs is read. No conversation content or
    account credentials are inspected.
    """
    wanted = {value for value in conversation_ids if value}
    if not wanted:
        return {}
    logs_root = Path(logs_root or (Path.home() / ".config/Code/logs"))
    workspace_storage = Path(workspace_storage or (Path.home() / ".config/Code/User/workspaceStorage"))
    live = {str(Path(value)) for value in (live_paths or []) if value}
    candidates = {}
    sessions = sorted((path for path in logs_root.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True)[:3] if logs_root.exists() else []
    for session in sessions:
        for codex_log in session.glob("window*/exthost/openai.chatgpt/Codex.log"):
            workspace = _workspace_path(codex_log, workspace_storage)
            if not workspace or (live and workspace not in live):
                continue
            latest = {}
            for line in _tail_text(codex_log).splitlines():
                match = ROLE_RE.search(line)
                if match and match.group("id") in wanted:
                    latest[match.group("id")] = (match.group("time"), match.group("role"))
            for conversation_id, (stamp, role) in latest.items():
                if role != "owner":
                    continue
                current = candidates.get(conversation_id)
                if current is None or stamp > current[0]:
                    candidates[conversation_id] = (stamp, workspace)
    return {conversation_id: {"path": value[1], "seen_at": value[0]} for conversation_id, value in candidates.items()}
