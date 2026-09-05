#!/usr/bin/env python3
"""Codex Control Tower - a small, dependency-free floating task board."""

from __future__ import annotations

import json
import os
import subprocess
try:
    from app_qt import main as qt_main
except ImportError:
    qt_main = None

# Prefer Qt's antialiased CJK text renderer. Tk on this machine exposes only
# legacy bitmap CJK aliases, which is the source of the blurry glyphs.
if qt_main is not None and __name__ == "__main__":
    qt_main()
    raise SystemExit

import tkinter as tk
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

# Some VS Code terminals launch Python with LC_CTYPE=C.UTF-8. Tk then cannot
# select CJK glyphs even when the font is installed, so normalize the locale
# before creating the first Tk interpreter.
os.environ["LANG"] = "zh_CN.UTF-8"
os.environ["LC_CTYPE"] = "zh_CN.UTF-8"


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "tasks.json"
EVENT_FILE = BASE_DIR / "events.jsonl"
STATUSES = ["Running", "Needs input", "Ready", "Blocked", "Done"]
STATUS_LABELS = {
    "Running": "执行中",
    "Needs input": "需要输入",
    "Ready": "已就绪",
    "Blocked": "已阻塞",
    "Done": "已完成",
}
STATUS_COLORS = {
    "Running": "#2f80ed",
    "Needs input": "#f2994a",
    "Ready": "#27ae60",
    "Blocked": "#eb5757",
    "Done": "#828282",
}
# WenQuanYi is installed as a native bitmap/outline family in the desktop
# session and renders simplified Chinese reliably in Tk (Noto's TTC fallback
# produced tofu boxes on some Linux Tk builds).
UI_FONT = "song ti"


@dataclass
class Task:
    id: int
    title: str
    project: str
    path: str
    account: str = "Plus-1"
    status: str = "Running"
    window_title: str = ""
    window_id: str = ""
    updated_at: str = "刚刚"


@dataclass
class VSCodeWindow:
    window_id: str
    pid: str
    wm_class: str
    title: str
    folder: str
    folder_path: str = ""


def now_label() -> str:
    return datetime.now().strftime("%m-%d %H:%M")


class ControlTower(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Codex 任务总控台")
        self.configure(bg="#111827")
        self.attributes("-topmost", True)
        # Use a real CJK font for every Tk widget; the default Sans fallback
        # is what caused Chinese glyphs to look thin or blurred.
        self.option_add("*Font", (UI_FONT, 11))
        self.minsize(420, 80)
        self.expanded = False
        self.tasks: list[Task] = []
        self.windows: list[VSCodeWindow] = []
        self.codex_processes: list[str] = []
        self.event_offset = 0
        self.load_tasks()
        self.discover_windows()
        self.detect_codex_processes()
        self.build_shell()
        self.render()
        self.bind("<Control-Alt-c>", lambda _event: self.toggle())
        self.after(5000, self.auto_refresh)
        self.after(1500, self.poll_events)

    def load_tasks(self) -> None:
        if not DATA_FILE.exists():
            return
        try:
            raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            self.tasks = [Task(**item) for item in raw]
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showwarning("任务数据读取失败", f"将使用空看板。\n{exc}")

    def save_tasks(self) -> None:
        DATA_FILE.write_text(
            json.dumps([asdict(task) for task in self.tasks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def build_shell(self) -> None:
        self.header = tk.Frame(self, bg="#111827", padx=14, pady=10)
        self.header.pack(fill="x")
        self.title_label = tk.Label(
            self.header, text="◉  Codex 任务总控台", fg="#f9fafb", bg="#111827",
            font=(UI_FONT, 16, "bold"), anchor="w",
        )
        self.title_label.pack(side="left")
        self.toggle_button = tk.Button(
            self.header, text="展开", command=self.toggle, bg="#2563eb", fg="white",
            activebackground="#1d4ed8", activeforeground="white", relief="flat", padx=10,
        )
        self.toggle_button.pack(side="right")
        self.scan_button = tk.Button(
            self.header, text="扫描 VS Code", command=self.scan_and_render,
            bg="#374151", fg="white", activebackground="#4b5563", activeforeground="white",
            relief="flat", padx=8,
        )
        self.scan_button.pack(side="right", padx=(0, 7))
        self.summary = tk.Label(
            self.header, fg="#d1d5db", bg="#111827", font=(UI_FONT, 12),
            anchor="w", width=52,
        )
        self.summary.pack(side="left", padx=(12, 0), fill="x", expand=True)

        self.body = tk.Frame(self, bg="#f3f4f6", padx=12, pady=10)
        self.canvas = tk.Canvas(self.body, bg="#f3f4f6", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.body, orient="vertical", command=self.canvas.yview)
        self.list_frame = tk.Frame(self.canvas, bg="#f3f4f6")
        self.list_frame.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(self.canvas_window, width=event.width),
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.add_panel = tk.Frame(self.list_frame, bg="#e5e7eb", padx=8, pady=8)

    def toggle(self) -> None:
        self.expanded = not self.expanded
        if self.expanded:
            self.geometry("760x600")
            self.body.pack(fill="both", expand=True)
            self.toggle_button.configure(text="收起")
        else:
            self.body.pack_forget()
            self.geometry("820x110")
            self.toggle_button.configure(text="展开")
        self.render()

    def render(self) -> None:
        counts = {status: sum(t.status == status for t in self.tasks) for status in STATUSES}
        self.summary.configure(
            text=f"窗口 {len(self.windows)}  ·  Codex 进程 {len(self.codex_processes)}  ·  执行中 {counts['Running']}  ·  需输入 {counts['Needs input']}  ·  已就绪 {counts['Ready']}"
        )
        if self.windows:
            names = " / ".join(window.folder for window in self.windows)
            self.summary.configure(text=f"{self.summary.cget('text')}   |   {names[:70]}")
        if not self.expanded:
            return
        for child in self.list_frame.winfo_children():
            child.destroy()
        self.render_windows()
        for task in self.tasks:
            self.render_task(task)
        if not self.tasks:
            tk.Label(self.list_frame, text="还没有任务，下面添加一个。", bg="#f3f4f6", fg="#6b7280", font=(UI_FONT, 11)).pack(pady=20)
        self.add_panel = tk.Frame(self.list_frame, bg="#e5e7eb", padx=8, pady=8)
        self.render_add_panel()

    def render_task(self, task: Task) -> None:
        card = tk.Frame(self.list_frame, bg="white", bd=0, padx=10, pady=9)
        card.pack(fill="x", pady=(0, 8))
        top = tk.Frame(card, bg="white")
        top.pack(fill="x")
        tk.Label(top, text=task.title, bg="white", fg="#111827", font=(UI_FONT, 11, "bold")).pack(side="left")
        tk.Label(top, text=STATUS_LABELS.get(task.status, task.status), bg=STATUS_COLORS.get(task.status, "#6b7280"), fg="white", padx=7).pack(side="right")
        binding = "窗口已绑定" if task.window_id else "未绑定窗口"
        info = f"{task.project}   ·   {task.account}   ·   {task.updated_at}   ·   {binding}"
        tk.Label(card, text=info, bg="white", fg="#6b7280", anchor="w", font=(UI_FONT, 11)).pack(fill="x", pady=(4, 5))
        status_help = {
            "Running": "正在执行（目前由看板状态记录）",
            "Needs input": "等待你回答或授权",
            "Ready": "本轮已结束，等待你检查",
            "Blocked": "遇到错误或无法继续",
            "Done": "你已确认完成",
        }
        tk.Label(card, text=status_help.get(task.status, ""), bg="white", fg=STATUS_COLORS.get(task.status, "#6b7280"), anchor="w", font=(UI_FONT, 9)).pack(fill="x")
        actions = tk.Frame(card, bg="white")
        actions.pack(fill="x")
        tk.Button(actions, text="跳转 VS Code", command=lambda t=task: self.jump_to_vscode(t), relief="flat", bg="#dbeafe", fg="#1d4ed8").pack(side="left")
        tk.Button(actions, text="状态 ▾", command=lambda t=task: self.cycle_status(t), relief="flat", bg="#f3f4f6").pack(side="left", padx=6)
        tk.Button(actions, text="删除", command=lambda t=task: self.delete_task(t), relief="flat", bg="#fef2f2", fg="#b91c1c").pack(side="right")
        if task.path:
            tk.Label(card, text=task.path, bg="white", fg="#9ca3af", anchor="w", font=(UI_FONT, 8)).pack(fill="x")

    def render_windows(self) -> None:
        panel = tk.Frame(self.list_frame, bg="#e0f2fe", padx=10, pady=8)
        panel.pack(fill="x", pady=(0, 10))
        tk.Label(panel, text=f"当前 VS Code 窗口（{len(self.windows)}） · Codex 进程（{len(self.codex_processes)}）", bg="#e0f2fe", fg="#0c4a6e", font=(UI_FONT, 12, "bold")).pack(anchor="w")
        tk.Label(panel, text="已自动读取窗口标题和项目文件夹名称；逐任务状态可手动更新或由通知回调更新。", bg="#e0f2fe", fg="#075985", font=(UI_FONT, 10)).pack(anchor="w", pady=(2, 0))
        if not self.windows:
            tk.Label(panel, text="没有扫描到窗口。请确认在桌面会话中运行，并点击“扫描 VS Code”。", bg="#e0f2fe", fg="#075985", font=(UI_FONT, 10)).pack(anchor="w", pady=(4, 0))
            return
        for window in self.windows:
            row = tk.Frame(panel, bg="#e0f2fe")
            row.pack(fill="x", pady=(5, 0))
            location = window.folder_path or "路径未记录"
            tk.Label(row, text=f"文件夹：{window.folder}   |   {location}\n窗口：{window.title}", bg="#e0f2fe", fg="#0c4a6e", anchor="w", justify="left", font=(UI_FONT, 11)).pack(side="left", fill="x", expand=True)
            tk.Label(row, text=f"进程 {window.pid}", bg="#e0f2fe", fg="#0369a1", font=(UI_FONT, 10)).pack(side="left", padx=8)
            tk.Button(row, text="聚焦", command=lambda w=window: self.focus_window(w.window_id), relief="flat", bg="white", fg="#0369a1").pack(side="right")
            tk.Button(row, text="建任务", command=lambda w=window: self.create_task_from_window(w), relief="flat", bg="white", fg="#0369a1").pack(side="right", padx=5)

    def render_add_panel(self) -> None:
        self.add_panel.pack(fill="x", pady=(2, 0))
        for child in self.add_panel.winfo_children():
            child.destroy()
        tk.Label(self.add_panel, text="添加任务", bg="#e5e7eb", fg="#111827", font=(UI_FONT, 10, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        self.inputs: dict[str, tk.Entry] = {}
        fields = [("任务名称", "title", 0), ("项目名", "project", 1), ("项目路径", "path", 2), ("窗口标题(可选)", "window_title", 3)]
        for label, key, col in fields:
            tk.Label(self.add_panel, text=label, bg="#e5e7eb", fg="#374151").grid(row=1, column=col, sticky="w")
            entry = tk.Entry(self.add_panel, width=18)
            entry.grid(row=2, column=col, padx=(0, 6), sticky="ew")
            self.inputs[key] = entry
        tk.Label(self.add_panel, text="账号", bg="#e5e7eb", fg="#374151").grid(row=3, column=0, sticky="w", pady=(7, 0))
        self.account_var = tk.StringVar(value="Plus-1")
        ttk.Combobox(self.add_panel, textvariable=self.account_var, values=[f"Plus-{i}" for i in range(1, 6)], width=15, state="readonly").grid(row=4, column=0, sticky="w")
        tk.Label(self.add_panel, text="绑定窗口", bg="#e5e7eb", fg="#374151").grid(row=3, column=1, sticky="w", pady=(7, 0))
        self.window_var = tk.StringVar(value="不绑定")
        self.window_map = {"不绑定": None}
        for window in self.windows:
            label = f"{window.title[:42]} [{window.window_id}]"
            self.window_map[label] = window
        ttk.Combobox(self.add_panel, textvariable=self.window_var, values=list(self.window_map), width=28, state="readonly").grid(row=4, column=1, columnspan=2, sticky="w")
        tk.Button(self.add_panel, text="加入看板", command=self.add_task, relief="flat", bg="#2563eb", fg="white", padx=12).grid(row=4, column=3, sticky="e", pady=(7, 0))
        for col in range(4):
            self.add_panel.columnconfigure(col, weight=1)

    def add_task(self) -> None:
        values = {key: entry.get().strip() for key, entry in self.inputs.items()}
        if not values["title"] or not values["path"]:
            messagebox.showinfo("还差一点", "请至少填写任务名称和项目路径。")
            return
        next_id = max((task.id for task in self.tasks), default=0) + 1
        selected_window = self.window_map.get(self.window_var.get())
        if selected_window:
            values["window_title"] = selected_window.title
        self.tasks.insert(0, Task(id=next_id, account=self.account_var.get(), window_id=selected_window.window_id if selected_window else "", updated_at=now_label(), **values))
        self.save_tasks()
        self.render()

    def cycle_status(self, task: Task) -> None:
        task.status = STATUSES[(STATUSES.index(task.status) + 1) % len(STATUSES)]
        task.updated_at = now_label()
        self.save_tasks()
        self.render()

    def delete_task(self, task: Task) -> None:
        if messagebox.askyesno("删除任务", f"确定删除“{task.title}”吗？"):
            self.tasks.remove(task)
            self.save_tasks()
            self.render()

    def jump_to_vscode(self, task: Task) -> None:
        if not task.path:
            return
        title = task.window_title.strip() or task.project.strip()
        try:
            if task.window_id and self.focus_window(task.window_id):
                return
            if title:
                focused = subprocess.run(["wmctrl", "-a", title], check=False, timeout=2)
                if focused.returncode == 0:
                    return
            subprocess.Popen(["code", "--reuse-window", task.path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror("无法跳转", f"请确认已安装 wmctrl 和 VS Code。\n{exc}")

    def discover_windows(self) -> None:
        self.windows = []
        try:
            result = subprocess.run(["wmctrl", "-l", "-x", "-p"], capture_output=True, text=True, check=False, timeout=3)
        except (OSError, subprocess.SubprocessError):
            return
        for line in result.stdout.splitlines():
            parts = line.split(None, 4)
            if len(parts) < 5:
                continue
            window_id, _desktop, pid, wm_class, remainder = parts
            # wmctrl inserts the client machine name before the actual title.
            title_parts = remainder.split(None, 1)
            title = title_parts[1] if len(title_parts) == 2 else remainder
            class_name = wm_class.lower()
            if class_name.startswith("code.") or "visual studio code" in title.lower():
                clean_title = title.replace(" - Visual Studio Code", "").strip()
                # VS Code puts the workspace/folder name at the end of the title.
                folder = clean_title.split(" - ")[-1].strip() or "未命名项目"
                folder_path = self.resolve_folder_path(folder)
                self.windows.append(VSCodeWindow(window_id, pid, wm_class, clean_title, folder, folder_path))

    @staticmethod
    def resolve_folder_path(folder: str) -> str:
        """Resolve an active workspace name to its folder via VS Code's local workspace records."""
        if BASE_DIR.name == folder:
            return str(BASE_DIR)
        storage = Path.home() / ".config" / "Code" / "User" / "workspaceStorage"
        if not storage.exists():
            return ""
        try:
            for record in storage.glob("*/workspace.json"):
                try:
                    raw = json.loads(record.read_text(encoding="utf-8"))
                    uri = str(raw.get("folder", ""))
                    candidate = uri.removeprefix("file://")
                    if Path(candidate).name == folder:
                        return candidate
                except (OSError, ValueError, TypeError):
                    continue
        except OSError:
            pass
        return ""

    def detect_codex_processes(self) -> None:
        self.codex_processes = []
        try:
            result = subprocess.run(["ps", "-eo", "pid=,comm=,args="], capture_output=True, text=True, check=False, timeout=3)
        except (OSError, subprocess.SubprocessError):
            return
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) >= 2 and parts[1].lower() in {"codex", "codex-cli"}:
                self.codex_processes.append(parts[0])

    def focus_window(self, window_id: str) -> bool:
        try:
            result = subprocess.run(["wmctrl", "-i", "-a", window_id], check=False, timeout=2)
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def create_task_from_window(self, window: VSCodeWindow) -> None:
        next_id = max((task.id for task in self.tasks), default=0) + 1
        project = window.title.replace(" - Visual Studio Code", "").strip() or "VS Code 项目"
        self.tasks.insert(0, Task(id=next_id, title=f"跟进：{project}", project=project, path="", account="Plus-1", status="Running", window_title=window.title, window_id=window.window_id, updated_at=now_label()))
        self.save_tasks()
        self.render()

    def scan_and_render(self) -> None:
        self.discover_windows()
        self.detect_codex_processes()
        self.render()

    def auto_refresh(self) -> None:
        old_windows = [window.window_id for window in self.windows]
        old_processes = list(self.codex_processes)
        self.discover_windows()
        self.detect_codex_processes()
        changed = old_windows != [window.window_id for window in self.windows] or old_processes != self.codex_processes
        # Avoid wiping a half-filled task form while the user is typing.
        form_busy = any(entry.get().strip() for entry in getattr(self, "inputs", {}).values())
        if changed and (not self.expanded or not form_busy):
            self.render()
        self.after(5000, self.auto_refresh)

    def poll_events(self) -> None:
        """Apply optional events emitted by notify_hook.py."""
        try:
            with EVENT_FILE.open("r", encoding="utf-8") as stream:
                stream.seek(self.event_offset)
                lines = stream.readlines()
                self.event_offset = stream.tell()
        except OSError:
            lines = []
        changed = False
        for line in lines:
            try:
                event = json.loads(line)
                task_id = int(event.get("task_id", 0))
                task = next((item for item in self.tasks if item.id == task_id), None)
                if task and event.get("status") in STATUSES:
                    task.status = event["status"]
                    task.updated_at = event.get("summary") or now_label()
                    changed = True
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
        if changed:
            self.save_tasks()
            self.render()
        self.after(1500, self.poll_events)


if __name__ == "__main__":
    app = ControlTower()
    app.geometry("820x110")
    app.mainloop()
