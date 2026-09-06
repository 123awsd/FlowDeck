"""Versioned curriculum loading, validation and local learning progress."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .paths import DATA_DIR, PROJECT_ROOT


CURRICULUM_ROOT = PROJECT_ROOT / "learning" / "domains"
PROGRESS_FILE = DATA_DIR / "curriculum_progress.json"
PATH_LABELS = {
    "minimum_path": "核心路线",
    "standard_path": "标准路线",
    "research_path": "研究路线",
}
STATE_LABELS = {
    "unlearned": "未学习",
    "learning": "还不清楚",
    "understood": "已理解",
    "deep": "稍后深入",
}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _version_key(path: Path):
    match = re.search(r"_v(\d+)\.json$", path.name)
    return int(match.group(1)) if match else 0


def validate_bundle(directory: Path):
    """Validate identifiers, references, module membership and DAG structure."""
    errors, warnings = [], []
    curriculum_files = sorted(directory.glob("curriculum_v*.json"), key=_version_key)
    if not curriculum_files:
        return {"ok": False, "errors": ["缺少 curriculum_v*.json"], "warnings": []}
    curriculum_path = curriculum_files[-1]
    sources_path = directory / "sources.json"
    try:
        curriculum = _read_json(curriculum_path)
    except Exception as exc:
        return {"ok": False, "errors": [f"课程 JSON 无法解析：{exc}"], "warnings": []}
    try:
        sources = _read_json(sources_path)
    except Exception as exc:
        return {"ok": False, "errors": [f"来源 JSON 无法解析：{exc}"], "warnings": []}

    source_rows = sources.get("sources", [])
    source_ids = [row.get("id") for row in source_rows]
    source_set = set(source_ids)
    if None in source_set or len(source_set) != len(source_ids):
        errors.append("source id 缺失或重复")
    for row in source_rows:
        if not row.get("url"):
            errors.append(f"来源 {row.get('id', '?')} 缺少 URL")

    modules = curriculum.get("modules", [])
    concepts = curriculum.get("concepts", [])
    module_ids = [row.get("id") for row in modules]
    concept_ids = [row.get("id") for row in concepts]
    module_set, concept_set = set(module_ids), set(concept_ids)
    if None in module_set or len(module_set) != len(module_ids):
        errors.append("module id 缺失或重复")
    if None in concept_set or len(concept_set) != len(concept_ids):
        errors.append("concept id 缺失或重复")

    for source_id in curriculum.get("source_ids", []):
        if source_id not in source_set:
            errors.append(f"课程引用未知来源：{source_id}")
    module_members = {}
    for module in modules:
        for concept_id in module.get("concept_ids", []):
            if concept_id not in concept_set:
                errors.append(f"模块 {module.get('id')} 引用未知节点：{concept_id}")
            if concept_id in module_members:
                errors.append(f"节点 {concept_id} 同时出现在多个模块")
            module_members[concept_id] = module.get("id")

    graph = {concept_id: [] for concept_id in concept_ids if concept_id}
    for concept in concepts:
        concept_id = concept.get("id", "?")
        module_id = concept.get("module_id")
        if module_id not in module_set:
            errors.append(f"节点 {concept_id} 引用未知模块：{module_id}")
        if module_members.get(concept_id) != module_id:
            errors.append(f"节点 {concept_id} 的 module_id 与模块目录不一致")
        if concept.get("priority") not in {"P0", "P1", "P2"}:
            errors.append(f"节点 {concept_id} 的优先级无效")
        if concept.get("stability") not in {"foundation", "evolving", "frontier"}:
            errors.append(f"节点 {concept_id} 的稳定性无效")
        if not concept.get("source_ids"):
            errors.append(f"节点 {concept_id} 没有来源")
        for source_id in concept.get("source_ids", []):
            if source_id not in source_set:
                errors.append(f"节点 {concept_id} 引用未知来源：{source_id}")
        for relation in ("prerequisites", "related_concepts"):
            for target in concept.get(relation, []):
                if target not in concept_set:
                    errors.append(f"节点 {concept_id} 的 {relation} 引用未知节点：{target}")
        graph[concept_id] = list(concept.get("prerequisites", []))

    visiting, visited = set(), set()

    def visit(node):
        if node in visiting:
            errors.append(f"前置依赖存在环：{node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for parent in graph.get(node, []):
            visit(parent)
        visiting.remove(node)
        visited.add(node)

    for concept_id in graph:
        visit(concept_id)

    for path_name, path in curriculum.get("recommended_paths", {}).items():
        if len(path) != len(set(path)):
            errors.append(f"{path_name} 存在重复节点")
        positions = {concept_id: index for index, concept_id in enumerate(path)}
        for concept_id in path:
            if concept_id not in concept_set:
                errors.append(f"{path_name} 引用未知节点：{concept_id}")
                continue
            for parent in graph.get(concept_id, []):
                if parent in positions and positions[parent] > positions[concept_id]:
                    errors.append(f"{path_name} 中 {parent} 晚于依赖它的 {concept_id}")
                elif parent not in positions:
                    warnings.append(f"{path_name} 未包含 {concept_id} 的前置节点 {parent}")

    return {
        "ok": not errors,
        "errors": list(dict.fromkeys(errors)),
        "warnings": list(dict.fromkeys(warnings)),
        "curriculum_path": curriculum_path,
        "sources_path": sources_path,
        "curriculum": curriculum,
        "sources": sources,
        "counts": {"modules": len(modules), "concepts": len(concepts), "sources": len(source_rows)},
    }


class CurriculumLibrary:
    def __init__(self, root=CURRICULUM_ROOT):
        self.root = Path(root)
        self._bundles = {}
        self.reload()

    def reload(self):
        self._bundles = {}
        if not self.root.exists():
            return
        for directory in sorted(path for path in self.root.iterdir() if path.is_dir()):
            report = validate_bundle(directory)
            if not report.get("ok"):
                continue
            curriculum = report["curriculum"]
            domain = curriculum.get("domain", {})
            domain_id = domain.get("id") or directory.name
            concepts = curriculum.get("concepts", [])
            sources = report["sources"].get("sources", [])
            self._bundles[domain_id] = {
                "id": domain_id,
                "directory": directory,
                "curriculum_path": report["curriculum_path"],
                "readable_path": directory / f"curriculum_{domain.get('version', 'v1')}.md",
                "review_path": directory / f"review_{domain.get('version', 'v1')}.md",
                "domain": domain,
                "modules": curriculum.get("modules", []),
                "concepts": concepts,
                "concept_by_id": {row["id"]: row for row in concepts},
                "source_by_id": {row["id"]: row for row in sources},
                "recommended_paths": curriculum.get("recommended_paths", {}),
                "validation": report,
            }

    def domains(self):
        return list(self._bundles.values())

    def get(self, domain_id):
        return self._bundles.get(domain_id)

    @staticmethod
    def path(bundle, path_name):
        path = list(bundle.get("recommended_paths", {}).get(path_name, []))
        if path:
            return [concept_id for concept_id in path if concept_id in bundle["concept_by_id"]]
        ordered = []
        for module in sorted(bundle["modules"], key=lambda row: row.get("order", 0)):
            ordered.extend(module.get("concept_ids", []))
        return [concept_id for concept_id in ordered if concept_id in bundle["concept_by_id"]]


class CurriculumStore:
    def __init__(self, path=PROGRESS_FILE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self):
        try:
            value = _read_json(self.path)
            if isinstance(value, dict):
                return value
        except Exception:
            pass
        return {"schema_version": 1, "selected_domain": "vla", "curricula": {}}

    def _save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _key(bundle):
        return f"{bundle['id']}:{bundle['domain'].get('version', 'v1')}"

    def record(self, bundle):
        return self.data.setdefault("curricula", {}).setdefault(
            self._key(bundle), {"approved_at": None, "path": "standard_path", "current": None, "concepts": {}}
        )

    def approved(self, bundle):
        return bool(self.record(bundle).get("approved_at"))

    def approve(self, bundle):
        self.record(bundle)["approved_at"] = datetime.now().isoformat(timespec="seconds")
        self._save()

    def selected_domain(self):
        return self.data.get("selected_domain", "vla")

    def select_domain(self, domain_id):
        self.data["selected_domain"] = domain_id
        self._save()

    def selected_path(self, bundle):
        value = self.record(bundle).get("path", "standard_path")
        return value if value in PATH_LABELS else "standard_path"

    def select_path(self, bundle, path_name):
        self.record(bundle)["path"] = path_name
        self.record(bundle)["current"] = None
        self._save()

    def state(self, bundle, concept_id):
        return self.record(bundle).get("concepts", {}).get(concept_id, {}).get("state", "unlearned")

    def set_state(self, bundle, concept_id, state):
        if state not in STATE_LABELS:
            return
        row = self.record(bundle).setdefault("concepts", {}).setdefault(concept_id, {})
        row.update({"state": state, "updated_at": datetime.now().isoformat(timespec="seconds")})
        if state == "learning":
            row["unclear_count"] = int(row.get("unclear_count", 0)) + 1
        self._save()

    def current(self, bundle, path):
        record = self.record(bundle)
        current = record.get("current")
        if current in path:
            return current
        current = next((concept_id for concept_id in path if self.state(bundle, concept_id) not in {"understood", "deep"}), path[0] if path else None)
        record["current"] = current
        self._save()
        return current

    def set_current(self, bundle, concept_id):
        self.record(bundle)["current"] = concept_id
        self._save()

    def advance(self, bundle, path, concept_id):
        if not path:
            return None
        try:
            start = path.index(concept_id) + 1
        except ValueError:
            start = 0
        current = next((item for item in path[start:] if self.state(bundle, item) not in {"understood", "deep"}), None)
        if current is None:
            current = next((item for item in path if self.state(bundle, item) not in {"understood", "deep"}), path[-1])
        self.set_current(bundle, current)
        return current

    def stats(self, bundle, path):
        states = [self.state(bundle, concept_id) for concept_id in path]
        mastered = sum(state in {"understood", "deep"} for state in states)
        return {"total": len(path), "mastered": mastered, "percent": round(mastered / len(path) * 100) if path else 0}
