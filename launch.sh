#!/usr/bin/env bash
CONTROL_TOWER_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$CONTROL_TOWER_ROOT" || exit 1
## Use system Qt5/PyQt5, whose Fcitx5 platform plugin matches the desktop Qt.
## The UI code remains the same; only the Qt runtime/input backend changes.
export QT_IM_MODULE=fcitx
export GTK_IM_MODULE=fcitx
export XMODIFIERS=@im=fcitx
export PYTHONPATH="$CONTROL_TOWER_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m codex_control_tower
