#!/usr/bin/env bash
cd "/home/uav/桌面/codex管理" || exit 1
## Use system Qt5/PyQt5, whose Fcitx5 platform plugin matches the desktop Qt.
## The UI code remains the same; only the Qt runtime/input backend changes.
export QT_IM_MODULE=fcitx
export GTK_IM_MODULE=fcitx
export XMODIFIERS=@im=fcitx
exec /usr/bin/python3 app.py
