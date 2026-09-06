"""Bounded local storage for project-scoped ideas."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from .paths import DATA_DIR


IDEAS_FILE = DATA_DIR / "project_ideas.json"
MAX_IDEAS = 1000


class ProjectIdeaStore:
    def __init__(self, path=IDEAS_FILE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        self.data = payload if isinstance(payload, dict) else {}
        self.data.setdefault("schema_version", 1)
        self.data.setdefault("ideas", [])

    def list(self, project_path, include_done=True):
        rows = [row for row in self.data["ideas"] if row.get("project_path") == project_path]
        if not include_done:
            rows = [row for row in rows if not row.get("done")]
        rows.sort(key=lambda row: row.get("updated_at", row.get("created_at", "")), reverse=True)
        rows.sort(key=lambda row: bool(row.get("done")))
        return rows

    def add(self, project_path, project, text):
        text = str(text or "").strip()
        if not project_path or not text:
            return None
        now = datetime.now().isoformat(timespec="seconds")
        row = {"id": uuid.uuid4().hex, "project_path": project_path, "project": project, "text": text, "done": False, "created_at": now, "updated_at": now}
        self.data["ideas"].append(row)
        self._save()
        return row

    def update(self, idea_id, text):
        row = self._get(idea_id); text = str(text or "").strip()
        if not row or not text:
            return False
        row["text"] = text; row["updated_at"] = datetime.now().isoformat(timespec="seconds"); self._save(); return True

    def toggle(self, idea_id, done):
        row = self._get(idea_id)
        if not row:
            return False
        row["done"] = bool(done); row["updated_at"] = datetime.now().isoformat(timespec="seconds"); self._save(); return True

    def delete(self, idea_id):
        before = len(self.data["ideas"]); self.data["ideas"] = [row for row in self.data["ideas"] if row.get("id") != idea_id]
        if len(self.data["ideas"]) == before:
            return False
        self._save(); return True

    def _get(self, idea_id):
        return next((row for row in self.data["ideas"] if row.get("id") == idea_id), None)

    def _save(self):
        rows = self.data["ideas"]
        if len(rows) > MAX_IDEAS:
            open_rows = sorted((row for row in rows if not row.get("done")), key=lambda row: row.get("updated_at", ""), reverse=True)
            done_rows = sorted((row for row in rows if row.get("done")), key=lambda row: row.get("updated_at", ""), reverse=True)
            self.data["ideas"] = (open_rows + done_rows)[:MAX_IDEAS]
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
