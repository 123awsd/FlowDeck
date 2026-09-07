"""Audited local routing for Codex VS Code child processes.

Only the child process' CODEX_HOME is changed. Provider homes never share
writable databases, locks, IPC sockets, logs, or session directories.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path


BRIDGE_DIR = Path.home() / ".codex-window-manager"
WRAPPER = BRIDGE_DIR / "codex-provider-wrapper.py"
PATCH_MARKER = "__codexTowerWrapper"
PATCH_TARGET = 'function QP(t,e){let r=pn("cliExecutable");'
PATCH_REPLACEMENT = (
    'function QP(t,e){let __codexTowerWrapper=require("node:path").join('
    'require("node:os").homedir(),".codex-window-manager","codex-provider-wrapper.py");'
    'if(require("node:fs").existsSync(__codexTowerWrapper))return __codexTowerWrapper;'
    'let r=pn("cliExecutable");'
)

# A patch is enabled only for a byte-for-byte reviewed upstream file.
SUPPORTED_EXTENSIONS = {
    "26.5901.22334": "e8d3bb57b73a1fd316fd557859aec56e540b48de3489012d1952fa4a2e371208",
}

WRAPPER_SOURCE = r'''#!/usr/bin/env python3
import glob
import fcntl
import json
import os
import sys
import time
from pathlib import Path

root = Path.home() / ".codex-window-manager"
parent = os.getppid()
provider = "subscription"
codex_home = ""
marker = root / "hosts" / f"{parent}.json"
try:
    route = json.loads(marker.read_text(encoding="utf-8"))
    if time.time() - float(route.get("at", 0)) / 1000 <= 15:
        provider = route.get("provider", "subscription")
        codex_home = route.get("codexHome", "")
except Exception:
    pass

# During an extension-host restart the Codex extension can start before the
# bridge receives its new PID. A short-lived, single-consumer ticket carries
# the already validated target route across that one restart.
ticket = root / "pending-launch.json"
lock_path = root / "pending-launch.lock"
try:
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        value = json.loads(ticket.read_text(encoding="utf-8"))
        if time.time() - float(value.get("at", 0)) / 1000 <= 15:
            provider = value.get("provider", "subscription")
            codex_home = value.get("codexHome", "")
            ticket.unlink()
except Exception:
    pass

if provider != "subscription" and codex_home and Path(codex_home).is_dir():
    os.environ["CODEX_HOME"] = codex_home
else:
    provider = "subscription"
    codex_home = ""
    os.environ.pop("CODEX_HOME", None)

try:
    receipts = root / "launches"
    receipts.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for old in receipts.glob("*.json"):
        if now - old.stat().st_mtime > 86400:
            old.unlink()
    receipt = receipts / f"{parent}-{os.getpid()}.json"
    temporary = receipt.with_suffix(".tmp")
    temporary.write_text(json.dumps({
        "parent": parent, "child": os.getpid(), "provider": provider,
        "codexHome": codex_home, "at": int(now * 1000)
    }), encoding="utf-8")
    os.replace(temporary, receipt)
except Exception:
    pass

candidates = glob.glob(str(Path.home() / ".vscode/extensions/openai.chatgpt-*/bin/*/codex"))
if not candidates:
    raise SystemExit("Codex executable not found")
binary = max(candidates, key=os.path.getmtime)
os.execve(binary, [binary, *sys.argv[1:]], os.environ)
'''


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest_extension() -> tuple[Path, str] | tuple[None, None]:
    candidates = list((Path.home() / ".vscode/extensions").glob("openai.chatgpt-*/out/extension.js"))
    if not candidates:
        return None, None
    target = max(candidates, key=lambda item: item.stat().st_mtime)
    manifest = target.parent.parent / "package.json"
    try:
        version = str(json.loads(manifest.read_text(encoding="utf-8"))["version"])
    except (OSError, ValueError, KeyError):
        return target, None
    return target, version


def ensure_provider_routing_patch() -> tuple[bool, str]:
    """Install the wrapper and patch only a reviewed Codex extension build."""
    target, version = _latest_extension()
    if target is None:
        return False, "未找到已安装的 Codex VS Code 扩展"
    expected = SUPPORTED_EXTENSIONS.get(version or "")
    if not expected:
        return False, f"Codex 扩展 {version or '未知版本'} 尚未通过兼容性检查"
    try:
        source = target.read_text(encoding="utf-8")
        if PATCH_MARKER in source:
            if source.count(PATCH_MARKER) < 2:
                return False, "Codex 扩展中的路由补丁形态异常"
        else:
            actual = _sha256(target)
            if actual != expected:
                return False, "Codex 扩展文件与已审核版本不一致，已停止 API 切换"
            if source.count(PATCH_TARGET) != 1:
                return False, "Codex 扩展启动位置不唯一，已停止 API 切换"

        BRIDGE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary_wrapper = WRAPPER.with_suffix(f".tmp.{os.getpid()}")
        temporary_wrapper.write_text(WRAPPER_SOURCE, encoding="utf-8")
        temporary_wrapper.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        os.replace(temporary_wrapper, WRAPPER)

        if PATCH_MARKER in source:
            return True, ""
        patched = source.replace(PATCH_TARGET, PATCH_REPLACEMENT, 1)
        backup_dir = BRIDGE_DIR / "extension-backups"
        backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        backup = backup_dir / f"openai-chatgpt-{version}-{expected[:12]}.js"
        if not backup.exists():
            backup.write_text(source, encoding="utf-8")
        for old in sorted(backup_dir.glob("openai-chatgpt-*.js"), key=lambda p: p.stat().st_mtime, reverse=True)[3:]:
            old.unlink()
        temporary = target.with_name(f"extension.tmp.{os.getpid()}.js")
        temporary.write_text(patched, encoding="utf-8")
        code_wrapper = Path(shutil.which("code") or "/usr/bin/code")
        try:
            resolved = code_wrapper.resolve()
        except OSError:
            resolved = code_wrapper
        checker = resolved.parent.parent / "code" if resolved.parent.name == "bin" else resolved
        check_env = dict(os.environ)
        check_env["ELECTRON_RUN_AS_NODE"] = "1"
        check = subprocess.run([str(checker), "--check", str(temporary)], env=check_env, capture_output=True, text=True, timeout=20)
        if check.returncode:
            temporary.unlink(missing_ok=True)
            return False, "Codex 扩展补丁语法校验失败"
        os.replace(temporary, target)
        return True, ""
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)


def assert_independent_provider_home(home: str | Path) -> tuple[bool, str]:
    """Reject incomplete credentials or provider homes sharing writable state."""
    root = Path(home).expanduser()
    if not (root / "config.toml").is_file() or not (root / "auth.json").is_file():
        return False, "缺少 config.toml 或 auth.json"
    try:
        auth = json.loads((root / "auth.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "auth.json 无法读取"
    if auth.get("auth_mode") != "apikey" or not str(auth.get("OPENAI_API_KEY", "")).strip():
        return False, "尚未在这个 API 目录中保存有效的 API Key"
    unsafe = []
    for child in root.iterdir():
        if child.is_symlink():
            unsafe.append(child.name)
    if unsafe:
        return False, "存在共享符号链接：" + "、".join(sorted(unsafe))
    return True, ""
