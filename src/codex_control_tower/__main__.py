"""Package entry point for ``python -m codex_control_tower``."""

from .paths import migrate_legacy_runtime


def main():
    migrate_legacy_runtime()
    from .ui import main as run_ui

    run_ui()


if __name__ == "__main__":
    main()
