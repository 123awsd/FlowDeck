"""Shared visual language for the cozy control-tower interface."""

INK = "#273142"
INK_SOFT = "#556176"
MUTED = "#7f8999"
SURFACE = "#fffefa"
CANVAS = "#fbfaf7"
BORDER = "#e7ded5"

PAGE = {
    "monitor": {"bg": "#f4f9ff", "border": "#dbe9f6", "accent": "#6f9fd2", "soft": "#e6f2ff", "ink": "#3f6f9e"},
    "todo": {"bg": "#fff9ee", "border": "#f3dfb9", "accent": "#d49a58", "soft": "#fff0d2", "ink": "#865b2c"},
    "learn": {"bg": "#f8f5ff", "border": "#e6def4", "accent": "#8f7bc2", "soft": "#eee8fb", "ink": "#685a94"},
    "system": {"bg": "#f2faf6", "border": "#d5eadf", "accent": "#61a78b", "soft": "#e4f5ed", "ink": "#3d7863"},
}


def app_stylesheet():
    return f"""
    QWidget {{ font-family:'Noto Sans CJK SC'; font-size:13px; color:{INK}; }}
    QWidget#root {{ background:transparent; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background:transparent; border:0; }}
    QScrollBar:vertical {{ background:transparent; width:8px; margin:3px 1px; }}
    QScrollBar::handle:vertical {{ background:#d6d7dc; min-height:28px; border-radius:4px; }}
    QScrollBar::handle:vertical:hover {{ background:#bfc3ca; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
    QPushButton, QToolButton {{ padding:7px 12px; background:{SURFACE}; border:1px solid {BORDER}; border-radius:9px; color:#465064; }}
    QPushButton:hover, QToolButton:hover {{ background:#fff7ed; border-color:#d9cabe; }}
    QPushButton:pressed, QToolButton:pressed {{ background:#f7eee5; }}
    QPushButton:disabled, QToolButton:disabled {{ color:#a8adb6; background:#f5f2ee; border-color:#ece7e1; }}
    QToolButton::menu-indicator {{ image:none; }}
    QLineEdit, QPlainTextEdit, QComboBox {{ padding:7px; background:{SURFACE}; border:1px solid {BORDER}; border-radius:9px; selection-background-color:#b9d8f5; }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color:#9ec5e9; }}
    QComboBox::drop-down {{ border:0; width:22px; }}
    QMenu {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:10px; padding:6px; }}
    QMenu::item {{ padding:8px 24px 8px 12px; border-radius:7px; }}
    QMenu::item:selected {{ background:#edf5ff; color:#3e6f9f; }}
    QProgressBar {{ height:6px; border:0; border-radius:3px; background:#e8e5e1; text-align:center; }}
    QProgressBar::chunk {{ border-radius:3px; background:#75b89e; }}
    QToolTip {{ color:{INK}; background:{SURFACE}; border:1px solid {BORDER}; padding:5px; }}
    QTableWidget {{ border:0; background:{SURFACE}; alternate-background-color:#faf7f3; color:{INK}; gridline-color:#eee8e2; }}
    QHeaderView::section {{ background:#f3efea; color:{INK_SOFT}; border:0; padding:6px; font-size:10px; font-weight:700; }}
    """


def dialog_stylesheet(accent="learn"):
    color = PAGE[accent]
    return app_stylesheet() + f"""
    QDialog {{ background:{CANVAS}; }}
    QFrame#dialogCard, QFrame#metricCard {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:12px; }}
    """


def panel_style(name):
    color = PAGE[name]
    return f"QFrame#{name}Panel{{background:{color['bg']};border:1px solid {color['border']};border-radius:14px}} QFrame#{name}Panel QLabel{{background:transparent;border:0}}"


def button_style(name, primary=False):
    color = PAGE[name]
    if primary:
        return f"QPushButton{{background:{color['accent']};color:white;border:0;border-radius:9px;font-weight:700}} QPushButton:hover{{background:{color['ink']}}}"
    return f"QPushButton,QToolButton{{background:{color['soft']};color:{color['ink']};border:1px solid {color['border']};border-radius:9px;font-weight:700}} QPushButton:hover,QToolButton:hover{{background:{color['bg']}}}"


def badge_style(name):
    color = PAGE[name]
    return f"color:{color['ink']};background:{color['soft']};padding:4px 8px;border-radius:6px;font-size:10px;font-weight:700"
