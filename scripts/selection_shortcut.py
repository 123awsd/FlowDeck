#!/usr/bin/python3
"""Forward a GNOME selection shortcut to Control Tower, with legacy fallback."""
import json
import os
import socket
import subprocess
import sys
from pathlib import Path


def selected_text():
    try:
        result = subprocess.run(["xclip", "-o", "-selection", "primary"], capture_output=True,
                                text=True, timeout=2, check=False)
        return result.stdout[:20000].strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "translate"
    if mode not in ("translate", "explain"):
        raise SystemExit(2)
    path = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "codex-control-tower-selection.sock"
    payload = json.dumps({"mode": mode, "text": selected_text()}, ensure_ascii=False).encode("utf-8")
    try:
        sender = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sender.settimeout(0.4)
        sender.sendto(payload, str(path))
        sender.close()
    except OSError:
        legacy = Path.home() / ".local/bin/deepseek-selection-popup"
        if legacy.exists():
            subprocess.Popen([str(legacy), mode], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
