"""Qt UI: crisp Chinese text, VS Code discovery and task management."""
import hashlib, json, random, shutil, sqlite3, subprocess, sys, tempfile, threading, uuid
import time
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from .curriculum import CurriculumLibrary, CurriculumStore, PATH_LABELS, STATE_LABELS
from .lessons import LessonChatStore, LessonStore, ask_lesson_tutor, generate_lesson
from .learning_feed import PREFERENCES_PATH, Store as LearningStore, build_feed as build_learning_feed_v2, context_profile
from .paths import ASSETS_DIR, DATA_DIR, PROJECT_ROOT
from .project_ideas import ProjectIdeaStore
from .system_monitor import SystemMonitor
from .vocabulary import VocabularyLibrary, VocabularyStore
from .vscode_bridge import ensure_bridge_installed
try:
    from PySide6.QtCore import Qt, QTimer, QEvent, QPoint
    from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QLinearGradient, QPainter, QPen, QPixmap, QShortcut
    from PySide6.QtWidgets import *
except ImportError:
    from PyQt5.QtCore import Qt, QTimer, QEvent, QPoint
    from PyQt5.QtGui import QColor, QFont, QIcon, QKeySequence, QLinearGradient, QPainter, QPen, QPixmap
    from PyQt5.QtWidgets import *

BASE=PROJECT_ROOT; DATA=DATA_DIR/"tasks.json"; TODOS_FILE=DATA_DIR/"daily_todos.json"; EVENTS=DATA_DIR/"events.jsonl"
PROFILE_FILE=Path.home()/".config/Code/User/globalStorage/woozy-masta.codex-switch/profiles.json"
GLOBAL_DB=Path.home()/".config/Code/User/globalStorage/state.vscdb"
SEEN_FILE=DATA_DIR/"seen_sessions.json"
BRIDGE_DIR=Path.home()/".codex-window-manager"
API_CODEX_HOME=Path.home()/".codex-heju"
API_PROVIDERS_FILE=PROJECT_ROOT/"config"/"api_providers.json"
STATES=["Running","Needs input","Ready","Blocked","Done"]
LABELS=dict(zip(STATES,["执行中","需要输入","已就绪","已阻塞","已完成"]))
COLORS=dict(zip(STATES,["#2563eb","#d97706","#059669","#dc2626","#64748b"]))
SESSION_ROOT=Path.home()/".codex/sessions"
_SESSION_HEADERS={}
_SESSION_STREAMS={}
_CONVERSATION_TITLES={}
_LAST_BRIDGE_CLEANUP=0

def run_cancellable_audio(args,cancel,timeout=15):
    try:process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except OSError:return False
    deadline=time.monotonic()+timeout
    while process.poll() is None:
        if cancel.wait(.03) or time.monotonic()>=deadline:
            process.terminate()
            try:process.wait(timeout=1)
            except subprocess.TimeoutExpired:process.kill()
            return False
    return process.returncode==0 and not cancel.is_set()

def play_vocab_audio(text,cancel):
    """Reuse the Alt+Q Piper voice and stop stale playback immediately."""
    if cancel.is_set():return
    with tempfile.TemporaryDirectory(prefix="codex-vocab-tts-") as directory:
        wav=Path(directory)/"word.wav"; piper_url="http://127.0.0.1:59125/synthesize"; request=urllib.request.Request(piper_url,data=json.dumps({"text":text,"length_scale":0.92}).encode("utf-8"),headers={"Content-Type":"application/json"},method="POST")
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request,timeout=12) as response:audio=response.read()
                if cancel.is_set():return
                if audio:
                    wav.write_bytes(audio)
                    if run_cancellable_audio(["/usr/bin/aplay","-q",str(wav)],cancel):return
                    if cancel.is_set():return
            except Exception:
                if cancel.is_set():return
                if attempt==0:
                    try:subprocess.run(["systemctl","--user","start","selection-piper.service"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
                    except Exception:pass
                    if cancel.wait(.7):return
        edge=shutil.which("edge-tts"); player=shutil.which("ffplay"); media=Path(directory)/"word.mp3"
        if edge and player and not cancel.is_set():
            generated=run_cancellable_audio([edge,"--voice","en-US-AriaNeural","--rate","-8%","--text",text,"--write-media",str(media)],cancel)
            if generated and media.exists() and media.stat().st_size:
                if run_cancellable_audio([player,"-nodisp","-autoexit","-loglevel","quiet",str(media)],cancel):return
            if cancel.is_set():return
        command=next((name for name in ("spd-say","espeak-ng","espeak") if shutil.which(name)),None)
        if command and not cancel.is_set():
            args=[command,"-l","en","-r","-12","-t","female1",text] if command=="spd-say" else [command,"-s","145",text]
            run_cancellable_audio(args,cancel)

def global_point(event):
    return event.globalPosition().toPoint() if hasattr(event,"globalPosition") else event.globalPos()

def format_bytes(value):
    value=float(value or 0)
    for unit in ("B","KB","MB","GB","TB"):
        if abs(value)<1024 or unit=="TB":return f"{value:.1f} {unit}"
        value/=1024

def format_rate(value):return f"{format_bytes(value)}/s"

class Sparkline(QWidget):
    def __init__(self,color="#4f46e5",parent=None):
        super().__init__(parent); self.values=[]; self.color=QColor(color); self.setMinimumHeight(34)
    def set_values(self,values):self.values=list(values)[-60:]; self.update()
    def paintEvent(self,event):
        painter=QPainter(self); painter.setRenderHint(QPainter.Antialiasing); rect=self.rect().adjusted(1,5,-1,-4)
        if len(self.values)<2:return
        low,high=min(self.values),max(self.values); span=high-low or 1.0; points=[]
        for index,value in enumerate(self.values):
            x=rect.left()+rect.width()*index/max(1,len(self.values)-1); y=rect.bottom()-rect.height()*(value-low)/span; points.append((int(x),int(y)))
        painter.setPen(QPen(QColor(self.color),2));
        for first,second in zip(points,points[1:]):painter.drawLine(first[0],first[1],second[0],second[1])

def extension_state(db):
    try:
        con=sqlite3.connect(f"file:{db}?mode=ro",uri=True); row=con.execute("select value from ItemTable where key=?",("woozy-masta.codex-switch",)).fetchone(); con.close()
        return json.loads(row[0]) if row else {}
    except Exception:return {}

def profiles():
    try: rows=json.loads(PROFILE_FILE.read_text())["profiles"]
    except Exception:return []
    roots=list((Path.home()/".codex-switch/maintenance/v1").glob("*/profiles"))
    for p in rows:
        p["limits"]={}
        name=hashlib.sha256(p["id"].encode()).hexdigest()+".json"
        for root in roots:
            try:p["limits"]=json.loads((root/name).read_text()).get("rateLimits",{}); break
            except Exception:pass
    return rows

def api_provider_profiles():
    """Public provider metadata only; credentials remain in each private CODEX_HOME."""
    try: raw=json.loads(API_PROVIDERS_FILE.read_text(encoding="utf-8")); rows=raw.get("providers",[])
    except (OSError,ValueError): rows=[]
    out=[]
    for row in rows:
        if not row.get("id") or not row.get("name"):continue
        home=str(row.get("codex_home","")).replace("~",str(Path.home()),1)
        configured=bool(row.get("configured")) and (Path(home)/"config.toml").is_file() and (Path(home)/"auth.json").is_file()
        out.append({"id":"provider:"+row["id"],"name":row["name"],"kind":"api","provider":row["id"],"codexHome":home,"configured":configured,"baseUrl":row.get("base_url","")})
    return out

def api_provider_profile():
    return next(iter(api_provider_profiles()), {"id":"provider:hejuapi","name":"备用 API","kind":"api","provider":"hejuapi","codexHome":str(API_CODEX_HOME),"configured":False})

def api_profile_for(provider):
    return next((p for p in api_provider_profiles() if p.get("provider")==provider), {"name":provider or "备用 API"})

def bridge_window_info(path,folder=""):
    now=time.time(); candidates=[]
    if path:candidates.append(BRIDGE_DIR/f"ready-{path.encode('utf-8').hex()}.json")
    if folder:candidates.append(BRIDGE_DIR/f"ready-name-{folder.encode('utf-8').hex()}.json")
    for ready in candidates:
        try:
            info=json.loads(ready.read_text(encoding="utf-8"))
            if now-info.get("at",0)/1000<8:return info
        except Exception:pass
    return {}

def workspace_db(path):
    storage=Path.home()/".config/Code/User/workspaceStorage"
    for record in storage.glob("*/workspace.json"):
        try:
            if workspace_location(json.loads(record.read_text()).get("folder",""))[0]==path:return record.parent/"state.vscdb"
        except Exception:pass
    return None

def workspace_location(uri):
    """Return filesystem path and remote label for file:// and vscode-remote:// workspaces."""
    if not uri:return "",None
    parsed=urlparse(uri)
    if parsed.scheme=="file":return unquote(parsed.path),None
    if parsed.scheme=="vscode-remote":
        authority=unquote(parsed.netloc); label=None
        if authority.startswith("ssh-remote+"):
            encoded=authority.removeprefix("ssh-remote+")
            try:
                raw=bytes.fromhex(encoded).decode() if all(c in "0123456789abcdefABCDEF" for c in encoded) else unquote(encoded)
                config=json.loads(raw); label=config.get("hostName") or config.get("host")
            except Exception:label=encoded
        return unquote(parsed.path),label or authority
    return uri.removeprefix("file://"),None

def latest_vscode_sessions():
    """Index session headers once and return the newest session per workspace."""
    latest={}
    for f in SESSION_ROOT.glob("**/*.jsonl"):
        key=str(f)
        try:
            stat=f.stat(); signature=(stat.st_ino,stat.st_size,stat.st_mtime_ns)
            cached=_SESSION_HEADERS.get(key)
            if cached is None:
                first=json.loads(f.open(encoding="utf-8").readline()); payload=first.get("payload",{})
                cached={"cwd":payload.get("cwd"),"source":payload.get("source"),"id":payload.get("id") or payload.get("session_id")}
                _SESSION_HEADERS[key]=cached
            cached["file"]=f; cached["mtime"]=stat.st_mtime
            if cached.get("source")!="vscode" or not cached.get("cwd"):continue
            current=latest.get(cached["cwd"])
            if current is None or stat.st_mtime_ns>current[1].st_mtime_ns:latest[cached["cwd"]]=(f,stat,signature)
        except Exception:pass
    return latest

def conversation_title(f):
    key=str(f)
    if key in _CONVERSATION_TITLES:return _CONVERSATION_TITLES[key]
    title="新对话"
    try:
        with f.open("rb") as stream:
            for _ in range(80):
                raw=stream.readline()
                if not raw:break
                try:record=json.loads(raw)
                except Exception:continue
                payload=record.get("payload",{})
                if payload.get("type")=="user_message" and payload.get("message"):
                    text=payload["message"]
                    if "## My request for Codex:" in text:
                        text=text.split("## My request for Codex:",1)[1]
                        if "```text\n" in text:text=text.split("```text\n",1)[1].removesuffix("```")
                    elif "## My request:" in text:text=text.split("## My request:",1)[1]
                    elif text.lstrip().startswith("## Referenced chats with Codex:"):
                        if "\n\n```text\n" in text:text=text.split("\n\n```text\n",1)[1].removesuffix("```")
                        elif "]\n\n" in text:text=text.rsplit("]\n\n",1)[1]
                    title=" ".join(text.split()).strip() or title
                    break
    except Exception:pass
    if len(title)>32:title=title[:32]+"…"
    _CONVERSATION_TITLES[key]=title
    return title

def project_conversations(project_path,limit=8):
    root=Path(project_path); rows=[]
    for item in _SESSION_HEADERS.values():
        if item.get("source")!="vscode" or not item.get("id") or not item.get("cwd"):continue
        try:inside=Path(item["cwd"])==root or Path(item["cwd"]).is_relative_to(root)
        except Exception:inside=False
        if inside:rows.append(item)
    rows.sort(key=lambda item:item.get("mtime",0),reverse=True)
    return [{**item,"title":conversation_title(item["file"])} for item in rows[:limit]],len(rows)

def parse_session(latest):
    """Read only bytes appended since the previous refresh."""
    f,stat,signature=latest; key=str(f); cached=_SESSION_STREAMS.get(key)
    if cached is None or cached.get("inode")!=stat.st_ino or stat.st_size<cached.get("offset",0):
        cached={"inode":stat.st_ino,"offset":0,"line":0,"started":0,"done":0,"completed_at":0,"rate_limits":None}
    try:
        with f.open("rb") as stream:
            stream.seek(cached["offset"])
            while True:
                start=stream.tell(); raw=stream.readline()
                if not raw:break
                if not raw.endswith(b"\n"):
                    stream.seek(start); break
                try:record=json.loads(raw)
                except Exception:continue
                cached["line"]+=1; payload=record.get("payload",{}); typ=payload.get("type")
                if typ=="task_started":cached["started"]=cached["line"]
                if typ=="task_complete":
                    cached["done"]=cached["line"]
                    cached["completed_at"]=payload.get("completed_at") or stat.st_mtime
                if typ=="token_count" and payload.get("rate_limits"):cached["rate_limits"]=payload["rate_limits"]
            cached["offset"]=stream.tell()
        _SESSION_STREAMS[key]=cached
    except Exception:return None
    return cached

def session_status(path, known_profiles, session_index):
    latest=session_index.get(path)
    if not latest:return "未发现会话",0,None
    parsed=parse_session(latest)
    if not parsed:return "状态未知",0,None
    started=parsed["started"]; done=parsed["done"]; rate_limits=parsed["rate_limits"]
    matched=None
    if rate_limits:
        resets={w.get("resets_at") for w in (rate_limits.get("primary") or {},rate_limits.get("secondary") or {})}
        for profile in known_profiles:
            cached=profile.get("limits",{}); profile_resets={(cached.get(k) or {}).get("resetsAt") for k in ("primary","secondary")}
            if (resets-{None}) & (profile_resets-{None}):matched=profile.get("name"); break
    if started>done:return "正在运行",0,matched
    return ("运行结束",parsed["completed_at"],matched) if done else ("会话空闲",0,matched)

def remote_session_status(path):
    ready=BRIDGE_DIR/f"ready-{path.encode('utf-8').hex()}.json"
    try:
        info=json.loads(ready.read_text(encoding="utf-8")); remote=info.get("remoteStatus") or {}; value=remote.get("status")
        labels={"running":"正在运行","complete":"运行结束","idle":"会话空闲","no_session":"未发现会话","monitor_missing":"远程监控未安装","unknown":"状态未知"}
        return labels.get(value,"远程状态连接中"),remote.get("completed",0),None
    except Exception:return "远程状态连接中",0,None

def cleanup_bridge_files(force=False):
    """Bound transient IPC storage without touching profiles or Codex sessions."""
    global _LAST_BRIDGE_CLEANUP
    now=time.time()
    if not force and now-_LAST_BRIDGE_CLEANUP<300:return
    _LAST_BRIDGE_CLEANUP=now
    groups=((BRIDGE_DIR,"ready-*.json",86400),(BRIDGE_DIR,"reopen-*.json",86400),(BRIDGE_DIR/"results","*.json",86400),(BRIDGE_DIR/"requests","*.json",86400))
    for root,pattern,max_age in groups:
        try:
            for f in root.glob(pattern):
                try:
                    if now-f.stat().st_mtime>max_age:f.unlink()
                except Exception:pass
        except Exception:pass

def find_path(name):
    plain_name=name.split(" [SSH:",1)[0].strip()
    if plain_name==BASE.name:return str(BASE)
    for f in (Path.home()/".config/Code/User/workspaceStorage").glob("*/workspace.json"):
        try:
            p,_=workspace_location(json.loads(f.read_text()).get("folder",""))
            if Path(p).name==plain_name:return p
        except Exception:pass
    return ""

def reset_label(timestamp):
    if not timestamp:return "时间未知"
    value=datetime.fromtimestamp(timestamp); today=datetime.now().date(); delta=(value.date()-today).days
    day="今天" if delta==0 else ("明天" if delta==1 else value.strftime("%m-%d"))
    return f"{day} {value:%H:%M}"

def remaining_label(timestamp):
    if not timestamp:return "等待刷新时间"
    seconds=max(0,int(timestamp-datetime.now().timestamp()))
    if seconds<60:return "即将刷新"
    days,seconds=divmod(seconds,86400); hours,seconds=divmod(seconds,3600); minutes=seconds//60
    if days:return f"{days} 天 {hours} 小时后"
    if hours:return f"{hours} 小时 {minutes} 分后"
    return f"{minutes} 分钟后"

def scan():
    try:s=subprocess.run(["wmctrl","-l","-x","-p"],capture_output=True,text=True,timeout=3).stdout
    except Exception:return []
    cleanup_bridge_files(); out=[]; ps=profiles(); sessions=latest_vscode_sessions(); by_id={p["id"]:p for p in ps}; global_id=extension_state(GLOBAL_DB).get("codexSwitch.activeProfileId.default")
    for line in s.splitlines():
        p=line.split(None,4)
        if len(p)<5:continue
        wid,_,pid,klass,rest=p; b=rest.split(None,1); title=b[1] if len(b)==2 else rest
        if not (klass.lower().startswith("code.") or "visual studio code" in title.lower()):continue
        title=title.replace(" - Visual Studio Code","").strip(); name=title.split(" - ")[-1].strip()
        path=find_path(name); state=extension_state(workspace_db(path)) if path and workspace_db(path) else {}
        workspace_id=state.get("codexSwitch.activeProfileId.default"); profile=by_id.get(workspace_id or global_id,{})
        if " [SSH:" in name:status,completed,session_account=remote_session_status(path)
        else:status,completed,session_account=session_status(path,ps,sessions) if path else ("状态未知",0,None)
        bridge_info=bridge_window_info(path,name); provider=bridge_info.get("provider","subscription")
        provider_profile=api_profile_for(provider)
        account=provider_profile.get("name",provider) if provider!="subscription" else (session_account or profile.get("name","未知账号"))
        scope="API 服务商" if provider!="subscription" else ("最近请求" if session_account else ("工作区" if workspace_id else "插件当前"))
        out.append(dict(id=wid,pid=pid,title=title,folder=name,path=path,account=account,account_scope=scope,status=status,completed=completed,provider=provider))
    return out

def active_window_id():
    """Return the EWMH id of the window that currently owns keyboard focus."""
    try:
        output=subprocess.run(["xprop","-root","_NET_ACTIVE_WINDOW"],capture_output=True,text=True,timeout=2).stdout
        value=output.rsplit(None,1)[-1]
        return int(value,16)
    except Exception:return None

class BubbleButton(QPushButton):
    """Clickable to expand, draggable to reposition the floating bubble."""
    def __init__(self,parent=None):
        super().__init__(parent); self.unread=0; self.setCursor(Qt.PointingHandCursor)
    def setUnread(self,count):self.unread=count; self.update()
    def paintEvent(self,event):
        painter=QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        rect=self.rect().adjusted(3,3,-3,-3); gradient=QLinearGradient(rect.topLeft(),rect.bottomRight())
        gradient.setColorAt(0,QColor("#60a5fa" if not self.unread else "#fb7185")); gradient.setColorAt(1,QColor("#4f46e5" if not self.unread else "#dc2626"))
        painter.setPen(QPen(QColor(255,255,255,230),2)); painter.setBrush(gradient); painter.drawEllipse(rect)
        painter.setPen(Qt.NoPen); painter.setBrush(QColor("white")); cx,cy=self.width()/2,self.height()/2
        if self.unread:
            painter.setPen(QColor("white")); painter.setFont(QFont("Noto Sans CJK SC",15,QFont.Bold)); painter.drawText(self.rect(),Qt.AlignCenter,str(self.unread))
        else:
            for dx,dy in ((0,-8),(8,0),(0,8),(-8,0),(0,0)):painter.drawEllipse(int(cx+dx-3),int(cy+dy-3),6,6)
    def mousePressEvent(self,event):
        self._press=global_point(event); self._origin=self.window().pos(); self._moved=False; super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.LeftButton:
            delta=global_point(event)-self._press
            if delta.manhattanLength()>3:self._moved=True
            self.window().move(self._origin+delta); event.accept(); return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if self._moved:self.setDown(False); event.accept(); return
        super().mouseReleaseEvent(event)

class DraggableHeader(QFrame):
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:self._press=global_point(event); self._origin=self.window().pos()
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.LeftButton and not self.window().isMaximized():self.window().move(self._origin+global_point(event)-self._press); event.accept(); return
        super().mouseMoveEvent(event)
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton:self.window().toggle_maximize(); event.accept(); return
        super().mouseDoubleClickEvent(event)

class LessonChatDialog(QDialog):
    """A lightweight, concept-scoped tutor using the existing DeepSeek key."""
    def __init__(self,parent,bundle,concept,lesson,store,executor):
        super().__init__(parent); self.bundle=bundle; self.concept=concept; self.lesson=lesson; self.store=store; self.executor=executor; self.future=None; self._close_after_answer=False
        self.setWindowTitle("AI 学习助手 · "+concept.get("title_zh","当前知识点")); self.setWindowFlag(Qt.WindowStaysOnTopHint,True); self.setMinimumSize(460,480); self.resize(540,680); self.setStyleSheet("QDialog{background:#f8fafc} QLabel{font-family:'Noto Sans CJK SC';color:#172033} QPushButton{font-family:'Noto Sans CJK SC';padding:7px 12px;background:white;border:1px solid #dbe3ed;border-radius:7px} QPushButton:hover{background:#eef2ff;border-color:#a5b4fc} QPlainTextEdit{font-family:'Noto Sans CJK SC';font-size:12px;color:#172033;background:white;border:1px solid #cbd5e1;border-radius:9px;padding:8px}")
        root=QVBoxLayout(self); root.setContentsMargins(14,13,14,14); root.setSpacing(9)
        head=QHBoxLayout(); titles=QVBoxLayout(); titles.setSpacing(1); title=QLabel("AI 学习助手"); title.setFont(QFont("Noto Sans CJK SC",16,QFont.Bold)); title.setStyleSheet("color:#312e81"); titles.addWidget(title); subtitle=QLabel("当前课程 · "+concept.get("title_zh","知识点")); subtitle.setStyleSheet("color:#64748b;font-size:10px"); titles.addWidget(subtitle); head.addLayout(titles); head.addStretch(); clear=QPushButton("清空对话"); clear.clicked.connect(self.clear_chat); head.addWidget(clear); root.addLayout(head)
        privacy=QLabel("只会把当前知识点、当前微课和你在这里的提问发送给 DeepSeek；项目路径、账号和 Codex 对话不会发送。对话记录仅保存在本机。")
        privacy.setWordWrap(True); privacy.setStyleSheet("color:#475569;background:#eef2ff;padding:7px 9px;border-radius:7px;font-size:9px"); root.addWidget(privacy)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame); self.scroll.setStyleSheet("QScrollArea{background:#f8fafc;border:0} QScrollArea QWidget#qt_scrollarea_viewport{background:#f8fafc}"); self.chat_body=QWidget(); self.chat_body.setStyleSheet("background:#f8fafc"); self.chat_layout=QVBoxLayout(self.chat_body); self.chat_layout.setContentsMargins(2,4,2,4); self.chat_layout.setSpacing(8); self.scroll.setWidget(self.chat_body); root.addWidget(self.scroll,1)
        suggestions=QHBoxLayout(); suggestions.setSpacing(5)
        for text in ("换个直观例子","和相邻方法怎么区分？","论文里怎么识别它？"):
            chip=QPushButton(text); chip.setStyleSheet("QPushButton{padding:5px 8px;background:#f1f5f9;color:#475569;border:0;border-radius:6px;font-size:9px} QPushButton:hover{background:#e0e7ff;color:#3730a3}"); chip.clicked.connect(lambda _,value=text:self.input.setPlainText(value)); suggestions.addWidget(chip)
        suggestions.addStretch(); root.addLayout(suggestions)
        composer=QHBoxLayout(); composer.setSpacing(8); self.input=QPlainTextEdit(); self.input.setPlaceholderText("哪里不懂就直接问，例如：这里的速度场是谁预测的？\n支持系统中文输入法；点击发送或按 Ctrl+Enter。") ; self.input.setFixedHeight(82); composer.addWidget(self.input,1); self.send=QPushButton("发送"); self.send.setFixedSize(76,82); self.send.setStyleSheet("QPushButton{background:#4f46e5;color:white;border:0;border-radius:9px;font-weight:700} QPushButton:hover{background:#4338ca} QPushButton:disabled{background:#c7d2fe}"); self.send.clicked.connect(self.send_question); composer.addWidget(self.send); root.addLayout(composer)
        self.shortcut=QShortcut(QKeySequence("Ctrl+Return"),self); self.shortcut.activated.connect(self.send_question); self.render_messages(); self.input.setFocus()
    def render_messages(self):
        while self.chat_layout.count():
            item=self.chat_layout.takeAt(0); widget=item.widget()
            if widget:widget.deleteLater()
        rows=self.store.messages(self.bundle,self.concept["id"])
        if not rows:
            welcome=QLabel("这不是搜索框，你可以沿着自己的疑问连续追问。\n\n比如：\n• 先用完全不带公式的方式解释\n• 再给我一个机械臂动作例子\n• 那它和 Diffusion Policy 到底差在哪")
            welcome.setWordWrap(True); welcome.setAlignment(Qt.AlignCenter); welcome.setStyleSheet("color:#64748b;background:white;border:1px solid #e2e8f0;padding:20px;border-radius:10px"); self.chat_layout.addWidget(welcome)
        for row in rows:
            holder=QWidget(); line=QHBoxLayout(holder); line.setContentsMargins(0,0,0,0); role=row.get("role"); bubble=QFrame(); bubble.setMaximumWidth(490); bubble.setStyleSheet("QFrame{background:#4f46e5;border:0;border-radius:10px}" if role=="user" else "QFrame{background:white;border:1px solid #e2e8f0;border-radius:10px}"); inside=QVBoxLayout(bubble); inside.setContentsMargins(11,8,11,8); label=QLabel(row.get("content","").replace("**","")); label.setTextFormat(Qt.PlainText); label.setWordWrap(True); label.setTextInteractionFlags(Qt.TextSelectableByMouse); label.setStyleSheet("color:white;font-size:11px" if role=="user" else "color:#334155;font-size:11px"); inside.addWidget(label)
            if role=="user":line.addStretch(); line.addWidget(bubble)
            else:line.addWidget(bubble); line.addStretch()
            self.chat_layout.addWidget(holder)
        if self.future and not self.future.done():
            waiting=QLabel("AI 正在组织回答…"); waiting.setStyleSheet("color:#4338ca;background:#eef2ff;padding:8px 10px;border-radius:8px;font-size:10px"); self.chat_layout.addWidget(waiting,0,Qt.AlignLeft)
        self.chat_layout.addStretch(); QTimer.singleShot(0,lambda:self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))
    def send_question(self):
        question=self.input.toPlainText().strip()
        if not question or (self.future and not self.future.done()):return
        history=self.store.messages(self.bundle,self.concept["id"]); self.store.append(self.bundle,self.concept["id"],"user",question); self.input.clear(); self.send.setEnabled(False); self.future=self.executor.submit(ask_lesson_tutor,self.bundle,self.concept,self.lesson,history,question); self.render_messages(); QTimer.singleShot(100,self.poll_answer)
    def poll_answer(self):
        if not self.future:return
        if not self.future.done():QTimer.singleShot(100,self.poll_answer); return
        try:answer=self.future.result()
        except Exception as exc:answer="这次没有回答成功："+str(exc)+"\n\n你可以稍后重新发送。"
        self.store.append(self.bundle,self.concept["id"],"assistant",answer); self.future=None
        if self._close_after_answer:self.accept(); return
        self.send.setEnabled(True); self.render_messages(); self.input.setFocus()
    def clear_chat(self):
        if QMessageBox.question(self,"清空当前对话","只清空这个知识点的本地问答记录吗？",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:self.store.clear(self.bundle,self.concept["id"]); self.render_messages()
    def closeEvent(self,event):
        if self.future and not self.future.done():self._close_after_answer=True; self.hide(); event.ignore(); return
        super().closeEvent(event)

class ProjectIdeasDialog(QDialog):
    def __init__(self, store, project, parent=None):
        super().__init__(parent); self.store=store; self.project=project
        self.setWindowTitle("项目灵感 · "+project.get("folder","未命名项目")); self.setWindowFlag(Qt.WindowStaysOnTopHint,True); self.setMinimumSize(500,430); self.resize(560,560)
        self.setStyleSheet("QDialog{background:#f8fafc} QLabel{font-family:'Noto Sans CJK SC';color:#172033} QPushButton{font-family:'Noto Sans CJK SC';padding:7px 11px;background:white;border:1px solid #dbe3ed;border-radius:7px} QPushButton:hover{background:#eef2ff;border-color:#a5b4fc} QPlainTextEdit{font-family:'Noto Sans CJK SC';font-size:13px;color:#172033;background:white;border:1px solid #cbd5e1;border-radius:9px;padding:8px}")
        outer=QVBoxLayout(self); outer.setContentsMargins(16,14,16,16); outer.setSpacing(10)
        head=QHBoxLayout(); titles=QVBoxLayout(); titles.setSpacing(1); title=QLabel("灵感备忘"); title.setStyleSheet("font-size:18px;font-weight:700;color:#312e81"); titles.addWidget(title); subtitle=QLabel(project.get("folder","未命名项目")+" · 来不及实现的想法先放在这里"); subtitle.setStyleSheet("color:#64748b;font-size:10px"); titles.addWidget(subtitle); head.addLayout(titles); head.addStretch(); self.stats=QLabel(); self.stats.setStyleSheet("color:#6d28d9;background:#ede9fe;padding:4px 8px;border-radius:6px;font-size:10px;font-weight:700"); head.addWidget(self.stats); outer.addLayout(head)
        capture=QFrame(); capture.setObjectName("ideaCapture"); capture.setStyleSheet("QFrame#ideaCapture{background:#f5f3ff;border:1px solid #ddd6fe;border-radius:10px}"); capture_layout=QVBoxLayout(capture); capture_layout.setContentsMargins(10,9,10,10); capture_layout.setSpacing(7); self.input=QPlainTextEdit(); self.input.setPlaceholderText("记下一个想法、实验方向或以后要验证的问题……"); self.input.setFixedHeight(72); capture_layout.addWidget(self.input); capture_actions=QHBoxLayout(); hint=QLabel("只保存在本机，并绑定到这个项目"); hint.setStyleSheet("color:#7c3aed;font-size:9px"); capture_actions.addWidget(hint); capture_actions.addStretch(); add=QPushButton("＋ 记录灵感"); add.setStyleSheet("background:#6d28d9;color:white;border:0;font-weight:700"); add.clicked.connect(self.add_idea); capture_actions.addWidget(add); capture_layout.addLayout(capture_actions); outer.addWidget(capture)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame); self.container=QWidget(); self.list_layout=QVBoxLayout(self.container); self.list_layout.setContentsMargins(0,0,0,0); self.list_layout.setSpacing(7); self.scroll.setWidget(self.container); outer.addWidget(self.scroll,1); self.render()
    def render(self):
        while self.list_layout.count():
            item=self.list_layout.takeAt(0); widget=item.widget()
            if widget:widget.deleteLater()
        rows=self.store.list(self.project.get("path","")); open_count=sum(not row.get("done") for row in rows); self.stats.setText(f"{open_count} 条待处理")
        if not rows:
            empty=QLabel("还没有灵感记录\n想到什么就先放进来，不必现在实现"); empty.setAlignment(Qt.AlignCenter); empty.setStyleSheet("color:#94a3b8;background:white;padding:28px;border-radius:9px"); self.list_layout.addWidget(empty)
        for idea in rows:
            card=QFrame(); card.setObjectName("ideaCard"); card.setStyleSheet("QFrame#ideaCard{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px}" if idea.get("done") else "QFrame#ideaCard{background:white;border:1px solid #c4b5fd;border-left:3px solid #8b5cf6;border-radius:8px}"); line=QHBoxLayout(card); line.setContentsMargins(9,8,7,8); line.setSpacing(7); check=QCheckBox(); check.setChecked(bool(idea.get("done"))); check.setToolTip("标记为已处理"); check.stateChanged.connect(lambda state,idea_id=idea["id"]:self.toggle_idea(idea_id,state)); line.addWidget(check); text=QLabel(idea.get("text","")); text.setWordWrap(True); text.setTextInteractionFlags(Qt.TextSelectableByMouse); text.setStyleSheet("color:#94a3b8;text-decoration:line-through" if idea.get("done") else "color:#1e293b;font-size:12px;font-weight:600"); line.addWidget(text,1); edit=QPushButton("编辑"); edit.setFixedHeight(30); edit.clicked.connect(lambda _,row=idea:self.edit_idea(row)); line.addWidget(edit); remove=QPushButton("×"); remove.setFixedSize(29,29); remove.setToolTip("删除灵感"); remove.setStyleSheet("QPushButton{padding:0;border:0;background:transparent;color:#94a3b8;font-size:17px} QPushButton:hover{background:#fee2e2;color:#dc2626}"); remove.clicked.connect(lambda _,row=idea:self.delete_idea(row)); line.addWidget(remove); self.list_layout.addWidget(card)
        self.list_layout.addStretch()
    def add_idea(self):
        if self.store.add(self.project.get("path",""),self.project.get("folder","未命名项目"),self.input.toPlainText()):self.input.clear(); self.render()
    def toggle_idea(self,idea_id,state):self.store.toggle(idea_id,bool(state)); self.render()
    def edit_idea(self,idea):
        text,accepted=QInputDialog.getMultiLineText(self,"编辑灵感","内容",idea.get("text",""))
        if accepted and self.store.update(idea["id"],text):self.render()
    def delete_idea(self,idea):
        if QMessageBox.question(self,"删除灵感","确定删除这条灵感吗？",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:self.store.delete(idea["id"]); self.render()


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.tasks=self.load(); self.todos=self.load_todos(); self.idea_store=ProjectIdeaStore(); self.view_mode="monitor"; self.windows=[]; self.expanded=False
        self.pending_accounts={}; self.pending_focus={}; self.pending_opens={}; self.pending_bridge_recovery={}
        self.feed_error=""; self.feed_future=None; self.feed_executor=ThreadPoolExecutor(max_workers=1)
        self.feed_store=LearningStore(); self.feed_display_limit=6; self.feed_items=self.feed_store.recent(self.feed_display_limit); self.feed_stats=self.feed_store.stats()
        self.learning_context={"label":"具身智能前沿","terms":[],"topics":[]}; self.learning_mode="frontier"
        self.curriculum_library=CurriculumLibrary(); self.curriculum_store=CurriculumStore(); loaded=self.curriculum_library.domains(); preferred=self.curriculum_store.selected_domain()
        self.curriculum_domain_id=preferred if self.curriculum_library.get(preferred) else (loaded[0]["id"] if loaded else "")
        self.lesson_store=LessonStore(); self.lesson_chat_store=LessonChatStore(); self.lesson_executor=ThreadPoolExecutor(max_workers=1); self.tutor_executor=ThreadPoolExecutor(max_workers=1); self.lesson_future=None; self.lesson_job=None; self.lesson_errors={}; self.curriculum_card_widget=None; self.tutor_dialogs=[]; self.floating_tutor_available=False
        self.vocab_library=VocabularyLibrary(); self.vocab_store=VocabularyStore(); vocabularies=self.vocab_library.lexicons(); self.vocab_lexicon_id=self.vocab_store.selected(vocabularies); selected_vocab=self.vocab_library.get(self.vocab_lexicon_id); self.vocab_words=self.vocab_library.load(selected_vocab["path"]) if selected_vocab else []; self.vocab_current_id=(self.vocab_store.due_words(self.vocab_words)[0]["id"] if self.vocab_words else None); self.vocab_revealed=False; self.vocab_random=False; self.vocab_history=[]; self.vocab_retry_queue=[]; self.vocab_last_spoken_id=None; self.vocab_audio_generation=0; self.tts_cancel=None; self.tts_executor=ThreadPoolExecutor(max_workers=3); self.tts_future=None
        self.system_monitor=SystemMonitor(); self.system_executor=ThreadPoolExecutor(max_workers=1); self.system_future=None; self.system_metrics=self.system_monitor.empty(); self.system_history={"cpu":deque(maxlen=60),"memory":deque(maxlen=60),"gpu":deque(maxlen=60),"disk":deque(maxlen=60)}
        try:self.seen=json.loads(SEEN_FILE.read_text())
        except Exception:self.seen={}
        self.setWindowTitle("Codex 任务总控台"); self.setWindowIcon(QIcon(str(ASSETS_DIR/"codex-control-tower.svg"))); self.setWindowFlag(Qt.WindowStaysOnTopHint,True); self.setAttribute(Qt.WA_TranslucentBackground,True); self.setObjectName("root")
        self.setStyleSheet("QWidget{font-family:'Noto Sans CJK SC';font-size:13px;color:#172033} QWidget#root{background:transparent} QPushButton{padding:7px 13px;background:#ffffff;border:1px solid #dbe3ed;border-radius:7px} QPushButton:hover{background:#f5f7ff;border-color:#a5b4fc} QLineEdit,QComboBox{padding:7px;background:white;border:1px solid #dbe3ed;border-radius:6px} QMenu{background:white;border:1px solid #dbe3ed;border-radius:8px;padding:6px} QMenu::item{padding:8px 24px 8px 12px;border-radius:5px} QMenu::item:selected{background:#eef2ff;color:#4338ca} QProgressBar{height:6px;border:0;border-radius:3px;background:#e2e8f0;text-align:center} QProgressBar::chunk{border-radius:3px;background:#34d399}")
        self.root=QVBoxLayout(self); self.root.setContentsMargins(0,0,0,0); self.root.setSpacing(4); self.bubble=BubbleButton(); self.bubble.setFixedSize(58,58); self.bubble.setToolTip("点击展开，拖动可移动"); shadow=QGraphicsDropShadowEffect(self); shadow.setBlurRadius(18); shadow.setOffset(0,4); shadow.setColor(QColor(15,23,42,120)); self.bubble.setGraphicsEffect(shadow); self.bubble.clicked.connect(self.toggle); self.root.addWidget(self.bubble)
        self.shell=QFrame(); self.shell.setObjectName("shell"); self.shell.setStyleSheet("QFrame#shell{background:#f8fafc;border:1px solid #dbe3ed;border-radius:12px}"); shell_layout=QVBoxLayout(self.shell); shell_layout.setContentsMargins(0,0,0,0); shell_layout.setSpacing(0)
        self.header=DraggableHeader(); self.header.setStyleSheet("background:#f8fafc;border:0;border-bottom:1px solid #e2e8f0;border-top-left-radius:12px;border-top-right-radius:12px"); h=QHBoxLayout(self.header); h.setContentsMargins(14,9,9,9); title=QLabel("●  Codex 任务总控台"); title.setFont(QFont("Noto Sans CJK SC",15,QFont.Bold)); title.setStyleSheet("color:#0f172a;border:0"); h.addWidget(title)
        self.monitor_tab=QPushButton("任务监控"); self.todo_tab=QPushButton("今日待办"); self.learn_tab=QPushButton("等待学习"); self.system_tab=QPushButton("系统监控")
        for mode,button in (("monitor",self.monitor_tab),("todo",self.todo_tab),("learn",self.learn_tab),("system",self.system_tab)):
            button.setCheckable(True); button.setCursor(Qt.PointingHandCursor); button.clicked.connect(lambda _,m=mode:self.switch_view(m)); h.addWidget(button)
        self.summary=QLabel(); self.summary.setStyleSheet("color:#475569;border:0"); h.addWidget(self.summary,1)
        scan_btn=QPushButton("刷新"); scan_btn.setToolTip("立即扫描 VS Code"); scan_btn.clicked.connect(self.refresh); h.addWidget(scan_btn)
        controls=(("—","缩成悬浮球",self.collapse),("□","最大化 / 还原",self.toggle_maximize),("×","关闭",self.close))
        for text,tip,fn in controls:
            button=QPushButton(text); button.setFixedSize(32,30); button.setToolTip(tip); button.setStyleSheet("QPushButton{padding:0;background:transparent;border:0;border-radius:7px;font-size:16px;color:#475569} QPushButton:hover{background:#e2e8f0}" if text!="×" else "QPushButton{padding:0;background:transparent;border:0;border-radius:7px;font-size:18px;color:#475569} QPushButton:hover{background:#fee2e2;color:#dc2626}"); button.clicked.connect(fn); h.addWidget(button)
        shell_layout.addWidget(self.header); self.area=QScrollArea(); self.area.setWidgetResizable(True); self.content=QWidget(); self.box=QVBoxLayout(self.content); self.box.setSpacing(7); self.area.setWidget(self.content); shell_layout.addWidget(self.area); self.floating_tutor_button=QPushButton("问 AI",self.area.viewport()); self.floating_tutor_button.setFixedSize(72,36); self.floating_tutor_button.setCursor(Qt.PointingHandCursor); self.floating_tutor_button.setToolTip("随时围绕当前课程提问"); self.floating_tutor_button.setStyleSheet("QPushButton{background:#4f46e5;color:white;border:1px solid #c7d2fe;border-radius:18px;font-weight:700} QPushButton:hover{background:#4338ca}"); tutor_shadow=QGraphicsDropShadowEffect(self.floating_tutor_button); tutor_shadow.setBlurRadius(16); tutor_shadow.setOffset(0,3); tutor_shadow.setColor(QColor(49,46,129,100)); self.floating_tutor_button.setGraphicsEffect(tutor_shadow); self.floating_tutor_button.clicked.connect(self.open_curriculum_tutor); self.floating_tutor_button.hide(); self.area.viewport().installEventFilter(self); self.root.addWidget(self.shell); self.setup_vocab_shortcuts(); ensure_bridge_installed(); self.refresh(); self.collapse()
        self.timer=QTimer(self); self.timer.timeout.connect(self.periodic_refresh); self.timer.start(5000); self.system_timer=QTimer(self); self.system_timer.timeout.connect(self.schedule_system_sample); self.system_timer.start(2000)
    def load(self):
        try:return json.loads(DATA.read_text())
        except Exception:return []
    def save(self):DATA.write_text(json.dumps(self.tasks,ensure_ascii=False,indent=2))
    def load_todos(self):
        try:return json.loads(TODOS_FILE.read_text(encoding="utf-8"))
        except Exception:return []
    def save_todos(self):TODOS_FILE.write_text(json.dumps(self.todos,ensure_ascii=False,indent=2),encoding="utf-8")
    def switch_view(self,mode):
        if mode!="learn":self.cancel_vocab_audio(True); self.vocab_last_spoken_id=None
        self.view_mode=mode
        if mode=="system":self.schedule_system_sample()
        self.refresh()
    def update_tabs(self):
        active="QPushButton{padding:6px 12px;background:#4f46e5;color:white;border:0;border-radius:7px;font-weight:700}"
        normal="QPushButton{padding:6px 12px;background:#eef2ff;color:#475569;border:0;border-radius:7px} QPushButton:hover{background:#e0e7ff;color:#3730a3}"
        for mode,button in (("monitor",self.monitor_tab),("todo",self.todo_tab),("learn",self.learn_tab),("system",self.system_tab)):
            button.setChecked(self.view_mode==mode); button.setStyleSheet(active if self.view_mode==mode else normal)
    def periodic_refresh(self):
        before=(getattr(self,"running_count",0),getattr(self,"done_count",0),sum(w.get("completed",0)>self.seen.get(w.get("path",""),0) for w in self.windows))
        self.refresh(render=self.view_mode in ("monitor","system"))
        after=(self.running_count,self.done_count,sum(w.get("completed",0)>self.seen.get(w.get("path",""),0) for w in self.windows))
        if self.view_mode=="learn" and before!=after:self.refresh(render=True)
    def toggle(self):
        self.collapse() if self.expanded else self.expand()
    def expand(self):
        self.expanded=True; self.setWindowFlag(Qt.FramelessWindowHint,True); self.setWindowFlag(Qt.WindowStaysOnTopHint,True); self.setMinimumSize(740,420); self.setMaximumSize(16777215,16777215); self.root.setContentsMargins(6,6,6,6); self.bubble.hide(); self.shell.show(); self.area.show(); self.resize(840,540); self.show(); self.update_floating_tutor(); self.update_vocab_shortcuts()
        if self.view_mode=="learn" and self.learning_mode=="vocabulary":self.queue_vocab_autoplay(self.current_vocab_word())
        QTimer.singleShot(100,self.ensure_on_top)
    def collapse(self):
        if self.isMaximized():self.showNormal()
        self.cancel_vocab_audio(True); self.vocab_last_spoken_id=None
        self.expanded=False; self.floating_tutor_button.hide(); self.shell.hide(); self.bubble.show(); self.root.setContentsMargins(0,0,0,0); self.setMinimumSize(58,58); self.setMaximumSize(58,58); self.setWindowFlag(Qt.FramelessWindowHint,True); self.setWindowFlag(Qt.WindowStaysOnTopHint,True); self.resize(58,58); self.show(); self.update_vocab_shortcuts(); QTimer.singleShot(100,self.ensure_on_top)
    def toggle_maximize(self):
        if self.isMaximized():self.showNormal(); self.resize(840,540)
        else:self.setMaximumSize(16777215,16777215); self.showMaximized()
        QTimer.singleShot(100,self.ensure_on_top)
    def ensure_on_top(self):
        self.raise_()
        try:subprocess.run(["wmctrl","-i","-r",hex(int(self.winId())),"-b","add,above,sticky"],check=False,timeout=2)
        except Exception:pass
    def clear(self):
        while self.box.count():
            x=self.box.takeAt(0); w=x.widget()
            if w:w.deleteLater()
    def eventFilter(self,obj,event):
        if hasattr(self,"area") and obj is self.area.viewport() and event.type()==QEvent.Resize:QTimer.singleShot(0,self.position_floating_tutor)
        return super().eventFilter(obj,event)
    def position_floating_tutor(self):
        if not hasattr(self,"floating_tutor_button"):return
        viewport=self.area.viewport(); button=self.floating_tutor_button; button.move(max(8,viewport.width()-button.width()-18),max(8,viewport.height()-button.height()-16)); button.raise_()
    def update_floating_tutor(self):
        visible=bool(self.expanded and self.view_mode=="learn" and self.learning_mode=="curriculum" and self.floating_tutor_available)
        self.floating_tutor_button.setVisible(visible)
        if visible:self.position_floating_tutor()
    def setup_vocab_shortcuts(self):
        self.vocab_shortcuts=[]
        bindings=(("Space",self.reveal_vocab_word),("Return",self.reveal_vocab_word),("Left",self.previous_vocab_word),("Right",self.next_vocab_word),("R",self.speak_current_vocab_word),("1",lambda:self.rate_vocab_shortcut("forgot")),("2",lambda:self.rate_vocab_shortcut("fuzzy")),("3",lambda:self.rate_vocab_shortcut("remembered")))
        for key,handler in bindings:
            shortcut=QShortcut(QKeySequence(key),self); shortcut.activated.connect(handler); shortcut.setEnabled(False); self.vocab_shortcuts.append(shortcut)
    def update_vocab_shortcuts(self):
        active=bool(self.expanded and self.view_mode=="learn" and self.learning_mode=="vocabulary")
        for shortcut in getattr(self,"vocab_shortcuts",[]):shortcut.setEnabled(active)
    def refresh(self,render=True,scan_windows=True):
        if scan_windows:
            self.windows=scan(); active=active_window_id(); seen_changed=False
            for w in self.windows:
                try:is_active=int(w["id"],16)==active
                except Exception:is_active=False
                if is_active and w["completed"]>self.seen.get(w["path"],0):self.seen[w["path"]]=w["completed"]; seen_changed=True
            if seen_changed:SEEN_FILE.write_text(json.dumps(self.seen,ensure_ascii=False,indent=2))
        unread=sum(w["completed"]>self.seen.get(w["path"],0) for w in self.windows); self.running_count=sum(w["status"]=="正在运行" for w in self.windows); self.done_count=sum(w["status"]=="运行结束" for w in self.windows)
        active_todos=[t for t in self.todos if not t.get("done")]; done_today=[t for t in self.todos if t.get("done") and t.get("done_date")==datetime.now().strftime("%Y-%m-%d")]
        if self.view_mode=="monitor":
            notice=f" · {unread} 待查看" if unread else ""; self.summary.setText(f"{self.running_count} 正在运行 · {self.done_count} 已完成{notice}")
        elif self.view_mode=="todo":
            focused=[todo for todo in self.todos if todo.get("active") and not todo.get("done")]; self.summary.setText(f"正在做 {len(focused)} 项 · 今天完成 {len(done_today)}" if focused else f"{len(active_todos)} 项待办 · 今天完成 {len(done_today)}")
        elif self.view_mode=="learn":
            bundle=self.curriculum_library.get(self.curriculum_domain_id) if self.learning_mode=="curriculum" else None
            if bundle:
                path=self.curriculum_library.path(bundle,self.curriculum_store.selected_path(bundle)); stats=self.curriculum_store.stats(bundle,path)
                self.summary.setText(f"学习 {stats['mastered']}/{stats['total']}")
            elif self.learning_mode=="vocabulary":
                stats=self.vocab_store.stats(self.vocab_words); self.summary.setText(f"单词 今日 {stats['daily']['reviewed']} · 待复习 {stats['due']}")
            else:self.summary.setText(f"{self.running_count} 个任务运行中 · {len(self.feed_items)} 条前沿卡片")
        else:
            cpu=self.system_metrics.get("cpu",{}).get("percent",0); memory=self.system_metrics.get("memory",{}).get("percent",0); gpu=self.system_metrics.get("gpu",[]); gpu_text=f"GPU {gpu[0].get('percent',0):.0f}%" if gpu else "GPU --"
            self.summary.setText(f"CPU {cpu:.0f}% · 内存 {memory:.0f}% · {gpu_text}")
        self.update_tabs(); self.update_vocab_shortcuts(); self.bubble.setUnread(unread); self.bubble.setToolTip(f"运行 {self.running_count} · 完成 {self.done_count} · 待查看 {unread} · 今日待办 {len(active_todos)}")
        if not render:return
        self.floating_tutor_available=False; self.clear()
        if self.view_mode=="monitor":
            self.window_panel()
            for t in self.tasks:self.task_card(t)
            self.account_panel()
        elif self.view_mode=="todo":self.todo_panel()
        elif self.view_mode=="learn":self.learning_panel()
        else:self.system_panel()
        self.box.addStretch(); self.update_floating_tutor()
    def schedule_system_sample(self):
        if self.view_mode!="system":return
        if self.system_future and not self.system_future.done():return
        self.system_future=self.system_executor.submit(self.system_monitor.snapshot)
        QTimer.singleShot(80,self.poll_system_sample)
    def poll_system_sample(self):
        if not self.system_future:return
        if not self.system_future.done():QTimer.singleShot(80,self.poll_system_sample); return
        try:
            self.system_metrics=self.system_future.result(); cpu=self.system_metrics["cpu"]; memory=self.system_metrics["memory"]; gpu=self.system_metrics["gpu"]; disks=self.system_metrics["disks"]
            self.system_history["cpu"].append(cpu.get("percent",0)); self.system_history["memory"].append(memory.get("percent",0)); self.system_history["gpu"].append(gpu[0].get("percent",0) if gpu else 0); self.system_history["disk"].append(disks[0].get("percent",0) if disks else 0)
        except Exception:
            pass
        self.system_future=None
        if self.view_mode=="system":self.refresh(render=True)
    def system_card(self,title,value,detail,color,key):
        card=QFrame(); card.setObjectName("systemMetric"); card.setMinimumHeight(86); card.setStyleSheet("QFrame#systemMetric{background:transparent;border:0} QLabel{background:transparent;border:0}"); layout=QVBoxLayout(card); layout.setContentsMargins(12,7,12,7); layout.setSpacing(1)
        label=QLabel(title); label.setStyleSheet("color:#64748b;font-size:10px;font-weight:700"); layout.addWidget(label)
        row=QHBoxLayout(); row.setSpacing(7); number=QLabel(value); number.setFont(QFont("Noto Sans CJK SC",19,QFont.Bold)); number.setStyleSheet(f"color:{color}"); row.addWidget(number); row.addStretch(); spark=Sparkline(color); spark.set_values(self.system_history.get(key,[])); spark.setFixedSize(66,25); row.addWidget(spark); layout.addLayout(row)
        note=QLabel(detail); note.setStyleSheet("color:#94a3b8;font-size:9px"); note.setWordWrap(False); note.setToolTip(detail); layout.addWidget(note)
        return card
    def system_panel(self):
        metrics=self.system_metrics; cpu=metrics.get("cpu",{}); memory=metrics.get("memory",{}); gpus=metrics.get("gpu",[]); disks=metrics.get("disks",[]); network=metrics.get("network",{}); disk_io=metrics.get("disk_io",{})
        panel=QFrame(); panel.setObjectName("systemPanel"); panel.setStyleSheet("QFrame#systemPanel{background:#f8fafc;border:1px solid #e2e8f0;border-radius:11px} QLabel{background:transparent}"); outer=QVBoxLayout(panel); outer.setSizeConstraint(QLayout.SetMinimumSize); outer.setContentsMargins(14,12,14,14); outer.setSpacing(8)
        head=QHBoxLayout(); title=QLabel("系统监控"); title.setFont(QFont("Noto Sans CJK SC",16,QFont.Bold)); title.setStyleSheet("color:#0f172a"); head.addWidget(title); subtitle=QLabel("训练时的资源占用，最近趋势仅保留在内存中"); subtitle.setStyleSheet("color:#64748b;font-size:10px"); head.addWidget(subtitle); head.addStretch(); live=QLabel("●  2 秒刷新"); live.setStyleSheet("color:#047857;background:#ecfdf5;padding:4px 8px;border-radius:6px;font-size:10px;font-weight:700"); head.addWidget(live); outer.addLayout(head)
        temp=f" · {cpu.get('temperature'):.0f}°C" if cpu.get("temperature") else ""; memory_detail=f"已用 {format_bytes(memory.get('used'))} · 可用 {format_bytes(memory.get('available'))}" if memory.get("total") else "等待采样"
        gpu_util=max((g.get("percent",0) for g in gpus),default=0); gpu_used=sum(g.get("used",0) for g in gpus); gpu_total=sum(g.get("total",0) for g in gpus); gpu_value=f"{gpu_util:.0f}%" if gpus else "--"; gpu_detail=(f"{len(gpus)} 张 · 显存 {format_bytes(gpu_used)} / {format_bytes(gpu_total)}" if gpus else "未检测到 NVIDIA GPU")
        disk=disks[0] if disks else {}; disk_value=f"{disk.get('percent',0):.0f}%" if disk else "--"; disk_detail=f"{len(disks)} 个挂载点 · {format_bytes(disk.get('free'))} 可用" if disk else "等待采样"
        overview=QFrame(); overview.setObjectName("systemOverview"); overview.setStyleSheet("QFrame#systemOverview{background:white;border:1px solid #e2e8f0;border-radius:9px}"); metrics_row=QHBoxLayout(overview); metrics_row.setContentsMargins(0,3,0,3); metrics_row.setSpacing(0)
        cards=(("CPU",f"{cpu.get('percent',0):.0f}%",f"{cpu.get('cores',0)} 核 · 负载 {cpu.get('load',0):.2f}{temp}","#2563eb","cpu"),("内存",f"{memory.get('percent',0):.0f}%",memory_detail,"#7c3aed","memory"),("GPU / 显存",gpu_value,gpu_detail,"#ea580c","gpu"),("磁盘",disk_value,disk_detail,"#059669","disk"))
        for index,args in enumerate(cards):
            metrics_row.addWidget(self.system_card(*args),1)
            if index<len(cards)-1:
                divider=QFrame(); divider.setFrameShape(QFrame.VLine); divider.setStyleSheet("color:#e2e8f0;background:#e2e8f0"); divider.setFixedWidth(1); metrics_row.addWidget(divider)
        outer.addWidget(overview)
        details=QFrame(); details.setObjectName("systemDetails"); details.setMinimumHeight(49); details.setStyleSheet("QFrame#systemDetails{background:white;border:1px solid #e2e8f0;border-radius:9px}"); detail_grid=QGridLayout(details); detail_grid.setContentsMargins(12,7,12,7); detail_grid.setHorizontalSpacing(28)
        detail_grid.addWidget(QLabel("网络"),0,0); detail_grid.addWidget(QLabel(f"↓ {format_rate(network.get('download',0))}   ↑ {format_rate(network.get('upload',0))}"),1,0); detail_grid.addWidget(QLabel("磁盘读写"),0,1); detail_grid.addWidget(QLabel(f"读 {format_rate(disk_io.get('read',0))}   写 {format_rate(disk_io.get('write',0))}"),1,1); detail_grid.addWidget(QLabel("Swap"),0,2); detail_grid.addWidget(QLabel(f"{memory.get('swap_percent',0):.0f}% · {format_bytes(memory.get('swap_used'))} / {format_bytes(memory.get('swap_total'))}"),1,2)
        for i in range(3):detail_grid.itemAtPosition(0,i).widget().setStyleSheet("color:#64748b;font-size:10px;font-weight:700"); detail_grid.itemAtPosition(1,i).widget().setStyleSheet("color:#0f172a;font-size:11px;font-weight:600")
        outer.addWidget(details)
        disk_box=QFrame(); disk_box.setObjectName("diskBox"); disk_box.setMinimumHeight(40+len(disks)*36); disk_box.setStyleSheet("QFrame#diskBox{background:white;border:1px solid #e2e8f0;border-radius:9px}"); disk_layout=QVBoxLayout(disk_box); disk_layout.setContentsMargins(12,8,12,9); disk_layout.setSpacing(5); disk_head=QHBoxLayout(); disk_title=QLabel("磁盘空间"); disk_title.setStyleSheet("color:#0f172a;font-weight:700"); disk_head.addWidget(disk_title); disk_head.addStretch(); disk_count=QLabel(f"{len(disks)} 个本地挂载"); disk_count.setStyleSheet("color:#64748b;font-size:10px"); disk_head.addWidget(disk_count); disk_layout.addLayout(disk_head)
        for disk_item in disks:
            disk_row=QFrame(); disk_row.setObjectName("diskRow"); disk_row.setMinimumHeight(32); disk_row.setStyleSheet("QFrame#diskRow{background:#f8fafc;border:0;border-radius:6px}"); disk_line=QHBoxLayout(disk_row); disk_line.setContentsMargins(8,5,8,5); disk_line.setSpacing(8); mount_label=QLabel(disk_item.get("mount","/")); mount_label.setMinimumWidth(105); mount_label.setStyleSheet("color:#0f172a;font-size:10px;font-weight:700"); disk_line.addWidget(mount_label); disk_bar=QProgressBar(); disk_bar.setTextVisible(False); disk_bar.setRange(0,100); disk_bar.setValue(max(0,min(100,int(disk_item.get('percent',0))))); disk_bar.setStyleSheet("QProgressBar{height:6px;border:0;border-radius:3px;background:#e2e8f0} QProgressBar::chunk{background:#10b981;border-radius:3px}"); disk_line.addWidget(disk_bar,1); usage=QLabel(f"{format_bytes(disk_item.get('used'))} / {format_bytes(disk_item.get('total'))}"); usage.setStyleSheet("color:#475569;font-size:10px"); disk_line.addWidget(usage); percent_label=QLabel(f"{disk_item.get('percent',0):.0f}%"); percent_label.setMinimumWidth(34); percent_label.setAlignment(Qt.AlignRight|Qt.AlignVCenter); percent_label.setStyleSheet("color:#047857;font-size:10px;font-weight:700"); disk_line.addWidget(percent_label); disk_row.setToolTip(f"{disk_item.get('source','')} · {disk_item.get('fstype','')} · 可用 {format_bytes(disk_item.get('free'))}"); disk_layout.addWidget(disk_row)
        outer.addWidget(disk_box)
        if gpus:
            gpu_box=QFrame(); gpu_box.setObjectName("gpuBox"); gpu_box.setStyleSheet("QFrame#gpuBox{background:white;border:1px solid #e2e8f0;border-radius:9px}"); gpu_layout=QVBoxLayout(gpu_box); gpu_layout.setContentsMargins(12,7,12,7); gpu_title=QLabel("GPU 详情"); gpu_title.setStyleSheet("color:#0f172a;font-weight:700"); gpu_layout.addWidget(gpu_title)
            for gpu in gpus:
                row=QLabel(f"GPU {gpu.get('index')}  {gpu.get('name','未知')}    利用率 {gpu.get('percent',0):.0f}%    显存 {format_bytes(gpu.get('used'))}/{format_bytes(gpu.get('total'))}    温度 {gpu.get('temperature',0):.0f}°C    功耗 {gpu.get('power',0):.0f} W"); row.setStyleSheet("color:#475569;font-size:11px"); gpu_layout.addWidget(row)
            outer.addWidget(gpu_box)
        process_box=QFrame(); process_box.setObjectName("processBox"); process_box.setStyleSheet("QFrame#processBox{background:white;border:1px solid #e2e8f0;border-radius:9px}"); process_layout=QVBoxLayout(process_box); process_layout.setContentsMargins(12,7,12,9); process_title=QLabel("高占用进程"); process_title.setStyleSheet("color:#0f172a;font-weight:700"); process_layout.addWidget(process_title); table=QTableWidget(min(5,len(metrics.get('processes',[]))),4); table.setHorizontalHeaderLabels(["进程","CPU","内存","PID"]); table.verticalHeader().setVisible(False); table.setEditTriggers(QAbstractItemView.NoEditTriggers); table.setSelectionMode(QAbstractItemView.NoSelection); table.setFocusPolicy(Qt.NoFocus); table.setShowGrid(False); table.setAlternatingRowColors(True); table.setMinimumHeight(135); table.setStyleSheet("QTableWidget{border:0;background:white;alternate-background-color:#f8fafc;color:#334155} QHeaderView::section{background:#f1f5f9;color:#64748b;border:0;padding:5px;font-size:10px;font-weight:700}"); table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        for index,process in enumerate(metrics.get("processes",[])[:5]):
            values=(process.get("name","进程"),f"{process.get('cpu',0):.1f}%",format_bytes(process.get("memory",0)),process.get("pid",""))
            for column,value in enumerate(values):table.setItem(index,column,QTableWidgetItem(str(value)))
        process_layout.addWidget(table); outer.addWidget(process_box); self.box.addWidget(panel)
    def window_panel(self):
        p=QFrame(); p.setStyleSheet("QFrame{background:#eef6ff;border-radius:10px} QLabel{background:transparent}"); v=QVBoxLayout(p); v.setSpacing(8)
        head=QHBoxLayout(); heading=QLabel("项目窗口"); heading.setFont(QFont("Noto Sans CJK SC",15,QFont.Bold)); heading.setStyleSheet("color:#0f172a"); head.addWidget(heading); head.addStretch(); running=QLabel(f"●  正在运行 {self.running_count}"); running.setStyleSheet("color:#1d4ed8;background:#dbeafe;padding:4px 9px;border-radius:6px;font-size:11px;font-weight:700"); head.addWidget(running); done=QLabel(f"✓  已完成 {self.done_count}"); done.setStyleSheet("color:#047857;background:#d1fae5;padding:4px 9px;border-radius:6px;font-size:11px;font-weight:700"); head.addWidget(done); v.addLayout(head)
        hint=QLabel("自动监控运行状态 · 当前聚焦的窗口会自动标记为已查看"); hint.setStyleSheet("color:#64748b;font-size:11px"); v.addWidget(hint)
        for w in self.windows:
            unread=w["completed"]>self.seen.get(w["path"],0); state="运行结束，尚未查看" if unread else w["status"]
            card=QFrame(); card.setObjectName("windowCard"); card.setStyleSheet("QFrame#windowCard{background:white;border:1px solid #dbeafe;border-radius:8px}"); h=QHBoxLayout(card); h.setContentsMargins(12,10,10,10)
            dot=QLabel("●" if unread else ("●" if state=="正在运行" else "○")); dot.setStyleSheet(f"color:{'#ef4444' if unread else ('#2563eb' if state=='正在运行' else '#94a3b8')};font-size:18px"); h.addWidget(dot)
            info=QVBoxLayout(); name=QLabel(w["folder"]); name.setFont(QFont("Noto Sans CJK SC",14,QFont.Bold)); info.addWidget(name)
            meta=QHBoxLayout(); account=QLabel(w["account"]); account.setStyleSheet("color:#4338ca;background:#eef2ff;padding:3px 8px;border-radius:5px;font-size:12px"); meta.addWidget(account); status=QLabel("待查看" if unread else state); status.setStyleSheet(f"color:{'#b91c1c' if unread else '#475569'};background:{'#fee2e2' if unread else '#f1f5f9'};padding:3px 8px;border-radius:5px;font-weight:{'700' if unread else '500'};font-size:12px"); meta.addWidget(status); meta.addStretch(); info.addLayout(meta)
            open_ideas=self.idea_store.list(w["path"],include_done=False)
            if open_ideas:
                preview=QLabel("✦  "+open_ideas[0].get("text","")[:72]); preview.setToolTip(open_ideas[0].get("text","")); preview.setStyleSheet("color:#7c3aed;font-size:10px"); info.addWidget(preview)
            h.addLayout(info,1)
            conversations,total_conversations=project_conversations(w["path"])
            chats=QToolButton(); chats.setText(f"对话 {total_conversations}  ▾"); chats.setPopupMode(QToolButton.InstantPopup); chats.setCursor(Qt.PointingHandCursor); chats.setToolTip("只显示属于这个项目的 Codex 对话"); chats.setStyleSheet("QToolButton{padding:7px 11px;background:#f5f3ff;color:#6d28d9;border:1px solid #c4b5fd;border-radius:7px;font-weight:700} QToolButton:hover{background:#ede9fe} QToolButton::menu-indicator{image:none}")
            chat_menu=QMenu(chats); caption=chat_menu.addAction(f"此项目最近对话 · 共 {total_conversations} 条"); caption.setEnabled(False)
            if conversations:chat_menu.addSeparator()
            for conversation in conversations:
                stamp=datetime.fromtimestamp(conversation["mtime"]).strftime("%m-%d %H:%M")
                action=chat_menu.addAction(f"{conversation['title']}    {stamp}"); action.setToolTip(conversation["title"]); action.triggered.connect(lambda _,x=w,c=conversation:self.open_conversation(x,c))
            if not conversations:empty=chat_menu.addAction("这个项目还没有本地对话"); empty.setEnabled(False)
            if total_conversations>len(conversations):more=chat_menu.addAction(f"另外 {total_conversations-len(conversations)} 条较早对话暂未展开"); more.setEnabled(False)
            chats.setMenu(chat_menu); h.addWidget(chats)
            pending=self.pending_accounts.get(w["path"]); selected_name=pending.get("name") if pending else w["account"]
            selector=QToolButton(); selector.setText(f"{selected_name}  {'待切换' if pending else '▾'}"); selector.setPopupMode(QToolButton.InstantPopup); selector.setCursor(Qt.PointingHandCursor); selector.setStyleSheet("QToolButton{padding:7px 11px;background:#fff7ed;color:#c2410c;border:1px solid #fdba74;border-radius:7px;font-weight:700} QToolButton:hover{background:#ffedd5} QToolButton::menu-indicator{image:none}" if pending else "QToolButton{padding:7px 11px;background:#f8fafc;color:#334155;border:1px solid #dbe3ed;border-radius:7px} QToolButton:hover{background:#eef2ff;color:#4338ca;border-color:#a5b4fc} QToolButton::menu-indicator{image:none}")
            menu=QMenu(selector)
            available=[]
            for profile in profiles():
                primary=(profile.get("limits",{}).get("primary") or {}); remaining=primary.get("remainingPercent")
                if remaining is None or remaining>0:available.append(profile)
            for profile in available:
                remaining=(profile.get("limits",{}).get("primary") or {}).get("remainingPercent"); action=menu.addAction(("✓  " if profile.get("name")==selected_name else "    ")+f"{profile.get('name','未命名')}    {remaining if remaining is not None else '--'}%"); action.triggered.connect(lambda _,x=w,p=profile:self.select_account(x,p))
            api_profiles=api_provider_profiles()
            if available and api_profiles:menu.addSeparator()
            for api_profile in api_profiles:
                api_action=menu.addAction(("✓  " if api_profile.get("name")==selected_name else "    ")+f"{api_profile.get('name')}    按量计费")
                api_action.setEnabled(api_profile.get("configured",False)); api_action.setToolTip("手动选择的独立 API 接口，不会自动接管 Plus")
                api_action.triggered.connect(lambda _,x=w,p=api_profile:self.select_account(x,p))
            if not available and not any(p.get("configured") for p in api_profiles):disabled=menu.addAction("暂无可用账号"); disabled.setEnabled(False)
            selector.setMenu(menu); selector.setToolTip("先选择账号，再点聚焦应用切换"); h.addWidget(selector)
            ideas=QPushButton(f"灵感 {len(open_ideas)}" if open_ideas else "记灵感"); ideas.setToolTip("记录和管理这个项目暂未实现的想法"); ideas.setStyleSheet("background:#f5f3ff;color:#6d28d9;border:1px solid #ddd6fe"); ideas.clicked.connect(lambda _,x=w:self.open_project_ideas(x)); h.addWidget(ideas)
            create=QPushButton("加待办"); create.setToolTip("把这个项目加入今日待办"); create.clicked.connect(lambda _,x=w:self.prefill_todo(x)); h.addWidget(create)
            focus=QPushButton("切换并聚焦" if pending else ("查看" if unread else "聚焦")); focus.setStyleSheet("background:#ea580c;color:white;border:0" if pending else ("background:#dc2626;color:white;border:0" if unread else "background:#2563eb;color:white;border:0")); focus.clicked.connect(lambda _,x=w:self.focus(x["id"])); h.addWidget(focus); v.addWidget(card)
        self.box.addWidget(p)
    def open_project_ideas(self,window):
        dialog=ProjectIdeasDialog(self.idea_store,window,self); dialog.exec() if hasattr(dialog,"exec") else dialog.exec_(); self.refresh()
    def account_panel(self):
        rows=profiles(); api_profiles=api_provider_profiles(); api_ready=sum(p.get("configured",False) for p in api_profiles); p=QFrame(); p.setObjectName("accountPanel"); p.setStyleSheet("QFrame#accountPanel{background:#f7fcfa;border:1px solid #dbeee7;border-radius:11px} QLabel{background:transparent}"); v=QVBoxLayout(p); v.setContentsMargins(13,10,13,12); v.setSpacing(7); head=QHBoxLayout(); heading=QLabel("账号额度"); heading.setFont(QFont("Noto Sans CJK SC",14,QFont.Bold)); heading.setStyleSheet("color:#0f172a"); head.addWidget(heading); subtitle=QLabel("自动读取 Codex Switch"); subtitle.setStyleSheet("color:#64748b;font-size:10px"); head.addWidget(subtitle); head.addStretch(); count=QLabel(f"{len(rows)} 个 Plus · {api_ready} 个 API 备用"); count.setStyleSheet("color:#047857;background:#ecfdf5;padding:3px 7px;border-radius:5px;font-size:10px;font-weight:700"); head.addWidget(count); v.addLayout(head); h=QHBoxLayout(); h.setSpacing(7)
        for profile in rows:
            limits=profile.get("limits",{}); primary=limits.get("primary") or {}; secondary=limits.get("secondary") or {}
            card=QFrame(); card.setObjectName("quotaCard"); card.setStyleSheet("QFrame#quotaCard{background:white;border:1px solid #dbe7e2;border-radius:8px} QLabel{background:transparent}"); c=QVBoxLayout(card); c.setContentsMargins(9,7,9,8); c.setSpacing(3); name_row=QHBoxLayout(); name=QLabel(profile.get("name","未命名")); name.setFont(QFont("Noto Sans CJK SC",11,QFont.Bold)); name.setStyleSheet("color:#0f172a"); name_row.addWidget(name,1); windows_count=sum(bool(window) for window in (primary,secondary)); window_badge=QLabel(f"{windows_count} 个额度周期"); window_badge.setStyleSheet("color:#64748b;background:#f1f5f9;padding:2px 5px;border-radius:4px;font-size:8px"); name_row.addWidget(window_badge); c.addLayout(name_row)
            for label,window in (("5 小时",primary),("每周",secondary)):
                value=window.get("remainingPercent"); row=QHBoxLayout(); caption=QLabel(label); caption.setStyleSheet("color:#64748b;font-size:9px;font-weight:700"); row.addWidget(caption); row.addStretch(); number=QLabel(f"{value if value is not None else '--'}%"); number.setStyleSheet("color:#047857;font-size:10px;font-weight:700"); row.addWidget(number); c.addLayout(row); reset_text=f"{remaining_label(window.get('resetsAt'))} · {reset_label(window.get('resetsAt'))}"; reset=QLabel(reset_text); reset.setStyleSheet("color:#94a3b8;font-size:8px"); reset.setToolTip(f"{label}额度刷新：{reset_text}"); c.addWidget(reset); bar=QProgressBar(); bar.setTextVisible(False); bar.setRange(0,100); bar.setValue(value or 0); bar.setFixedHeight(5); c.addWidget(bar)
            h.addWidget(card,1)
        if not rows:
            empty=QLabel("暂未读取到账号额度"); empty.setAlignment(Qt.AlignCenter); empty.setStyleSheet("color:#94a3b8;padding:14px"); h.addWidget(empty,1)
        v.addLayout(h); self.box.addWidget(p)
    def learning_panel(self):
        panel=QFrame(); panel.setObjectName("learningPanel"); panel.setStyleSheet("QFrame#learningPanel{background:#f7f8fc;border:1px solid #e2e8f0;border-radius:11px} QLabel{background:transparent}"); v=QVBoxLayout(panel); v.setSizeConstraint(QLayout.SetMinimumSize); v.setContentsMargins(14,12,14,14); v.setSpacing(8)
        curriculum_mode=self.learning_mode=="curriculum"; vocabulary_mode=self.learning_mode=="vocabulary"; head=QHBoxLayout(); titles=QVBoxLayout(); titles.setSpacing(0); title=QLabel("系统学习" if curriculum_mode else ("单词闪卡" if vocabulary_mode else "前沿追踪")); title.setFont(QFont("Noto Sans CJK SC",16,QFont.Bold)); title.setStyleSheet("color:#0f172a"); titles.addWidget(title); subtitle=QLabel("沿稳定知识框架持续推进" if curriculum_mode else ("主动回忆 · 间隔复习 · 碎片时间" if vocabulary_mode else "兴趣只决定排序，重大更新和未知方向不会被过滤")); subtitle.setStyleSheet("color:#64748b;font-size:10px"); titles.addWidget(subtitle); head.addLayout(titles); head.addStretch()
        needs_review=[w for w in self.windows if w.get("completed",0)>self.seen.get(w.get("path",""),0)]; state_text=f"● {self.running_count} 运行中 · {len(needs_review)} 待处理"; state=QLabel(state_text); state.setStyleSheet(f"color:{'#b91c1c' if needs_review else '#1d4ed8'};background:{'#fee2e2' if needs_review else '#dbeafe'};padding:4px 9px;border-radius:6px;font-weight:700"); head.addWidget(state); v.addLayout(head)
        if needs_review:
            alert=QFrame(); alert.setObjectName("workAlert"); alert.setStyleSheet("QFrame#workAlert{background:#fff1f2;border:1px solid #fda4af;border-radius:9px} QLabel{background:transparent}"); alerts=QVBoxLayout(alert); alerts.setContentsMargins(11,8,9,8); label=QLabel(f"有 {len(needs_review)} 个 Codex 任务已经完成，需要你处理"); label.setStyleSheet("color:#9f1239;font-weight:700"); alerts.addWidget(label)
            for window in needs_review:
                row=QHBoxLayout(); name=QLabel(window.get("folder","未命名项目")); name.setStyleSheet("color:#1e293b;font-weight:600"); row.addWidget(name,1); view=QPushButton("立即查看"); view.setStyleSheet("background:#dc2626;color:white;border:0;font-weight:700"); view.clicked.connect(lambda _,x=window:self.focus(x["id"])); row.addWidget(view); alerts.addLayout(row)
            v.addWidget(alert)
        mode_bar=QFrame(); mode_bar.setObjectName("learningModeBar"); mode_bar.setStyleSheet("QFrame#learningModeBar{background:#eef2f7;border:0;border-radius:9px}"); mode_row=QHBoxLayout(mode_bar); mode_row.setContentsMargins(4,4,4,4); mode_row.setSpacing(4)
        for mode,label in (("frontier","前沿追踪"),("curriculum","系统学习"),("vocabulary","单词闪卡")):
            button=QPushButton(label); active=self.learning_mode==mode; button.setStyleSheet("background:white;color:#3730a3;border:1px solid #dbe3ed;font-weight:700" if active else "background:transparent;color:#64748b;border:0"); button.clicked.connect(lambda _,value=mode:self.switch_learning_mode(value)); mode_row.addWidget(button)
        mode_row.addStretch(); mode_hint=QLabel("固定框架 · 本地进度" if curriculum_mode else ("本地词库 · 间隔复习" if vocabulary_mode else "动态发现 · 有界推荐")); mode_hint.setStyleSheet("color:#94a3b8;font-size:9px;padding-right:6px"); mode_row.addWidget(mode_hint); v.addWidget(mode_bar)
        if curriculum_mode:
            self.curriculum_panel(v,panel); return
        if vocabulary_mode:
            self.vocabulary_panel(v,panel); return
        control_bar=QFrame(); control_bar.setObjectName("learningControls"); control_bar.setStyleSheet("QFrame#learningControls{background:white;border:1px solid #e2e8f0;border-radius:8px}"); controls=QHBoxLayout(control_bar); controls.setContentsMargins(9,6,8,6); hint=QLabel("宽召回 · 质量门槛 · "+self.learning_context.get("label","具身智能前沿")); hint.setStyleSheet("color:#475569;font-size:10px"); controls.addWidget(hint); controls.addStretch(); settings=QPushButton("推荐设置"); settings.setToolTip("打开 learning_preferences.json"); settings.clicked.connect(self.open_learning_preferences); controls.addWidget(settings); duration_label=QLabel("时长"); duration_label.setStyleSheet("color:#64748b;font-size:10px"); controls.addWidget(duration_label)
        duration=QComboBox(); duration.addItem("3 分钟",3); duration.addItem("5 分钟",5); duration.addItem("10 分钟",10); duration.addItem("20 分钟",20); duration.setCurrentIndex(duration.findData(getattr(self,"learning_minutes",5))); duration.currentIndexChanged.connect(lambda:self.set_learning_minutes(duration.currentData())); controls.addWidget(duration)
        refresh=QPushButton("获取最新"); refresh.setEnabled(not (self.feed_future and not self.feed_future.done())); refresh.setStyleSheet("background:#4f46e5;color:white;border:0;font-weight:700"); refresh.clicked.connect(self.start_learning_feed); controls.addWidget(refresh); v.addWidget(control_bar)
        if self.feed_future and not self.feed_future.done():
            loading=QLabel("正在扫描 arXiv、GitHub、Hugging Face 和官方 Demo，并计算质量与多通道得分…"); loading.setAlignment(Qt.AlignCenter); loading.setStyleSheet("color:#1d4ed8;background:white;padding:22px;border-radius:9px;font-weight:700"); v.addWidget(loading)
        elif not self.feed_items:
            empty=QLabel("点击“获取最新”生成具身前沿学习包\n质量不足时会少显示，不会为了凑数填充内容"); empty.setAlignment(Qt.AlignCenter); empty.setStyleSheet("color:#64748b;background:white;padding:26px;border-radius:9px"); v.addWidget(empty)
        if self.feed_error:
            warning=QLabel("部分来源或 AI 摘要暂不可用，其他内容仍可正常阅读 · "+self.feed_error[:100]); warning.setWordWrap(True); warning.setStyleSheet("color:#b45309;background:#fffbeb;padding:7px 9px;border-radius:6px;font-size:10px"); v.addWidget(warning)
        channel_colors={"core":("#2563eb","#eff6ff"),"adjacent":("#7c3aed","#f5f3ff"),"major":("#dc2626","#fff1f2"),"emerging":("#d97706","#fffbeb"),"serendipity":("#059669","#ecfdf5")}; kind_labels={"paper":"论文","repo":"代码","model":"模型","video":"Demo"}
        for index,item in enumerate(self.feed_items):
            read=bool(item.get("read")); channel=item.get("primary_channel","core"); accent,badge_bg=channel_colors.get(channel,channel_colors["core"]); featured=index==0; card=QFrame(); card.setObjectName("learningCard"); card.setMinimumHeight(190 if featured else 164); card.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Minimum); card.setStyleSheet(f"QFrame#learningCard{{background:{'#fbfcfe' if read else 'white'};border:1px solid {'#e2e8f0' if read else '#dbe3ed'};border-left:{'4px' if featured else '3px'} solid {accent};border-radius:9px}} QLabel{{background:transparent;border:0}}"); c=QVBoxLayout(card); c.setContentsMargins(12 if featured else 10,10 if featured else 8,11,9); c.setSpacing(5)
            badges=QHBoxLayout(); channel_badge=QLabel(item.get("channel_label","核心关注")); channel_badge.setStyleSheet(f"color:{accent};background:{badge_bg};padding:3px 7px;border-radius:5px;font-size:9px;font-weight:700"); badges.addWidget(channel_badge); media_label="▶ 有 Demo" if item.get("has_video") or item.get("kind")=="video" else kind_labels.get(item.get("kind"),"资料"); media=QLabel(media_label); media.setStyleSheet("color:#475569;background:#f1f5f9;padding:3px 7px;border-radius:5px;font-size:9px;font-weight:700"); badges.addWidget(media); difficulty=QLabel(item.get("difficulty","中等")); difficulty.setStyleSheet("color:#64748b;font-size:9px"); badges.addWidget(difficulty); badges.addStretch(); duration_badge=QLabel(f"{item.get('seconds',45)} 秒看懂"); duration_badge.setStyleSheet("color:#64748b;font-size:9px"); badges.addWidget(duration_badge); c.addLayout(badges)
            name=QLabel(item.get("title","未命名内容")); name.setWordWrap(True); name.setFont(QFont("Noto Sans CJK SC",15 if featured else 13,QFont.Bold)); name.setStyleSheet("color:#64748b" if read else "color:#0f172a"); c.addWidget(name)
            sources=" / ".join(item.get("sources") or [item.get("source","")]); meta_parts=[item.get("published","日期未知"),sources];
            if read:meta_parts.append("已读")
            meta=QLabel("  ·  ".join(str(part) for part in meta_parts if part)); meta.setStyleSheet("color:#94a3b8;font-size:9px"); c.addWidget(meta)
            summary=QLabel("<b>30 秒看懂</b>  "+item.get("summary","")); summary.setWordWrap(True); summary.setTextFormat(Qt.RichText); summary.setStyleSheet("color:#334155;font-size:11px"); c.addWidget(summary)
            insight=QFrame(); insight.setObjectName("learningInsight"); insight.setStyleSheet("QFrame#learningInsight{background:#f8fafc;border:0;border-radius:6px} QLabel{background:transparent;border:0}"); insight_layout=QVBoxLayout(insight); insight_layout.setContentsMargins(8,5,8,5); insight_layout.setSpacing(3); delta=QLabel("<b>相对已知工作</b>  "+item.get("delta","")); delta.setTextFormat(Qt.RichText); delta.setWordWrap(True); delta.setStyleSheet(f"color:{accent};font-size:10px"); insight_layout.addWidget(delta)
            if featured:
                why=QLabel("<b>为什么现在值得看</b>  "+item.get("why","")); why.setTextFormat(Qt.RichText); why.setWordWrap(True); why.setStyleSheet("color:#475569;font-size:10px"); insight_layout.addWidget(why)
            c.addWidget(insight)
            signals=QHBoxLayout(); signals.setSpacing(5)
            for signal_text in item.get("signals",[])[:3]:
                signal=QLabel(signal_text); signal.setStyleSheet("color:#475569;background:#f1f5f9;padding:2px 6px;border-radius:4px;font-size:8px"); signals.addWidget(signal)
            signals.addStretch(); c.addLayout(signals)
            bottom=QHBoxLayout(); reason=QLabel("入选原因："+item.get("recommend_reason","具身前沿")); reason.setWordWrap(True); reason.setStyleSheet("color:#64748b;font-size:9px"); bottom.addWidget(reason,1)
            resources=item.get("resources",[]); resource_button=QToolButton(); resource_button.setText(f"相关资料 {len(resources)}  ▾"); resource_button.setPopupMode(QToolButton.InstantPopup); resource_button.setStyleSheet("QToolButton{padding:6px 9px;background:white;color:#475569;border:1px solid #dbe3ed;border-radius:7px} QToolButton::menu-indicator{image:none}"); resource_menu=QMenu(resource_button)
            for resource in resources:
                resource_kind=kind_labels.get(resource.get("kind"),"资料"); action=resource_menu.addAction(f"{resource_kind}  ·  {resource.get('source','')}  ·  {resource.get('title','')[:42]}"); action.triggered.connect(lambda _,event_url=item.get("url",""),url=resource.get("url",""):self.open_learning_url(url,event_url))
            resource_button.setMenu(resource_menu); resource_button.setEnabled(bool(resources)); bottom.addWidget(resource_button)
            action_url=item.get("video_url") or item.get("url",""); primary=QPushButton("播放 Demo" if item.get("video_url") or item.get("kind")=="video" else "查看资料"); primary.setStyleSheet(f"background:{accent};color:white;border:0;font-weight:700"); primary.clicked.connect(lambda _,url=action_url,event_url=item.get("url",""):self.open_learning_url(url,event_url)); bottom.addWidget(primary); mark=QPushButton("已收藏" if item.get("saved") else "收藏"); mark.setStyleSheet("background:#ede9fe;color:#6d28d9;border:0" if item.get("saved") else ""); mark.clicked.connect(lambda _,url=item.get("url",""):self.toggle_learning_saved(url)); bottom.addWidget(mark)
            feedback=QToolButton(); feedback.setText("反馈  ▾"); feedback.setPopupMode(QToolButton.InstantPopup); feedback.setStyleSheet("QToolButton{padding:6px 9px;background:white;color:#475569;border:1px solid #dbe3ed;border-radius:7px} QToolButton::menu-indicator{image:none}"); feedback_menu=QMenu(feedback)
            for feedback_text,feedback_action in (("多推类似内容","more_like"),("不感兴趣","dismissed"),("内容太基础","too_basic"),("内容太难","too_hard")):
                action=feedback_menu.addAction(feedback_text); action.triggered.connect(lambda _,url=item.get("url",""),choice=feedback_action:self.feedback_learning(url,choice))
            feedback.setMenu(feedback_menu); bottom.addWidget(feedback); c.addLayout(bottom); v.addWidget(card)
        stats=self.feed_stats; storage=QLabel(f"有界存储：{stats.get('count',0)}/{stats.get('limit',1000)} 条 · 收藏 {stats.get('saved',0)} · {stats.get('bytes',0)/1024/1024:.1f} MB · 内容保留 60 天，热度快照保留 180 天"); storage.setAlignment(Qt.AlignCenter); storage.setStyleSheet("color:#64748b;font-size:10px;padding:6px"); v.addWidget(storage)
        self.box.addWidget(panel)
    def switch_learning_mode(self,mode):
        if mode not in ("frontier","curriculum","vocabulary") or self.learning_mode==mode:return
        if self.learning_mode=="vocabulary":self.cancel_vocab_audio(True); self.vocab_last_spoken_id=None
        self.learning_mode=mode; self.refresh(scan_windows=False)
    def current_vocab_word(self):
        return next((word for word in self.vocab_words if word["id"]==self.vocab_current_id),self.vocab_words[0] if self.vocab_words else None)
    def vocab_lexicon_name(self,item):
        if not item:return "选择词库"
        return {"文献术语精选_280":"文献术语","雅思词汇真经_扩展":"雅思词汇","高考3500词汇表":"高考词汇"}.get(item["id"],item["name"].replace("_"," "))
    def vocabulary_panel(self,v,panel):
        lexicons=self.vocab_library.lexicons(); stats=self.vocab_store.stats(self.vocab_words); word=self.current_vocab_word()
        controls=QFrame(); controls.setObjectName("vocabControls"); controls.setStyleSheet("QFrame#vocabControls{background:white;border:1px solid #e2e8f0;border-radius:9px}"); row=QHBoxLayout(controls); row.setContentsMargins(9,6,8,6); row.setSpacing(6)
        selected_lexicon=next((item for item in lexicons if item["id"]==self.vocab_lexicon_id),lexicons[0] if lexicons else None)
        selector=QToolButton(); selector.setText(f"▤  {self.vocab_lexicon_name(selected_lexicon)}   ▾"); selector.setPopupMode(QToolButton.InstantPopup); selector.setCursor(Qt.PointingHandCursor); selector.setToolTip("切换当前词库"); selector.setMinimumWidth(210); selector.setMaximumWidth(310); selector.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed); selector.setStyleSheet("QToolButton{padding:7px 11px;text-align:left;background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;border-radius:7px;font-weight:700} QToolButton:hover{background:#ffedd5;border-color:#fdba74} QToolButton::menu-indicator{image:none}")
        lexicon_menu=QMenu(selector)
        for item in lexicons:
            action=lexicon_menu.addAction(("✓  " if item["id"]==self.vocab_lexicon_id else "    ")+self.vocab_lexicon_name(item)+f"    {item['count']} 词")
            action.triggered.connect(lambda _,lexicon_id=item["id"]:self.select_vocabulary(lexicon_id))
        selector.setMenu(lexicon_menu); row.addWidget(selector)
        count_badge=QLabel(f"{selected_lexicon['count']} 词" if selected_lexicon else "0 词"); count_badge.setStyleSheet("color:#64748b;background:#f1f5f9;padding:4px 7px;border-radius:5px;font-size:9px"); row.addWidget(count_badge); row.addStretch()
        random_button=QPushButton("随机" if self.vocab_random else "顺序"); random_button.setToolTip("切换出词顺序"); random_button.clicked.connect(self.toggle_vocab_random); row.addWidget(random_button); imported=QPushButton("导入"); imported.setToolTip("导入 UTF-8 TXT 词库"); imported.clicked.connect(self.import_vocabulary); row.addWidget(imported); v.addWidget(controls)

        progress=QFrame(); progress.setObjectName("vocabProgress"); progress.setStyleSheet("QFrame#vocabProgress{background:#fff7ed;border:1px solid #fed7aa;border-radius:9px} QLabel{background:transparent}"); progress_layout=QVBoxLayout(progress); progress_layout.setContentsMargins(11,7,11,8); progress_layout.setSpacing(4); progress_top=QHBoxLayout(); today=stats["daily"]; progress_title=QLabel(f"今日 {today['reviewed']} 个"); progress_title.setStyleSheet("color:#9a3412;font-weight:700"); progress_top.addWidget(progress_title); progress_top.addStretch(); progress_meta=QLabel(f"待复习 {stats['due']} · 已学 {stats['learned']}/{stats['total']} · 收藏 {stats['favorites']}"); progress_meta.setStyleSheet("color:#c2410c;font-size:9px"); progress_top.addWidget(progress_meta); progress_layout.addLayout(progress_top); daily_bar=QProgressBar(); daily_bar.setRange(0,20); daily_bar.setValue(min(20,today["reviewed"])); daily_bar.setTextVisible(False); daily_bar.setStyleSheet("QProgressBar{height:6px;background:#ffedd5;border:0;border-radius:3px} QProgressBar::chunk{background:#fb923c;border-radius:3px}"); progress_layout.addWidget(daily_bar); v.addWidget(progress)

        if not word:
            empty=QLabel("当前没有可用词条\n点击“导入词库”添加 UTF-8 TXT 词库"); empty.setAlignment(Qt.AlignCenter); empty.setStyleSheet("color:#64748b;background:white;padding:30px;border-radius:9px"); v.addWidget(empty); self.box.addWidget(panel); return
        state=self.vocab_store.state(word["id"]); card=QFrame(); card.setObjectName("vocabCard"); card.setStyleSheet("QFrame#vocabCard{background:white;border:1px solid #fed7aa;border-radius:12px} QLabel{background:transparent;border:0}"); body=QHBoxLayout(card); body.setContentsMargins(18,14,16,15); body.setSpacing(14); text_column=QVBoxLayout(); text_column.setSpacing(7)
        meta_parts=[part for part in (word.get("pos"),word.get("category")) if part]; meta=QLabel(" · ".join(meta_parts) if meta_parts else "先回想它的含义"); meta.setStyleSheet("color:#c2410c;font-size:10px;font-weight:700"); text_column.addWidget(meta); title=QLabel(word["word"]); title.setStyleSheet("color:#0f172a;font-size:32px;font-weight:700"); title.setWordWrap(True); text_column.addWidget(title)
        if not self.vocab_revealed:
            clue="先别急着翻面，在脑中说出它的意思。"
            if word.get("example"):
                blank=word["example"].replace(word["word"],"_____").replace(word["word"].capitalize(),"_____"); clue+="\n\n例句线索："+blank
            prompt=QLabel(clue); prompt.setWordWrap(True); prompt.setStyleSheet("color:#475569;background:#f8fafc;padding:12px;border-radius:8px;font-size:13px"); text_column.addWidget(prompt)
        else:
            meaning=QLabel(word["meaning"]); meaning.setWordWrap(True); meaning.setTextInteractionFlags(Qt.TextSelectableByMouse); meaning.setStyleSheet("color:#7c2d12;background:#fff7ed;padding:12px;border-radius:8px;font-size:17px;font-weight:700"); text_column.addWidget(meaning)
            if word.get("example"):
                example=QLabel("例句  "+word["example"]); example.setWordWrap(True); example.setTextInteractionFlags(Qt.TextSelectableByMouse); example.setStyleSheet("color:#334155;font-size:12px"); text_column.addWidget(example)
            if word.get("extra"):
                extra=QLabel("拓展  "+word["extra"]); extra.setWordWrap(True); extra.setStyleSheet("color:#64748b;background:#f8fafc;padding:8px;border-radius:6px;font-size:11px"); text_column.addWidget(extra)
        actions=QHBoxLayout(); actions.setSpacing(6); previous=QPushButton("← 上一个"); previous.setToolTip("快捷键：←"); previous.setEnabled(bool(self.vocab_history)); previous.clicked.connect(self.previous_vocab_word); actions.addWidget(previous); next_word=QPushButton("下一个 →"); next_word.setToolTip("快捷键：→"); next_word.clicked.connect(self.next_vocab_word); actions.addWidget(next_word); speak=QPushButton("重播"); speak.setToolTip("重新朗读当前单词 · 快捷键：R"); speak.clicked.connect(lambda:self.speak_vocab_word(word["word"])); actions.addWidget(speak); favorite=QPushButton("已收藏" if state.get("favorite") else "收藏"); favorite.setStyleSheet("background:#fef3c7;color:#92400e;border:0" if state.get("favorite") else ""); favorite.clicked.connect(lambda:self.toggle_vocab_favorite(word["id"])); actions.addWidget(favorite); actions.addStretch()
        if not self.vocab_revealed:
            reveal=QPushButton("显示释义"); reveal.setToolTip("快捷键：空格或 Enter"); reveal.setStyleSheet("background:#f97316;color:white;border:0;font-weight:700"); reveal.clicked.connect(self.reveal_vocab_word); actions.addWidget(reveal)
        else:
            for label,rating,style in (("忘了","forgot","background:#fff1f2;color:#be123c;border:0"),("模糊","fuzzy","background:#fffbeb;color:#a16207;border:0"),("记住了","remembered","background:#059669;color:white;border:0;font-weight:700")):
                button=QPushButton(label); button.setToolTip("快捷键："+{"forgot":"1","fuzzy":"2","remembered":"3"}[rating]); button.setStyleSheet(style); button.clicked.connect(lambda _,value=rating:self.rate_vocab_word(value)); actions.addWidget(button)
        text_column.addLayout(actions); body.addLayout(text_column,1)
        cat=QLabel(); cat.setAlignment(Qt.AlignCenter|Qt.AlignBottom); cat.setFixedSize(68,64); cat_path=self.vocab_cat_path(word,state); pixmap=QPixmap(str(cat_path)) if cat_path else QPixmap()
        if not pixmap.isNull():cat.setPixmap(pixmap.scaled(62,58,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        cat.setToolTip({"forgot":"没关系，猫猫陪你再见一次","fuzzy":"已经有印象啦","remembered":"记住了，真棒"}.get(state.get("last_rating"),"先想一想，再翻面")); body.addWidget(cat,0,Qt.AlignBottom); v.addWidget(card)
        self.queue_vocab_autoplay(word); tip=QLabel("自动朗读  ·  空格 显示释义  ·  ← / → 切词  ·  R 重播  ·  1 忘了  2 模糊  3 记住了") ; tip.setAlignment(Qt.AlignCenter); tip.setStyleSheet("color:#94a3b8;font-size:9px;padding:3px"); v.addWidget(tip); self.box.addWidget(panel)
    def vocab_cat_path(self,word,state):
        paths=sorted((ASSETS_DIR/"vocab-cats").glob("*.png"))
        if not paths:return None
        offset={"forgot":0,"fuzzy":7,"remembered":15}.get(state.get("last_rating"),23); return paths[(int(word["id"][:8],16)+offset)%len(paths)]
    def select_vocabulary(self,lexicon_id):
        if not lexicon_id or lexicon_id==self.vocab_lexicon_id:return
        item=self.vocab_library.get(lexicon_id)
        if not item:return
        self.cancel_vocab_audio(True)
        self.vocab_lexicon_id=lexicon_id; self.vocab_store.select(lexicon_id); self.vocab_words=self.vocab_library.load(item["path"]); queue=self.vocab_store.due_words(self.vocab_words); self.vocab_current_id=queue[0]["id"] if queue else None; self.vocab_revealed=False; self.vocab_history=[]; self.vocab_retry_queue=[]; self.refresh(scan_windows=False)
    def toggle_vocab_random(self):self.vocab_random=not self.vocab_random; self.refresh(scan_windows=False)
    def reveal_vocab_word(self):
        if self.view_mode!="learn" or self.learning_mode!="vocabulary" or self.vocab_revealed:return
        self.vocab_revealed=True; self.refresh(scan_windows=False)
    def previous_vocab_word(self):
        if not self.vocab_history:return
        self.cancel_vocab_audio(True)
        self.vocab_current_id=self.vocab_history.pop(); self.vocab_revealed=True; self.refresh(scan_windows=False)
    def next_vocab_word(self):
        word=self.current_vocab_word()
        if not word:return
        queue=[item for item in self.vocab_store.due_words(self.vocab_words) if item["id"]!=word["id"]]
        if not queue:return
        self.cancel_vocab_audio(True)
        self.vocab_history.append(word["id"]); self.vocab_current_id=random.choice(queue[:min(100,len(queue))])["id"] if self.vocab_random else queue[0]["id"]; self.vocab_revealed=False; self.refresh(scan_windows=False)
    def rate_vocab_shortcut(self,rating):
        if self.view_mode=="learn" and self.learning_mode=="vocabulary" and self.vocab_revealed:self.rate_vocab_word(rating)
    def rate_vocab_word(self,rating):
        word=self.current_vocab_word()
        if not word:return
        self.cancel_vocab_audio(True)
        self.vocab_store.rate(word["id"],rating); self.vocab_history.append(word["id"])
        for item in self.vocab_retry_queue:item["wait"]-=1
        if rating=="forgot":self.vocab_retry_queue.append({"id":word["id"],"wait":3})
        ready=next((item for item in self.vocab_retry_queue if item["wait"]<=0 and item["id"]!=word["id"]),None)
        if ready:self.vocab_retry_queue.remove(ready); self.vocab_current_id=ready["id"]
        else:
            queue=[item for item in self.vocab_store.due_words(self.vocab_words) if item["id"]!=word["id"]]
            if queue:self.vocab_current_id=(random.choice(queue[:min(100,len(queue))])["id"] if self.vocab_random else queue[0]["id"])
        self.vocab_revealed=False; self.refresh(scan_windows=False)
    def toggle_vocab_favorite(self,word_id):self.vocab_store.toggle_favorite(word_id); self.refresh(scan_windows=False)
    def speak_current_vocab_word(self):
        word=self.current_vocab_word()
        if word:self.speak_vocab_word(word["word"])
    def cancel_vocab_audio(self,invalidate=False):
        if invalidate:self.vocab_audio_generation+=1
        if self.tts_cancel:self.tts_cancel.set()
    def queue_vocab_autoplay(self,word):
        if not word or word["id"]==self.vocab_last_spoken_id:return
        self.vocab_last_spoken_id=word["id"]; self.cancel_vocab_audio(True); generation=self.vocab_audio_generation; word_id=word["id"]; text=word["word"]
        QTimer.singleShot(140,lambda:self.autoplay_vocab_word(word_id,text,generation))
    def autoplay_vocab_word(self,word_id,text,generation):
        if generation!=self.vocab_audio_generation or self.view_mode!="learn" or self.learning_mode!="vocabulary" or self.vocab_current_id!=word_id:return
        self.start_vocab_audio(text)
    def start_vocab_audio(self,text):
        self.cancel_vocab_audio(); cancel=threading.Event(); self.tts_cancel=cancel; self.tts_future=self.tts_executor.submit(play_vocab_audio,text,cancel)
    def speak_vocab_word(self,text):
        self.vocab_audio_generation+=1; self.start_vocab_audio(text)
    def import_vocabulary(self):
        source,_=QFileDialog.getOpenFileName(self,"导入词库",str(Path.home()),"文本词库 (*.txt)")
        if not source:return
        try:lexicon_id=self.vocab_library.import_file(source)
        except Exception as exc:QMessageBox.warning(self,"导入失败",str(exc)); return
        self.vocab_lexicon_id=""; self.select_vocabulary(lexicon_id)
    def curriculum_panel(self,v,panel):
        self.curriculum_card_widget=None
        bundle=self.curriculum_library.get(self.curriculum_domain_id)
        if not bundle:
            empty=QLabel("还没有导入可用的系统学习路线"); empty.setAlignment(Qt.AlignCenter); empty.setStyleSheet("color:#64748b;background:white;padding:30px;border-radius:9px"); v.addWidget(empty); self.box.addWidget(panel); return
        path_name=self.curriculum_store.selected_path(bundle); path=self.curriculum_library.path(bundle,path_name); current_id=self.curriculum_store.current(bundle,path); concept=bundle["concept_by_id"].get(current_id)
        stats=self.curriculum_store.stats(bundle,path); approved=self.curriculum_store.approved(bundle); domain=bundle["domain"]

        controls=QFrame(); controls.setObjectName("curriculumControls"); controls.setStyleSheet("QFrame#curriculumControls{background:white;border:1px solid #e2e8f0;border-radius:9px}"); row=QHBoxLayout(controls); row.setContentsMargins(9,6,8,6); row.setSpacing(6)
        loaded={item["id"]:item for item in self.curriculum_library.domains()}
        for domain_id,label in (("vla","VLA"),("vln","VLN"),("wam","WAM")):
            route=QPushButton(label if domain_id in loaded else f"{label} · 待导入"); route.setEnabled(domain_id in loaded); active=domain_id==self.curriculum_domain_id; route.setStyleSheet("background:#4f46e5;color:white;border:0;font-weight:700" if active else "background:#f8fafc;color:#64748b;border:1px solid #e2e8f0"); route.clicked.connect(lambda _,value=domain_id:self.select_curriculum_domain(value)); row.addWidget(route)
        row.addStretch(); path_select=QComboBox()
        for key,label in PATH_LABELS.items():path_select.addItem(label,key)
        path_select.setCurrentIndex(max(0,path_select.findData(path_name))); path_select.currentIndexChanged.connect(lambda:self.select_curriculum_path(path_select.currentData())); row.addWidget(path_select)
        outline=QPushButton("查看完整框架"); outline.clicked.connect(lambda:self.open_curriculum_document("curriculum")); row.addWidget(outline); review=QPushButton("审查报告"); review.clicked.connect(lambda:self.open_curriculum_document("review")); row.addWidget(review); v.addWidget(controls)

        counts=bundle["validation"].get("counts",{}); approval=QFrame(); approval.setObjectName("approvalState"); approval.setStyleSheet(f"QFrame#approvalState{{background:{'#ecfdf5' if approved else '#fffbeb'};border:1px solid {'#a7f3d0' if approved else '#fde68a'};border-radius:8px}} QLabel{{background:transparent}}"); approval_row=QHBoxLayout(approval); approval_row.setContentsMargins(10,7,8,7); approval_text=QLabel(("✓ 已确认启用 · 进度仅保存在本机" if approved else f"结构校验已通过 · {counts.get('modules',0)} 个模块、{counts.get('concepts',0)} 个节点 · 框架仍待你人工确认")); approval_text.setStyleSheet(f"color:{'#047857' if approved else '#92400e'};font-size:10px;font-weight:700"); approval_row.addWidget(approval_text,1)
        if not approved:
            confirm=QPushButton("确认启用 v1"); confirm.setStyleSheet("background:#d97706;color:white;border:0;font-weight:700"); confirm.clicked.connect(self.approve_curriculum); approval_row.addWidget(confirm)
        v.addWidget(approval)

        progress_box=QFrame(); progress_box.setObjectName("curriculumProgress"); progress_box.setStyleSheet("QFrame#curriculumProgress{background:#eef2ff;border:1px solid #dbeafe;border-radius:9px} QLabel{background:transparent}"); progress_layout=QVBoxLayout(progress_box); progress_layout.setContentsMargins(11,8,11,9); progress_layout.setSpacing(5); progress_top=QHBoxLayout(); route_title=QLabel(f"{domain.get('name_zh','VLA')} · {PATH_LABELS.get(path_name,path_name)}"); route_title.setStyleSheet("color:#312e81;font-weight:700"); progress_top.addWidget(route_title); progress_top.addStretch(); progress_number=QLabel(f"已理解 {stats['mastered']}/{stats['total']} · {stats['percent']}%"); progress_number.setStyleSheet("color:#4338ca;font-size:10px;font-weight:700"); progress_top.addWidget(progress_number); progress_layout.addLayout(progress_top); progress_bar=QProgressBar(); progress_bar.setTextVisible(False); progress_bar.setRange(0,100); progress_bar.setValue(stats["percent"]); progress_bar.setStyleSheet("QProgressBar{height:7px;border:0;border-radius:3px;background:#dbeafe} QProgressBar::chunk{background:#6366f1;border-radius:3px}"); progress_layout.addWidget(progress_bar); v.addWidget(progress_box)

        if concept:
            modules={item["id"]:item for item in bundle["modules"]}; module=modules.get(concept.get("module_id"),{}); position=path.index(current_id)+1 if current_id in path else 1; state=self.curriculum_store.state(bundle,current_id); lesson=self.lesson_store.get(bundle,current_id)
            card=QFrame(); self.curriculum_card_widget=card; card.setObjectName("conceptCard"); card.setStyleSheet("QFrame#conceptCard{background:white;border:1px solid #dbe3ed;border-left:4px solid #6366f1;border-radius:10px} QLabel{background:transparent;border:0}"); card_layout=QVBoxLayout(card); card_layout.setContentsMargins(14,11,14,12); card_layout.setSpacing(9)
            badges=QHBoxLayout(); module_badge=QLabel(module.get("title_zh","VLA")); module_badge.setStyleSheet("color:#4338ca;background:#eef2ff;padding:3px 7px;border-radius:5px;font-size:9px;font-weight:700"); badges.addWidget(module_badge); priority=QLabel(concept.get("priority","P1")); priority.setStyleSheet("color:#b45309;background:#fef3c7;padding:3px 7px;border-radius:5px;font-size:9px;font-weight:700"); badges.addWidget(priority); stability_labels={"foundation":"稳定基础","evolving":"持续演进","frontier":"前沿扩展"}; stability=QLabel(stability_labels.get(concept.get("stability"),concept.get("stability",""))); stability.setStyleSheet("color:#0369a1;background:#e0f2fe;padding:3px 7px;border-radius:5px;font-size:9px;font-weight:700"); badges.addWidget(stability); state_badge=QLabel(STATE_LABELS.get(state,"未学习")); state_badge.setStyleSheet("color:#047857;background:#ecfdf5;padding:3px 7px;border-radius:5px;font-size:9px;font-weight:700"); badges.addWidget(state_badge); badges.addStretch(); number=QLabel(f"第 {position}/{len(path)} 项 · {concept.get('estimated_card_minutes',4)} 分钟"); number.setStyleSheet("color:#64748b;font-size:9px"); badges.addWidget(number); card_layout.addLayout(badges)
            concept_title=QLabel(concept.get("title_zh","未命名知识点")); concept_title.setFont(QFont("Noto Sans CJK SC",17,QFont.Bold)); concept_title.setStyleSheet("color:#0f172a"); card_layout.addWidget(concept_title); english=QLabel(concept.get("title_en","")); english.setStyleSheet("color:#64748b;font-size:10px"); card_layout.addWidget(english)
            if lesson:
                self.floating_tutor_available=bool(approved)
                self.render_curriculum_lesson(card_layout,lesson)
                if approved and not self.lesson_future:QTimer.singleShot(700,lambda b=bundle,p=list(path),c=current_id:self.prefetch_next_lesson(b,p,c))
            elif approved:
                loading=QFrame(); loading.setObjectName("lessonLoading"); loading.setStyleSheet("QFrame#lessonLoading{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px} QLabel{background:transparent}"); loading_layout=QVBoxLayout(loading); loading_layout.setContentsMargins(14,18,14,18); loading_layout.setSpacing(7)
                is_loading=bool(self.lesson_future and self.lesson_job and self.lesson_job.get("concept_id")==current_id); error=self.lesson_errors.get(current_id,"")
                loading_title=QLabel("正在准备 3～5 分钟讲解…" if is_loading else ("这节讲解生成失败" if error else "这节还没有教学正文")); loading_title.setAlignment(Qt.AlignCenter); loading_title.setStyleSheet("color:#3730a3;font-weight:700"); loading_layout.addWidget(loading_title)
                loading_note=QLabel((error[:160] if error else "会按“直觉 → 机制 → VLA 例子 → 方法辨析”生成，并保存在本机；切换页面不会阻塞窗口扫描。")); loading_note.setWordWrap(True); loading_note.setAlignment(Qt.AlignCenter); loading_note.setStyleSheet("color:#64748b;font-size:10px"); loading_layout.addWidget(loading_note)
                if error and not is_loading:
                    retry=QPushButton("重新生成讲解"); retry.setStyleSheet("background:#4f46e5;color:white;border:0;font-weight:700"); retry.clicked.connect(lambda _,cid=current_id:self.ensure_curriculum_lesson(cid,False,True)); loading_layout.addWidget(retry,0,Qt.AlignCenter)
                card_layout.addWidget(loading)
                if not is_loading and not error:QTimer.singleShot(0,lambda cid=current_id:self.ensure_curriculum_lesson(cid))
            else:
                preview=QLabel("这里目前只展示课程框架。确认启用后，系统会提供真正的 3～5 分钟教学正文，而不是让你直接对着提纲打卡。\n\n本节范围："+concept.get("scope","")); preview.setWordWrap(True); preview.setStyleSheet("color:#475569;background:#f8fafc;padding:11px;border-radius:7px;font-size:10px"); card_layout.addWidget(preview)
            bottom=QHBoxLayout(); previous=QPushButton("← 上一个"); previous.setEnabled(position>1); previous.clicked.connect(lambda:self.navigate_curriculum(-1)); bottom.addWidget(previous); sources=QToolButton(); source_ids=concept.get("source_ids",[]); sources.setText(f"学习来源 {len(source_ids)}  ▾"); sources.setPopupMode(QToolButton.InstantPopup); sources.setStyleSheet("QToolButton{padding:7px 10px;background:white;color:#475569;border:1px solid #dbe3ed;border-radius:7px} QToolButton::menu-indicator{image:none}"); source_menu=QMenu(sources)
            for source_id in source_ids:
                source=bundle["source_by_id"].get(source_id,{}); action=source_menu.addAction(f"{source.get('type','资料')} · {source.get('title',source_id)[:64]}"); action.triggered.connect(lambda _,url=source.get("url",""):self.open_external_url(url))
            sources.setMenu(source_menu); bottom.addWidget(sources); bottom.addStretch(); deep=QPushButton("基础懂了，待深入"); deep.setEnabled(approved and bool(lesson)); deep.setToolTip("基础内容已理解，同时加入深入队列" if lesson else "需要先生成教学正文"); deep.setStyleSheet("background:#eef2ff;color:#4338ca;border:0"); deep.clicked.connect(lambda:self.mark_curriculum_state("deep",True)); bottom.addWidget(deep); understood=QPushButton("学会了，下一课"); understood.setEnabled(approved and bool(lesson)); understood.setToolTip("记录进度并继续" if lesson else "需要先生成教学正文"); understood.setStyleSheet("background:#4f46e5;color:white;border:0;font-weight:700"); understood.clicked.connect(lambda:self.mark_curriculum_state("understood",True)); bottom.addWidget(understood); card_layout.addLayout(bottom); v.addWidget(card)

        map_box=QFrame(); map_box.setObjectName("curriculumMap"); map_box.setStyleSheet("QFrame#curriculumMap{background:white;border:1px solid #e2e8f0;border-radius:9px} QLabel{background:transparent}"); map_layout=QVBoxLayout(map_box); map_layout.setContentsMargins(11,9,11,10); map_title=QLabel("路线概览"); map_title.setStyleSheet("color:#0f172a;font-weight:700"); map_layout.addWidget(map_title)
        for module in sorted(bundle["modules"],key=lambda item:item.get("order",0)):
            module_path=[item for item in path if item in module.get("concept_ids",[])]; mastered=sum(self.curriculum_store.state(bundle,item) in {"understood","deep"} for item in module_path); module_row=QHBoxLayout(); module_name=QLabel(module.get("title_zh",module.get("id",""))); module_name.setMinimumWidth(180); module_name.setStyleSheet("color:#334155;font-size:10px"); module_row.addWidget(module_name); module_progress=QProgressBar(); module_progress.setTextVisible(False); module_progress.setRange(0,100); module_progress.setValue(round(mastered/len(module_path)*100) if module_path else 0); module_progress.setFixedHeight(5); module_row.addWidget(module_progress,1); module_count=QLabel(f"{mastered}/{len(module_path)}"); module_count.setMinimumWidth(36); module_count.setAlignment(Qt.AlignRight|Qt.AlignVCenter); module_count.setStyleSheet("color:#64748b;font-size:9px"); module_row.addWidget(module_count); jump=QPushButton("继续"); jump.setEnabled(bool(module_path)); jump.setStyleSheet("padding:4px 9px;font-size:9px"); target=next((item for item in module_path if self.curriculum_store.state(bundle,item) not in {"understood","deep"}),module_path[0] if module_path else ""); jump.clicked.connect(lambda _,concept_id=target:self.select_curriculum_concept(concept_id)); module_row.addWidget(jump); map_layout.addLayout(module_row)
        v.addWidget(map_box); self.box.addWidget(panel)
    def render_curriculum_lesson(self,layout,lesson):
        lead=QFrame(); lead.setObjectName("lessonLead"); lead.setStyleSheet("QFrame#lessonLead{background:#eef2ff;border:1px solid #c7d2fe;border-radius:8px} QLabel{background:transparent}"); lead_layout=QVBoxLayout(lead); lead_layout.setContentsMargins(11,8,11,9); lead_layout.setSpacing(3); lead_title=QLabel("先记住这一句"); lead_title.setStyleSheet("color:#4338ca;font-size:9px;font-weight:700"); lead_layout.addWidget(lead_title); lead_text=QLabel(lesson.get("one_liner","")); lead_text.setWordWrap(True); lead_text.setStyleSheet("color:#1e1b4b;font-size:12px;font-weight:650"); lead_layout.addWidget(lead_text); layout.addWidget(lead)

        def section(title,text,color="#334155",background="transparent"):
            heading=QLabel(title); heading.setStyleSheet("color:#0f172a;font-size:11px;font-weight:700;padding-top:3px"); layout.addWidget(heading)
            body=QLabel(text); body.setWordWrap(True); body.setTextInteractionFlags(Qt.TextSelectableByMouse); body.setStyleSheet(f"color:{color};background:{background};padding:{'9px' if background!='transparent' else '0'};border-radius:7px;font-size:11px;line-height:1.35"); layout.addWidget(body)

        section("直觉理解",lesson.get("intuition",""))
        mechanism=lesson.get("mechanism",[]); section("它是怎么工作的","\n\n".join(f"{index}. {text}" for index,text in enumerate(mechanism,1)))
        section("放进 VLA 里看",lesson.get("vla_example",""),"#164e63","#ecfeff")

        comparisons=lesson.get("comparisons",[])
        if comparisons:
            section("和相邻方法的区别","\n".join(f"• {row.get('name','相邻方法')}：{row.get('difference','')}" for row in comparisons),"#4338ca","#f5f3ff")
        pitfalls=lesson.get("pitfalls",[])
        if pitfalls:section("容易混淆的地方","\n".join(f"• {text}" for text in pitfalls),"#92400e","#fffbeb")
        terms=lesson.get("terms",[])
        if terms:section("读论文时会遇到","\n".join(f"• {row.get('term','术语')}：{row.get('meaning','')}" for row in terms),"#334155","#f8fafc")
        takeaways=lesson.get("takeaways",[])
        if takeaways:section("学完带走这三点","\n".join(f"✓ {text}" for text in takeaways),"#047857","#ecfdf5")

        check=lesson.get("check",{})
        if check.get("question"):
            check_box=QFrame(); check_box.setObjectName("lessonCheck"); check_box.setStyleSheet("QFrame#lessonCheck{background:white;border:1px dashed #a5b4fc;border-radius:8px} QLabel{background:transparent}"); check_layout=QVBoxLayout(check_box); check_layout.setContentsMargins(10,8,10,8); check_layout.setSpacing(5); check_title=QLabel("最后用 20 秒检验理解"); check_title.setStyleSheet("color:#4338ca;font-size:10px;font-weight:700"); check_layout.addWidget(check_title); question=QLabel(check.get("question","")); question.setWordWrap(True); question.setStyleSheet("color:#334155;font-size:10px"); check_layout.addWidget(question); reveal=QPushButton("查看参考答案"); reveal.setStyleSheet("background:#eef2ff;color:#4338ca;border:0"); check_layout.addWidget(reveal,0,Qt.AlignLeft); answer=QLabel(check.get("answer","")); answer.setWordWrap(True); answer.setStyleSheet("color:#475569;background:#f8fafc;padding:8px;border-radius:6px;font-size:10px"); answer.hide(); check_layout.addWidget(answer); reveal.clicked.connect(lambda _,label=answer,button=reveal:self.toggle_lesson_answer(label,button)); layout.addWidget(check_box)
    def toggle_lesson_answer(self,label,button):
        visible=not label.isVisible(); label.setVisible(visible); button.setText("收起参考答案" if visible else "查看参考答案")
    def ensure_curriculum_lesson(self,concept_id,prefetch=False,force=False):
        bundle=self.curriculum_library.get(self.curriculum_domain_id)
        if not bundle or concept_id not in bundle["concept_by_id"]:return
        if not force and self.lesson_store.get(bundle,concept_id):return
        if self.lesson_future and not self.lesson_future.done():return
        self.lesson_errors.pop(concept_id,None); self.lesson_job={"bundle":bundle,"concept_id":concept_id,"prefetch":prefetch}; self.lesson_future=self.lesson_executor.submit(generate_lesson,bundle,bundle["concept_by_id"][concept_id])
        if not prefetch:self.refresh(scan_windows=False)
        QTimer.singleShot(120,self.poll_curriculum_lesson)
    def poll_curriculum_lesson(self):
        if not self.lesson_future:return
        if not self.lesson_future.done():QTimer.singleShot(120,self.poll_curriculum_lesson); return
        job=self.lesson_job; success=False
        try:self.lesson_store.put(job["bundle"],job["concept_id"],self.lesson_future.result()); success=True
        except Exception as exc:self.lesson_errors[job["concept_id"]]=str(exc)
        self.lesson_future=None; self.lesson_job=None
        bundle,path,current=self.current_curriculum()
        visible=bool(bundle and self.view_mode=="learn" and self.learning_mode=="curriculum")
        if visible:
            self.refresh_curriculum(current==job["concept_id"])
            if current and not self.lesson_store.get(bundle,current):
                QTimer.singleShot(0,lambda cid=current:self.ensure_curriculum_lesson(cid))
            elif success and current==job["concept_id"]:
                self.prefetch_next_lesson(bundle,path,current)
    def prefetch_next_lesson(self,bundle,path,current):
        if self.lesson_future or current not in path:return
        index=path.index(current)+1
        if index<len(path):
            next_id=path[index]
            if not self.lesson_store.get(bundle,next_id):self.ensure_curriculum_lesson(next_id,True)
    def open_curriculum_tutor(self):
        bundle,path,current=self.current_curriculum()
        if not bundle or not current:return
        lesson=self.lesson_store.get(bundle,current)
        if not lesson:return
        dialog=LessonChatDialog(self,bundle,bundle["concept_by_id"][current],lesson,self.lesson_chat_store,self.tutor_executor); self.tutor_dialogs.append(dialog); dialog.finished.connect(lambda _,item=dialog:self.release_tutor_dialog(item)); dialog.show(); self.place_tutor_dialog(dialog); dialog.raise_(); dialog.activateWindow()
    def place_tutor_dialog(self,dialog):
        if self.isMaximized():self.showNormal(); self.resize(840,min(900,max(540,QApplication.primaryScreen().availableGeometry().height()-40))); QApplication.processEvents()
        screens=QApplication.screens(); main_rect=self.frameGeometry(); current=QApplication.screenAt(main_rect.center()) or QApplication.primaryScreen(); available=current.availableGeometry(); gap=12
        dialog_width=min(540,max(440,available.width()-main_rect.width()-gap-28)); dialog_height=min(680,available.height()-28); dialog.resize(dialog_width,dialog_height)
        right_space=available.right()-main_rect.right(); left_space=main_rect.left()-available.left()
        top=max(available.top()+10,min(main_rect.top(),available.bottom()-dialog.height()-10))
        if right_space>=dialog.width()+gap:dialog.move(main_rect.right()+gap,top); return
        if left_space>=dialog.width()+gap:dialog.move(main_rect.left()-dialog.width()-gap,top); return
        for screen in screens:
            if screen is current:continue
            target=screen.availableGeometry()
            if target.width()>=dialog.width()+20 and target.height()>=dialog.height()+20:dialog.move(target.left()+10,target.top()+10); return
        total=main_rect.width()+gap+dialog.width()
        if total>available.width()-20:
            target_main=max(self.minimumWidth(),available.width()-540-gap-20)
            if target_main<main_rect.width():self.resize(target_main,min(self.height(),available.height()-20)); QApplication.processEvents(); main_rect=self.frameGeometry()
            dialog.resize(max(400,available.width()-main_rect.width()-gap-20),dialog.height()); total=main_rect.width()+gap+dialog.width()
        if total<=available.width()-20:
            pair_left=available.left()+max(10,(available.width()-total)//2); main_top=max(available.top()+10,min(main_rect.top(),available.bottom()-main_rect.height()-10)); self.move(pair_left,main_top); dialog.move(pair_left+main_rect.width()+gap,top); return
        dialog.move(available.right()-dialog.width()-10,top)
    def release_tutor_dialog(self,dialog):
        if dialog in self.tutor_dialogs:self.tutor_dialogs.remove(dialog)
        dialog.deleteLater()
    def refresh_curriculum(self,scroll=False):
        self.refresh(scan_windows=False)
        if scroll:QTimer.singleShot(0,self.scroll_to_curriculum_card)
    def scroll_to_curriculum_card(self):
        card=self.curriculum_card_widget
        if not card:return
        try:
            y=card.mapTo(self.content,QPoint(0,0)).y(); self.area.verticalScrollBar().setValue(max(0,y-8))
        except RuntimeError:pass
    def current_curriculum(self):
        bundle=self.curriculum_library.get(self.curriculum_domain_id)
        if not bundle:return None,[],None
        path=self.curriculum_library.path(bundle,self.curriculum_store.selected_path(bundle)); return bundle,path,self.curriculum_store.current(bundle,path)
    def select_curriculum_domain(self,domain_id):
        if not self.curriculum_library.get(domain_id):return
        self.curriculum_domain_id=domain_id; self.curriculum_store.select_domain(domain_id); self.refresh_curriculum()
    def select_curriculum_path(self,path_name):
        bundle=self.curriculum_library.get(self.curriculum_domain_id)
        if bundle and path_name in PATH_LABELS:self.curriculum_store.select_path(bundle,path_name); self.refresh_curriculum(True)
    def select_curriculum_concept(self,concept_id):
        bundle,path,_=self.current_curriculum()
        if bundle and concept_id in path:self.curriculum_store.set_current(bundle,concept_id); self.refresh_curriculum(True)
    def navigate_curriculum(self,step):
        bundle,path,current=self.current_curriculum()
        if not bundle or current not in path:return
        index=max(0,min(len(path)-1,path.index(current)+step)); self.curriculum_store.set_current(bundle,path[index]); self.refresh_curriculum(True)
    def mark_curriculum_state(self,state,advance):
        bundle,path,current=self.current_curriculum()
        if not bundle or not current:return
        self.curriculum_store.set_state(bundle,current,state)
        if advance:self.curriculum_store.advance(bundle,path,current)
        self.refresh_curriculum(True)
    def approve_curriculum(self):
        bundle=self.curriculum_library.get(self.curriculum_domain_id)
        if not bundle:return
        result=QMessageBox.question(self,"确认启用课程",f"确认你已经检查过 {bundle['domain'].get('name_zh','当前')} {bundle['domain'].get('version','v1')} 的框架，并将它作为系统学习路线吗？\n\n这只记录本机确认状态，不会自动修改课程内容。",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if result==QMessageBox.Yes:self.curriculum_store.approve(bundle); self.refresh_curriculum()
    def open_curriculum_document(self,kind):
        bundle=self.curriculum_library.get(self.curriculum_domain_id)
        if not bundle:return
        path=bundle.get("review_path" if kind=="review" else "readable_path")
        if path and Path(path).exists():subprocess.Popen(["xdg-open",str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def open_external_url(self,url):
        if url:subprocess.Popen(["xdg-open",url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def set_learning_minutes(self,value):self.learning_minutes=int(value or 5)
    def start_learning_feed(self):
        if self.feed_future and not self.feed_future.done():return
        context_parts=[]
        for window in self.windows:
            context_parts.append(window.get("folder","")+" "+window.get("path",""))
            if window.get("status")=="正在运行":
                conversations,_=project_conversations(window.get("path",""),2); context_parts.extend(x.get("title","") for x in conversations)
        self.learning_context=context_profile(" ".join(context_parts)); count={3:4,5:6,10:9,20:12}.get(getattr(self,"learning_minutes",5),6); self.feed_error=""; self.feed_future=self.feed_executor.submit(build_learning_feed_v2,count,self.learning_context); self.refresh(); QTimer.singleShot(250,self.poll_learning_feed)
    def poll_learning_feed(self):
        if not self.feed_future:return
        if not self.feed_future.done():QTimer.singleShot(250,self.poll_learning_feed); return
        try:
            self.feed_items,self.feed_error,self.feed_stats=self.feed_future.result()
            self.feed_display_limit=max(1,len(self.feed_items))
        except Exception as exc:self.feed_error=str(exc)
        self.feed_future=None
        if self.view_mode=="learn":self.refresh()
    def open_learning_preferences(self):
        subprocess.Popen(["xdg-open",str(PREFERENCES_PATH)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def open_learning_url(self,url,mark_url=None):
        if url:
            event_url=mark_url or url; self.feed_store.mark_read(event_url)
            for item in self.feed_items:
                if item.get("url")==event_url:item["read"]=True
            subprocess.Popen(["xdg-open",url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); self.refresh()
    def toggle_learning_saved(self,url):
        if url:self.feed_store.toggle_saved(url)
        self.feed_items=self.feed_store.recent(self.feed_display_limit); self.feed_stats=self.feed_store.stats(); self.refresh()
    def feedback_learning(self,url,action):
        if not url:return
        self.feed_store.feedback(url,action); self.feed_items=self.feed_store.recent(self.feed_display_limit); self.feed_stats=self.feed_store.stats(); self.refresh()
    def todo_panel(self):
        today=datetime.now().strftime("%Y-%m-%d"); visible=[t for t in self.todos if not t.get("done") or t.get("done_date")==today]
        priority_order={"高":0,"中":1,"低":2}; visible.sort(key=lambda t:(not bool(t.get("active") and not t.get("done")),bool(t.get("done")),priority_order.get(t.get("priority","中"),1),t.get("created_at","")))
        panel=QFrame(); panel.setObjectName("todoPanel"); panel.setStyleSheet("QFrame#todoPanel{background:#f5f3ff;border:1px solid #ddd6fe;border-radius:11px} QLabel{background:transparent}"); layout=QVBoxLayout(panel); layout.setContentsMargins(14,13,14,14); layout.setSpacing(9)
        head=QHBoxLayout(); title=QLabel("今日待办"); title.setFont(QFont("Noto Sans CJK SC",16,QFont.Bold)); title.setStyleSheet("color:#312e81"); head.addWidget(title); head.addStretch(); completed=sum(t.get("done") for t in visible); progress=QLabel(f"已完成 {completed}/{len(visible)}"); progress.setStyleSheet("color:#6d28d9;background:#ede9fe;padding:4px 9px;border-radius:6px;font-weight:700"); head.addWidget(progress); layout.addLayout(head)
        active_count=sum(bool(todo.get("active") and not todo.get("done")) for todo in visible); hint=QLabel(f"当前并行推进 {active_count} 项 · 激活项统一置顶" if active_count else "可以同时激活多个正在推进的事项 · 未完成事项会自动保留到第二天"); hint.setStyleSheet("color:#7c3aed;font-size:11px"); layout.addWidget(hint)
        entry=QFrame(); entry.setStyleSheet("background:white;border:1px solid #ddd6fe;border-radius:9px"); row=QHBoxLayout(entry); row.setContentsMargins(9,8,9,8)
        self.todo_input=QLineEdit(); self.todo_input.setPlaceholderText("输入今天要做的事，按回车添加……"); self.todo_input.returnPressed.connect(self.add_todo); row.addWidget(self.todo_input,1)
        self.todo_priority=QComboBox(); self.todo_priority.addItems(["中","高","低"]); self.todo_priority.setToolTip("优先级"); row.addWidget(self.todo_priority)
        self.todo_project=QComboBox(); self.todo_project.addItem("不绑定项目","")
        for w in self.windows:self.todo_project.addItem(w["folder"],w["path"])
        row.addWidget(self.todo_project); add=QPushButton("添加"); add.setStyleSheet("background:#4f46e5;color:white;border:0;font-weight:700"); add.clicked.connect(self.add_todo); row.addWidget(add); layout.addWidget(entry)
        if not visible:
            empty=QLabel("今天还没有待办，先记下最重要的一件事吧"); empty.setAlignment(Qt.AlignCenter); empty.setStyleSheet("color:#94a3b8;background:white;padding:28px;border-radius:9px"); layout.addWidget(empty)
        colors={"高":("#dc2626","#fee2e2"),"中":("#d97706","#fef3c7"),"低":("#059669","#d1fae5")}
        for todo in visible:
            active=bool(todo.get("active") and not todo.get("done")); card=QFrame(); card.setObjectName("todoCard"); card.setStyleSheet("QFrame#todoCard{background:#f0f9ff;border:1px solid #bae6fd;border-left:4px solid #38bdf8;border-radius:9px}" if active else "QFrame#todoCard{background:white;border:1px solid #e9d5ff;border-radius:8px}"); line=QHBoxLayout(card); line.setContentsMargins(9 if active else 11,8,8,8)
            check=QCheckBox(); check.setChecked(bool(todo.get("done"))); check.setCursor(Qt.PointingHandCursor); check.stateChanged.connect(lambda state,t=todo:self.toggle_todo(t,state)); line.addWidget(check)
            if active:
                active_badge=QLabel("● 正在做"); active_badge.setStyleSheet("color:#0369a1;background:#e0f2fe;padding:3px 7px;border-radius:5px;font-size:10px;font-weight:700"); line.addWidget(active_badge)
            text=QLabel(todo.get("text","")); text.setWordWrap(True); text.setStyleSheet("color:#94a3b8;text-decoration:line-through" if todo.get("done") else "color:#1e293b;font-size:13px;font-weight:600"); line.addWidget(text,1)
            if todo.get("project"):
                project=QLabel(todo["project"]); project.setStyleSheet("color:#4338ca;background:#eef2ff;padding:3px 7px;border-radius:5px;font-size:10px"); line.addWidget(project)
            priority=todo.get("priority","中"); fg,bg=colors.get(priority,colors["中"]); badge=QLabel(priority); badge.setStyleSheet(f"color:{fg};background:{bg};padding:3px 7px;border-radius:5px;font-size:10px;font-weight:700"); line.addWidget(badge)
            if not todo.get("done"):
                activate=QPushButton("暂停" if active else "开始"); activate.setToolTip("取消这项的正在做状态" if active else "加入正在并行推进的事项并置顶"); activate.setStyleSheet("background:white;color:#0369a1;border:1px solid #bae6fd;font-weight:700" if active else "background:#f8fafc;color:#475569;border:1px solid #dbe3ed"); activate.clicked.connect(lambda _,t=todo:self.toggle_todo_active(t)); line.addWidget(activate)
            edit=QPushButton("编辑"); edit.setToolTip("修改内容、优先级和绑定项目"); edit.clicked.connect(lambda _,t=todo:self.edit_todo(t)); line.addWidget(edit)
            remove=QPushButton("×"); remove.setFixedSize(28,28); remove.setToolTip("删除待办"); remove.setStyleSheet("QPushButton{padding:0;border:0;background:transparent;color:#94a3b8;font-size:17px} QPushButton:hover{background:#fee2e2;color:#dc2626}"); remove.clicked.connect(lambda _,t=todo:self.delete_todo(t)); line.addWidget(remove); layout.addWidget(card)
        self.box.addWidget(panel)
    def add_todo(self):
        text=self.todo_input.text().strip()
        if not text:return
        project_path=self.todo_project.currentData() or ""; project=self.todo_project.currentText() if project_path else ""
        self.todos.append({"id":uuid.uuid4().hex,"text":text,"priority":self.todo_priority.currentText(),"project":project,"project_path":project_path,"done":False,"created_at":datetime.now().isoformat(timespec="seconds")}); self.save_todos(); self.refresh()
    def toggle_todo(self,todo,state):
        todo["done"]=bool(state); todo["done_date"]=datetime.now().strftime("%Y-%m-%d") if state else ""; todo["active"]=False if state else bool(todo.get("active")); self.save_todos(); self.refresh()
    def toggle_todo_active(self,todo):
        if not todo.get("done"):todo["active"]=not bool(todo.get("active"))
        self.save_todos(); self.refresh()
    def edit_todo(self,todo):
        dialog=QDialog(self); dialog.setWindowTitle("编辑待办"); dialog.setWindowFlag(Qt.WindowStaysOnTopHint,True); dialog.setMinimumWidth(440); dialog.setStyleSheet("QDialog{background:#f8fafc} QLabel{font-family:'Noto Sans CJK SC';color:#475569} QLineEdit,QComboBox{font-family:'Noto Sans CJK SC';padding:8px;background:white;border:1px solid #cbd5e1;border-radius:7px} QPushButton{font-family:'Noto Sans CJK SC';padding:8px 14px;background:white;border:1px solid #dbe3ed;border-radius:7px}")
        form=QVBoxLayout(dialog); form.setContentsMargins(16,14,16,16); form.setSpacing(8); heading=QLabel("修改待办"); heading.setStyleSheet("color:#312e81;font-size:17px;font-weight:700"); form.addWidget(heading); form.addWidget(QLabel("内容")); content=QLineEdit(todo.get("text","")); content.selectAll(); form.addWidget(content); options=QHBoxLayout(); priority_box=QComboBox(); priority_box.addItems(["高","中","低"]); priority_box.setCurrentText(todo.get("priority","中")); options.addWidget(priority_box); project_box=QComboBox(); project_box.addItem("不绑定项目",""); known_paths=set()
        if todo.get("project_path"):project_box.addItem(todo.get("project") or Path(todo["project_path"]).name,todo["project_path"]); known_paths.add(todo["project_path"])
        for window in self.windows:
            if window["path"] not in known_paths:project_box.addItem(window["folder"],window["path"]); known_paths.add(window["path"])
        project_box.setCurrentIndex(max(0,project_box.findData(todo.get("project_path","") or ""))); options.addWidget(project_box,1); form.addLayout(options); actions=QHBoxLayout(); actions.addStretch(); cancel=QPushButton("取消"); cancel.clicked.connect(dialog.reject); actions.addWidget(cancel); save=QPushButton("保存修改"); save.setStyleSheet("background:#4f46e5;color:white;border:0;font-weight:700"); save.clicked.connect(dialog.accept); actions.addWidget(save); form.addLayout(actions); content.returnPressed.connect(dialog.accept); content.setFocus()
        result=dialog.exec() if hasattr(dialog,"exec") else dialog.exec_()
        if result and content.text().strip():
            todo["text"]=content.text().strip(); todo["priority"]=priority_box.currentText(); todo["project_path"]=project_box.currentData() or ""; todo["project"]=project_box.currentText() if todo["project_path"] else ""; todo["updated_at"]=datetime.now().isoformat(timespec="seconds"); self.save_todos(); self.refresh()
    def delete_todo(self,todo):
        if todo in self.todos:self.todos.remove(todo); self.save_todos(); self.refresh()
    def prefill_todo(self,w):
        self.view_mode="todo"; self.refresh(); self.todo_input.setText(f"查看 {w['folder']} 的进展"); index=self.todo_project.findData(w["path"]); self.todo_project.setCurrentIndex(max(0,index)); self.todo_input.setFocus(); self.todo_input.selectAll()
    def task_card(self,t):
        p=QFrame(); p.setStyleSheet("QFrame{background:white;border:1px solid #dbe3ed;border-radius:8px} QLabel{border:0;background:transparent}"); v=QVBoxLayout(p); h=QHBoxLayout(); q=QLabel(t.get("title","未命名任务")); q.setFont(QFont("Noto Sans CJK SC",14,QFont.Bold)); h.addWidget(q,1); s=t.get("status","Running"); badge=QLabel(LABELS.get(s,s)); badge.setStyleSheet(f"color:white;background:{COLORS.get(s,'#64748b')};padding:4px 9px;border-radius:5px"); h.addWidget(badge); v.addLayout(h); meta=QLabel(f"{t.get('project','')} · {t.get('account','Plus-1')} · {t.get('updated_at','')}"); meta.setStyleSheet("color:#64748b;font-size:11px"); v.addWidget(meta); a=QHBoxLayout()
        for text,fn in (("跳转 VS Code",lambda _,x=t:self.jump(x)),("切换状态",lambda _,x=t:self.cycle(x)),("删除",lambda _,x=t:self.delete(x))):b=QPushButton(text); b.clicked.connect(fn); a.addWidget(b)
        a.addStretch(); v.addLayout(a); self.box.addWidget(p)
    def cycle(self,t):s=t.get("status","Running"); t["status"]=STATES[(STATES.index(s)+1)%len(STATES)]; self.save(); self.refresh()
    def delete(self,t):
        if QMessageBox.question(self,"删除任务",f"确定删除“{t.get('title','')}”吗？")==QMessageBox.Yes:self.tasks.remove(t); self.save(); self.refresh()
    def jump(self,t):
        if t.get("window_id") and subprocess.run(["wmctrl","-i","-a",t["window_id"]]).returncode==0:self.collapse(); return
        if t.get("path"):subprocess.Popen(["code","--reuse-window",t["path"]])
    def select_account(self,w,profile):
        if not profile:return
        if profile.get("name")==w.get("account"):self.pending_accounts.pop(w["path"],None)
        else:self.pending_accounts[w["path"]]=profile
        self.refresh()
    def bridge_ready(self,w,provider_switch=False):
        now=time.time(); candidates=[BRIDGE_DIR/f"ready-{w['path'].encode('utf-8').hex()}.json",BRIDGE_DIR/f"ready-name-{w['folder'].encode('utf-8').hex()}.json"]
        candidates.extend(BRIDGE_DIR.glob("ready-active-*.json"))
        for ready in candidates:
            try:
                info=json.loads(ready.read_text(encoding="utf-8"))
                if now-info.get("at",0)/1000>=8:continue
                if ready.name.startswith("ready-active-"):
                    active=info.get("activeFile","")
                    if not active or not (active==w["path"] or active.startswith(w["path"].rstrip("/")+"/")):continue
                if provider_switch and info.get("bridgeVersion")!="0.1.4":continue
                return True
            except Exception:pass
        return False
    def switch_account(self,w,profile,focus_after=False):
        if not profile:return
        provider_switch=profile.get("kind")=="api" or w.get("provider","subscription")!="subscription"
        if not self.bridge_ready(w,provider_switch):
            self.recover_bridge_then_switch(w,profile,focus_after,provider_switch)
            return
        request_id=str(uuid.uuid4()); requests=BRIDGE_DIR/"requests"; requests.mkdir(parents=True,exist_ok=True)
        if profile.get("kind")=="api":payload={"id":request_id,"action":"switchProvider","provider":profile.get("provider","hejuapi"),"codexHome":profile.get("codexHome",str(API_CODEX_HOME)),"targetPath":w["path"],"profileName":profile.get("name","备用 API")}
        else:payload={"id":request_id,"action":"switchAccount","provider":"subscription","targetPath":w["path"],"profileId":profile["id"],"profileName":profile.get("name","未命名")}
        (requests/f"{request_id}.json").write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
        self.pending_focus[request_id]=(w["id"],w["path"],profile.get("name","未命名"),0)
        self.pending_accounts.pop(w["path"],None); self.collapse(); subprocess.run(["wmctrl","-i","-a",w["id"]]); QTimer.singleShot(500,lambda rid=request_id:self.wait_switch_result(rid))
    def recover_bridge_then_switch(self,w,profile,focus_after=False,provider_switch=False):
        path=w.get("path","")
        if not path:return
        if path in self.pending_bridge_recovery:return
        installed,error=ensure_bridge_installed(force=True)
        if not installed:
            QMessageBox.warning(self,"桥接修复失败",f"无法修复 VS Code 桥接：{error}")
            return
        self.pending_bridge_recovery[path]=(dict(w),profile,focus_after,provider_switch,0)
        self.collapse()
        QTimer.singleShot(600,lambda p=path:self.wait_bridge_recovery(p))
    def wait_bridge_recovery(self,path):
        pending=self.pending_bridge_recovery.get(path)
        if not pending:return
        w,profile,focus_after,provider_switch,attempt=pending
        if self.bridge_ready(w,provider_switch):
            self.pending_bridge_recovery.pop(path,None)
            self.switch_account(w,profile,focus_after)
            return
        if attempt>=25:
            self.pending_bridge_recovery.pop(path,None)
            QMessageBox.warning(self,"桥接恢复超时","桥接已重新安装，但目标 VS Code 窗口未在预期时间内响应。请在窗口完全打开后再点一次“切换并聚焦”。")
            return
        self.pending_bridge_recovery[path]=(w,profile,focus_after,provider_switch,attempt+1)
        QTimer.singleShot(500,lambda p=path:self.wait_bridge_recovery(p))
    def open_conversation(self,w,conversation):
        if not self.bridge_ready(w):
            QMessageBox.warning(self,"该窗口需要重载一次","这个 VS Code 窗口的本地桥接尚未就绪，请执行一次“开发人员: 重新加载窗口”后重试。"); return
        request_id=str(uuid.uuid4()); requests=BRIDGE_DIR/"requests"; requests.mkdir(parents=True,exist_ok=True)
        payload={"id":request_id,"action":"openConversation","targetPath":w["path"],"conversationId":conversation["id"]}
        (requests/f"{request_id}.json").write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
        self.pending_opens[request_id]=(w["id"],conversation["title"],0); self.collapse(); subprocess.run(["wmctrl","-i","-a",w["id"]]); QTimer.singleShot(300,lambda rid=request_id:self.wait_open_result(rid))
    def wait_open_result(self,request_id):
        pending=self.pending_opens.get(request_id)
        if not pending:return
        wid,title,attempt=pending; result_file=BRIDGE_DIR/"results"/f"{request_id}.json"
        if result_file.exists():
            try:result=json.loads(result_file.read_text())
            except Exception:result={"ok":False,"error":"结果文件损坏"}
            try:result_file.unlink()
            except Exception:pass
            self.pending_opens.pop(request_id,None)
            if result.get("ok"):subprocess.run(["wmctrl","-i","-a",wid]); QTimer.singleShot(250,self.ensure_on_top)
            else:QMessageBox.warning(self,"打开对话失败",f"未能打开“{title}”：{result.get('error','未知错误')}")
            return
        if attempt>=20:
            self.pending_opens.pop(request_id,None)
            try:(BRIDGE_DIR/"requests"/f"{request_id}.json").unlink()
            except Exception:pass
            QMessageBox.warning(self,"打开对话超时",f"目标窗口没有确认“{title}”，请重载该 VS Code 窗口后重试。"); return
        self.pending_opens[request_id]=(wid,title,attempt+1); QTimer.singleShot(500,lambda rid=request_id:self.wait_open_result(rid))
    def wait_switch_result(self,request_id):
        pending=self.pending_focus.get(request_id)
        if not pending:return
        wid,path,name,attempt=pending; result_file=BRIDGE_DIR/"results"/f"{request_id}.json"
        if result_file.exists():
            try:result=json.loads(result_file.read_text())
            except Exception:result={"ok":False,"error":"结果文件损坏"}
            try:result_file.unlink()
            except Exception:pass
            self.pending_focus.pop(request_id,None)
            if result.get("ok"):
                QTimer.singleShot(1800,lambda:self.finish_switch_focus(wid))
            else:QMessageBox.warning(self,"切换失败",f"未能切换到 {name}：{result.get('error','未知错误')}")
            return
        if attempt>=20:
            self.pending_focus.pop(request_id,None)
            try:(BRIDGE_DIR/"requests"/f"{request_id}.json").unlink()
            except Exception:pass
            QMessageBox.warning(self,"切换超时",f"{name} 的切换请求没有被目标窗口确认，请重载该 VS Code 窗口后重试。"); return
        self.pending_focus[request_id]=(wid,path,name,attempt+1); QTimer.singleShot(500,lambda rid=request_id:self.wait_switch_result(rid))
    def finish_switch_focus(self,wid):
        subprocess.run(["wmctrl","-i","-a",wid]); QTimer.singleShot(250,self.ensure_on_top)
    def focus(self,wid):
        w=next((x for x in self.windows if x["id"]==wid),None)
        if w and w["completed"]:self.seen[w["path"]]=w["completed"]; SEEN_FILE.write_text(json.dumps(self.seen,ensure_ascii=False,indent=2)); self.refresh()
        pending=self.pending_accounts.get(w["path"]) if w else None
        if pending:self.switch_account(w,pending,True); return
        self.collapse(); subprocess.run(["wmctrl","-i","-a",wid]); QTimer.singleShot(250,self.ensure_on_top)
    def closeEvent(self,event):
        self.timer.stop(); self.system_timer.stop()
        self.cancel_vocab_audio(True)
        for executor in (self.feed_executor,self.system_executor,self.tts_executor):
            try:executor.shutdown(wait=False,cancel_futures=True)
            except TypeError:executor.shutdown(wait=False)
        event.accept()

def main():
    app=QApplication(sys.argv); app.setApplicationName("codex-control-tower"); app.setApplicationDisplayName("Codex 任务总控台");
    if hasattr(app,"setDesktopFileName"):app.setDesktopFileName("codex-control-tower")
    app.setWindowIcon(QIcon(str(ASSETS_DIR/"codex-control-tower.svg"))); app.setFont(QFont("Noto Sans CJK SC",13)); w=App(); w.show(); sys.exit(app.exec() if hasattr(app,"exec") else app.exec_())
