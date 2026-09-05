#!/usr/bin/env python3
"""Write a Codex turn event for Control Tower.

Usage example:
  python3 notify_hook.py --task-id 3 --status Ready --summary "测试已完成"

The task ID and status can also be provided in a JSON object on stdin.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


EVENT_FILE = Path(__file__).resolve().parent / "events.jsonl"
STATUSES = {"Running", "Needs input", "Ready", "Blocked", "Done"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", type=int)
    parser.add_argument("--status", choices=sorted(STATUSES))
    parser.add_argument("--summary", default="")
    args = parser.parse_args()
    payload = {}
    if not sys.stdin.isatty():
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            payload = {}
    task_id = args.task_id or payload.get("task_id")
    status = args.status or payload.get("status")
    if not task_id or status not in STATUSES:
        return 2
    event = {
        "task_id": int(task_id),
        "status": status,
        "summary": args.summary or payload.get("summary", "") or datetime.now().strftime("%m-%d %H:%M"),
    }
    with EVENT_FILE.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
