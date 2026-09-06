#!/usr/bin/env python3
"""Validate a versioned curriculum bundle before it is enabled in the UI."""

import argparse
from pathlib import Path

from codex_control_tower.curriculum import validate_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    report = validate_bundle(args.directory)
    counts = report.get("counts", {})
    print(f"sources={counts.get('sources', 0)} modules={counts.get('modules', 0)} concepts={counts.get('concepts', 0)}")
    for warning in report.get("warnings", []):
        print(f"WARNING: {warning}")
    for error in report.get("errors", []):
        print(f"ERROR: {error}")
    print("OK" if report.get("ok") else "FAILED")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
