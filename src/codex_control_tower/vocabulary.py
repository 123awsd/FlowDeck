"""Local vocabulary parsing and compact spaced-repetition state."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from .paths import DATA_DIR, PROJECT_ROOT


BUILTIN_VOCAB_DIR = PROJECT_ROOT / "learning" / "vocabulary"
USER_VOCAB_DIR = DATA_DIR / "vocabularies"
VOCAB_PROGRESS_FILE = DATA_DIR / "vocabulary_progress.json"
MAX_WORD_STATES = 20_000


def _clean(value):
    return str(value or "").strip().replace("\\n", "\n")


def _entry(lexicon_id, word, meaning, pos="", example="", extra="", category=""):
    word, meaning = _clean(word), _clean(meaning)
    if not word or not meaning:
        return None
    stable = hashlib.sha1(f"{lexicon_id}\0{word.lower()}\0{meaning}".encode()).hexdigest()
    return {
        "id": stable,
        "word": word,
        "meaning": meaning,
        "pos": _clean(pos),
        "example": _clean(example),
        "extra": _clean(extra),
        "category": _clean(category),
        "lexicon_id": lexicon_id,
    }


def parse_vocabulary(path):
    """Parse simple TAB, rich TAB, pipe, and legacy whitespace formats."""
    path = Path(path); lexicon_id = path.stem; rows = []; category = ""
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line in {"===", "+++", "---"}:
            continue
        item = None
        if "|" in line:
            parts = [part.strip() for part in line.split("|")]
            item = _entry(lexicon_id, parts[0] if parts else "", parts[2] if len(parts)>2 else "", parts[1] if len(parts)>1 else "", parts[3] if len(parts)>3 else "", parts[4] if len(parts)>4 else "", category)
        elif "\t" in line:
            parts = [part.strip() for part in line.split("\t")]
            if len(parts)>=3:item = _entry(lexicon_id,parts[0],parts[2],parts[1],parts[3] if len(parts)>3 else "",parts[4] if len(parts)>4 else "",parts[5] if len(parts)>5 else category)
            elif len(parts)>=2:item = _entry(lexicon_id,parts[0],parts[1],category=category)
        else:
            parts = line.split(maxsplit=1)
            if len(parts)==2:item = _entry(lexicon_id,parts[0],parts[1],category=category)
            else:category=line
        if item:rows.append(item)
    seen=set(); unique=[]
    for row in rows:
        key=row["word"].lower()
        if key in seen:continue
        seen.add(key); unique.append(row)
    return unique


class VocabularyLibrary:
    def __init__(self):
        USER_VOCAB_DIR.mkdir(parents=True,exist_ok=True); self._cache={}

    def lexicons(self):
        found={}
        for directory,builtin in ((BUILTIN_VOCAB_DIR,True),(USER_VOCAB_DIR,False)):
            if not directory.exists():continue
            for path in sorted(directory.glob("*.txt")):
                try:count=len(self.load(path))
                except Exception:continue
                if count:found[path.stem]={"id":path.stem,"name":path.stem,"path":path,"count":count,"builtin":builtin}
        return list(found.values())

    def load(self,path):
        path=Path(path); stamp=path.stat().st_mtime_ns; cached=self._cache.get(str(path))
        if cached and cached[0]==stamp:return cached[1]
        rows=parse_vocabulary(path); self._cache[str(path)]=(stamp,rows); return rows

    def get(self,lexicon_id):
        return next((row for row in self.lexicons() if row["id"]==lexicon_id),None)

    def import_file(self,source):
        source=Path(source)
        if source.suffix.lower()!=".txt":raise ValueError("目前只支持 UTF-8 TXT 词库")
        if not parse_vocabulary(source):raise ValueError("没有识别到有效词条，请检查分隔格式和 UTF-8 编码")
        target=USER_VOCAB_DIR/source.name; index=2
        while target.exists() and target.read_bytes()!=source.read_bytes():target=USER_VOCAB_DIR/f"{source.stem}-{index}{source.suffix}"; index+=1
        if not target.exists():shutil.copy2(source,target)
        self._cache.pop(str(target),None); return target.stem


class VocabularyStore:
    def __init__(self,path=VOCAB_PROGRESS_FILE):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        try:value=json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:value={}
        self.data=value if isinstance(value,dict) else {}
        self.data.setdefault("schema_version",1); self.data.setdefault("selected_lexicon",""); self.data.setdefault("words",{}); self._sync_today()

    def _sync_today(self):
        today=date.today().isoformat(); daily=self.data.get("daily",{})
        if daily.get("date")!=today:self.data["daily"]={"date":today,"reviewed":0,"remembered":0,"new":0}

    def _save(self):
        self._sync_today(); words=self.data["words"]
        if len(words)>MAX_WORD_STATES:
            ordered=sorted(words.items(),key=lambda item:item[1].get("last_review",""),reverse=True); self.data["words"]=dict(ordered[:MAX_WORD_STATES])
        temporary=self.path.with_suffix(".tmp"); temporary.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding="utf-8"); temporary.replace(self.path)

    def selected(self,available):
        ids={row["id"] for row in available}; current=self.data.get("selected_lexicon","")
        if current in ids:return current
        preferred=next((item for item in ("文献术语精选_280","雅思词汇真经_扩展","高考3500词汇表") if item in ids),next(iter(ids),"")); self.data["selected_lexicon"]=preferred; self._save(); return preferred

    def select(self,lexicon_id):self.data["selected_lexicon"]=lexicon_id; self._save()
    def state(self,word_id):return self.data["words"].get(word_id,{})
    def toggle_favorite(self,word_id):
        row=self.data["words"].setdefault(word_id,{}); row["favorite"]=not row.get("favorite",False); self._save(); return row["favorite"]

    def rate(self,word_id,rating):
        if rating not in {"forgot","fuzzy","remembered"}:return
        row=self.data["words"].setdefault(word_id,{}); first=not row.get("last_review"); repetitions=int(row.get("repetitions",0)); old_interval=max(0,int(row.get("interval_days",0))); ease=float(row.get("ease",2.3))
        if rating=="forgot":interval=1; repetitions=0; ease=max(1.3,ease-.2); row["lapses"]=int(row.get("lapses",0))+1
        elif rating=="fuzzy":interval=max(2,round(max(1,old_interval)*1.5)); repetitions+=1; ease=max(1.3,ease-.05)
        else:interval=3 if repetitions==0 else max(old_interval+1,round(max(1,old_interval)*ease)); repetitions+=1; ease=min(2.8,ease+.05)
        today=date.today(); row.update({"last_rating":rating,"last_review":datetime.now().isoformat(timespec="seconds"),"due":(today+timedelta(days=interval)).isoformat(),"interval_days":interval,"repetitions":repetitions,"ease":round(ease,2)})
        daily=self.data["daily"]; daily["reviewed"]+=1; daily["remembered"]+=int(rating=="remembered"); daily["new"]+=int(first); self._save()

    def due_words(self,words):
        today=date.today().isoformat(); due=[]; unseen=[]; future=[]
        for word in words:
            state=self.state(word["id"]); due_date=state.get("due","")
            if not state.get("last_review"):unseen.append(word)
            elif not due_date or due_date<=today:due.append(word)
            else:future.append(word)
        due.sort(key=lambda word:(self.state(word["id"]).get("due",""),self.state(word["id"]).get("last_review",""))); future.sort(key=lambda word:self.state(word["id"]).get("due","9999")); return due+unseen+future

    def stats(self,words):
        self._sync_today(); today=date.today().isoformat(); reviewed=sum(bool(self.state(word["id"]).get("last_review")) for word in words); due=sum(bool(self.state(word["id"]).get("last_review")) and self.state(word["id"]).get("due","")<=today for word in words); favorites=sum(bool(self.state(word["id"]).get("favorite")) for word in words); return {"total":len(words),"learned":reviewed,"due":due,"favorites":favorites,"daily":dict(self.data["daily"])}
