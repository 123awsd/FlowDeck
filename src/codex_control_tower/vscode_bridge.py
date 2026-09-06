"""Package and install the local VS Code bridge used by the tower."""

import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .paths import PROJECT_ROOT


BRIDGE_SOURCE = PROJECT_ROOT / "extensions" / "vscode-bridge"
EXTENSIONS_DIR = Path.home() / ".vscode/extensions"


def bridge_version():
    try:
        return json.loads((BRIDGE_SOURCE / "package.json").read_text(encoding="utf-8"))["version"]
    except (OSError, KeyError, json.JSONDecodeError):
        return ""


def installed_bridge_matches():
    version = bridge_version()
    installed = EXTENSIONS_DIR / f"local.codex-window-bridge-{version}"
    if not version or not installed.is_dir():
        return False
    try:
        return all(
            (installed / name).read_bytes() == (BRIDGE_SOURCE / name).read_bytes()
            for name in ("package.json", "extension.js")
        )
    except OSError:
        return False


def _build_vsix(destination):
    files = {
        "extension/package.json": BRIDGE_SOURCE / "package.json",
        "extension/extension.js": BRIDGE_SOURCE / "extension.js",
        "extension.vsixmanifest": BRIDGE_SOURCE / "extension.vsixmanifest",
        "[Content_Types].xml": BRIDGE_SOURCE / "[Content_Types].xml",
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for archive_name, source in files.items():
            archive.write(source, archive_name)


def ensure_bridge_installed(force=False):
    """Install/update the bridge; VS Code hot-activates it in open windows."""
    required = ("package.json", "extension.js", "extension.vsixmanifest", "[Content_Types].xml")
    if not all((BRIDGE_SOURCE / name).is_file() for name in required):
        return False, "仓库中缺少 VS Code 桥接扩展文件"
    if not force and installed_bridge_matches():
        return True, ""
    code = shutil.which("code")
    if not code:
        return False, "未找到 VS Code 命令行程序"
    try:
        with tempfile.TemporaryDirectory(prefix="codex-window-bridge-") as directory:
            package = Path(directory) / f"codex-window-bridge-{bridge_version()}.vsix"
            _build_vsix(package)
            result = subprocess.run(
                [code, "--install-extension", str(package), "--force"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=25,
            )
        if result.returncode:
            return False, (result.stderr.strip() or "VS Code 拒绝安装桥接")
        return True, ""
    except (OSError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        return False, str(error)
