"""Central project paths and the one-time runtime-data migration."""

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
ASSETS_DIR = PROJECT_ROOT / "assets"
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
EXTENSIONS_DIR = PROJECT_ROOT / "extensions"
ENV_FILE = PROJECT_ROOT / ".env"

LEGACY_RUNTIME_FILES = (
    "tasks.json",
    "daily_todos.json",
    "seen_sessions.json",
    "events.jsonl",
    "learning_feed.json",
    "learning_state.json",
    "learning.db",
    "learning.db-shm",
    "learning.db-wal",
)


def ensure_runtime_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def migrate_legacy_runtime():
    """Move pre-0.3 root-level state into data/ without overwriting data."""
    ensure_runtime_dirs()
    for name in LEGACY_RUNTIME_FILES:
        source = PROJECT_ROOT / name
        target = DATA_DIR / name
        if source.exists() and not target.exists():
            source.replace(target)
