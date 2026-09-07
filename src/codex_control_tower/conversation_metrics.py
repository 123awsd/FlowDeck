"""Bounded, read-only summaries of Codex JSONL session usage."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


_CACHE = {}
_TAIL_LIMIT = 4 * 1024 * 1024


def _timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _tail_lines(path, limit=_TAIL_LIMIT):
    with path.open("rb") as stream:
        size = stream.seek(0, 2)
        stream.seek(max(0, size - limit))
        if size > limit:
            stream.readline()
        return stream.read().splitlines()


def session_metrics(path):
    """Return the newest usage snapshot without scanning an unbounded session."""
    path = Path(path)
    try:
        stat = path.stat(); signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
    except OSError:
        return {}
    cached = _CACHE.get(str(path))
    if cached and cached[0] == signature:
        return dict(cached[1])
    started = 0.0
    try:
        with path.open(encoding="utf-8") as stream:
            first = json.loads(stream.readline())
        started = _timestamp(first.get("timestamp"))
    except (OSError, ValueError):
        pass
    info = None
    turn_usage = None
    turn_started_at = turn_completed_at = 0.0
    try:
        for raw in reversed(_tail_lines(path)):
            try:
                record = json.loads(raw); payload = record.get("payload", {})
            except (ValueError, UnicodeDecodeError):
                continue
            payload_type = payload.get("type")
            if turn_usage is None and record.get("type") == "token_usage_record" and isinstance(payload.get("turn_token_usage"), dict):
                turn_usage = payload["turn_token_usage"]
            if info is None and payload_type == "token_count" and isinstance(payload.get("info"), dict):
                info = payload["info"]
            if not turn_started_at and payload_type == "task_started":
                turn_started_at = _timestamp(record.get("timestamp"))
            if not turn_completed_at and payload_type == "task_complete":
                turn_completed_at = _timestamp(record.get("timestamp"))
            if info is not None and turn_usage is not None and turn_started_at and turn_completed_at:
                break
    except OSError:
        pass
    total = dict((info or {}).get("total_token_usage") or {})
    last = dict((info or {}).get("last_token_usage") or {})
    context_window = int((info or {}).get("model_context_window") or 0)
    context_tokens = int(last.get("input_tokens") or 0)
    input_tokens = int(total.get("input_tokens") or 0)
    cached_tokens = int(total.get("cached_input_tokens") or 0)
    result = {
        "started_at": started,
        "updated_at": stat.st_mtime,
        "turn_started_at": turn_started_at,
        "turn_running": bool(turn_started_at and turn_started_at > turn_completed_at),
        "total": total,
        "last": last,
        "turn": dict(turn_usage or last),
        "context_window": context_window,
        "context_tokens": context_tokens,
        "context_percent": min(100, round(context_tokens / context_window * 100)) if context_window else None,
        "cache_percent": min(100, round(cached_tokens / input_tokens * 100)) if input_tokens else None,
    }
    _CACHE[str(path)] = (signature, result)
    if len(_CACHE) > 200:
        for key in list(_CACHE)[:-150]:
            _CACHE.pop(key, None)
    return dict(result)


def compact_tokens(value):
    value = int(value or 0)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def elapsed_label(started_at, updated_at=None, running=False, now=None):
    import time
    if not started_at:
        return "时间未知"
    end = (now or time.time()) if running else (updated_at or now or time.time())
    minutes = max(0, int((end - started_at) / 60))
    if minutes < 60:
        return f"{minutes} 分钟"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} 小时 {minutes} 分"
    return f"{hours // 24} 天 {hours % 24} 小时"
