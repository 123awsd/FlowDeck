"""Qt UI: crisp Chinese text, VS Code discovery and task management."""
import hashlib, json, sqlite3, subprocess, sys, uuid
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from learning_feed import Store as LearningStore, build_feed as build_learning_feed_v2, context_profile
from system_monitor import SystemMonitor
try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPen
    from PySide6.QtWidgets import *
except ImportError:
    from PyQt5.QtCore import Qt, QTimer, QEvent
    from PyQt5.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPen
    from PyQt5.QtWidgets import *

BASE=Path(__file__).resolve().parent; DATA=BASE/"tasks.json"; TODOS_FILE=BASE/"daily_todos.json"; EVENTS=BASE/"events.jsonl"
PROFILE_FILE=Path.home()/".config/Code/User/globalStorage/woozy-masta.codex-switch/profiles.json"
GLOBAL_DB=Path.home()/".config/Code/User/globalStorage/state.vscdb"
SEEN_FILE=BASE/"seen_sessions.json"
BRIDGE_DIR=Path.home()/".codex-window-manager"
STATES=["Running","Needs input","Ready","Blocked","Done"]
LABELS=dict(zip(STATES,["执行中","需要输入","已就绪","已阻塞","已完成"]))
COLORS=dict(zip(STATES,["#2563eb","#d97706","#059669","#dc2626","#64748b"]))
SESSION_ROOT=Path.home()/".codex/sessions"
_SESSION_HEADERS={}
_SESSION_STREAMS={}
_CONVERSATION_TITLES={}
_LAST_BRIDGE_CLEANUP=0

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
        out.append(dict(id=wid,pid=pid,title=title,folder=name,path=path,account=session_account or profile.get("name","未知账号"),account_scope="最近请求" if session_account else ("工作区" if workspace_id else "插件当前"),status=status,completed=completed))
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

class App(QWidget):
    def __init__(self):
        super().__init__(); self.tasks=self.load(); self.todos=self.load_todos(); self.view_mode="monitor"; self.windows=[]; self.expanded=False; self.pending_accounts={}; self.pending_focus={}; self.pending_opens={}; self.feed_error=""; self.feed_future=None; self.feed_executor=ThreadPoolExecutor(max_workers=1); self.feed_store=LearningStore(); self.feed_items=self.feed_store.recent(12); self.feed_stats=self.feed_store.stats(); self.learning_context={"label":"机器人前沿","terms":[]}; self.system_monitor=SystemMonitor(); self.system_executor=ThreadPoolExecutor(max_workers=1); self.system_future=None; self.system_metrics=self.system_monitor.empty(); self.system_history={"cpu":deque(maxlen=60),"memory":deque(maxlen=60),"gpu":deque(maxlen=60),"disk":deque(maxlen=60)}
        try:self.seen=json.loads(SEEN_FILE.read_text())
        except Exception:self.seen={}
        self.setWindowTitle("Codex 任务总控台"); self.setWindowIcon(QIcon(str(BASE/"assets/codex-control-tower.svg"))); self.setWindowFlag(Qt.WindowStaysOnTopHint,True); self.setAttribute(Qt.WA_TranslucentBackground,True); self.setObjectName("root")
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
        shell_layout.addWidget(self.header); self.area=QScrollArea(); self.area.setWidgetResizable(True); self.content=QWidget(); self.box=QVBoxLayout(self.content); self.box.setSpacing(7); self.area.setWidget(self.content); shell_layout.addWidget(self.area); self.root.addWidget(self.shell); self.refresh(); self.collapse()
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
        self.expanded=True; self.setWindowFlag(Qt.FramelessWindowHint,True); self.setWindowFlag(Qt.WindowStaysOnTopHint,True); self.setMinimumSize(740,420); self.setMaximumSize(16777215,16777215); self.root.setContentsMargins(6,6,6,6); self.bubble.hide(); self.shell.show(); self.area.show(); self.resize(840,540); self.show(); QTimer.singleShot(100,self.ensure_on_top)
    def collapse(self):
        if self.isMaximized():self.showNormal()
        self.expanded=False; self.shell.hide(); self.bubble.show(); self.root.setContentsMargins(0,0,0,0); self.setMinimumSize(58,58); self.setMaximumSize(58,58); self.setWindowFlag(Qt.FramelessWindowHint,True); self.setWindowFlag(Qt.WindowStaysOnTopHint,True); self.resize(58,58); self.show(); QTimer.singleShot(100,self.ensure_on_top)
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
    def refresh(self,render=True):
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
        elif self.view_mode=="todo":self.summary.setText(f"{len(active_todos)} 项待办 · 今天完成 {len(done_today)}")
        elif self.view_mode=="learn":self.summary.setText(f"{self.running_count} 个任务运行中 · {len(self.feed_items)} 条前沿卡片")
        else:
            cpu=self.system_metrics.get("cpu",{}).get("percent",0); memory=self.system_metrics.get("memory",{}).get("percent",0); gpu=self.system_metrics.get("gpu",[]); gpu_text=f"GPU {gpu[0].get('percent',0):.0f}%" if gpu else "GPU --"
            self.summary.setText(f"CPU {cpu:.0f}% · 内存 {memory:.0f}% · {gpu_text}")
        self.update_tabs(); self.bubble.setUnread(unread); self.bubble.setToolTip(f"运行 {self.running_count} · 完成 {self.done_count} · 待查看 {unread} · 今日待办 {len(active_todos)}")
        if not render:return
        self.clear()
        if self.view_mode=="monitor":
            self.window_panel()
            for t in self.tasks:self.task_card(t)
            self.account_panel()
        elif self.view_mode=="todo":self.todo_panel()
        elif self.view_mode=="learn":self.learning_panel()
        else:self.system_panel()
        self.box.addStretch()
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
        card=QFrame(); card.setObjectName("systemCard"); card.setMinimumHeight(96); card.setStyleSheet(f"QFrame#systemCard{{background:white;border:1px solid #dbe3ed;border-radius:11px}} QLabel{{background:transparent}}"); layout=QVBoxLayout(card); layout.setContentsMargins(13,11,13,9); layout.setSpacing(3)
        head=QHBoxLayout(); label=QLabel(title); label.setStyleSheet("color:#475569;font-size:11px;font-weight:700"); head.addWidget(label); head.addStretch(); indicator=QLabel("实时"); indicator.setStyleSheet(f"color:{color};background:{color}22;padding:2px 6px;border-radius:4px;font-size:9px;font-weight:700"); head.addWidget(indicator); layout.addLayout(head)
        number=QLabel(value); number.setFont(QFont("Noto Sans CJK SC",21,QFont.Bold)); number.setStyleSheet(f"color:{color}"); layout.addWidget(number)
        spark=Sparkline(color); spark.set_values(self.system_history.get(key,[])); spark.setFixedHeight(34); layout.addWidget(spark)
        note=QLabel(detail); note.setStyleSheet("color:#64748b;font-size:10px"); note.setWordWrap(True); layout.addWidget(note)
        return card
    def system_panel(self):
        metrics=self.system_metrics; cpu=metrics.get("cpu",{}); memory=metrics.get("memory",{}); gpus=metrics.get("gpu",[]); disks=metrics.get("disks",[]); network=metrics.get("network",{}); disk_io=metrics.get("disk_io",{})
        panel=QFrame(); panel.setObjectName("systemPanel"); panel.setStyleSheet("QFrame#systemPanel{background:#f0fdfa;border:1px solid #99f6e4;border-radius:11px} QLabel{background:transparent}"); outer=QVBoxLayout(panel); outer.setContentsMargins(14,13,14,14); outer.setSpacing(10)
        head=QHBoxLayout(); title=QLabel("系统监控"); title.setFont(QFont("Noto Sans CJK SC",16,QFont.Bold)); title.setStyleSheet("color:#134e4a"); head.addWidget(title); subtitle=QLabel("本机资源 · 2 秒采样 · 只保留内存中的最近曲线"); subtitle.setStyleSheet("color:#0f766e;font-size:11px"); head.addWidget(subtitle); head.addStretch(); head.addWidget(QLabel("不产生告警")); outer.addLayout(head)
        grid=QGridLayout(); grid.setSpacing(8)
        temp=f" · {cpu.get('temperature'):.0f}°C" if cpu.get("temperature") else " · 温度不可用"; memory_detail=f"{format_bytes(memory.get('used'))} / {format_bytes(memory.get('total'))} · 可用 {format_bytes(memory.get('available'))}" if memory.get("total") else "等待采样"
        gpu_util=max((g.get("percent",0) for g in gpus),default=0); gpu_used=sum(g.get("used",0) for g in gpus); gpu_total=sum(g.get("total",0) for g in gpus); gpu_value=f"{gpu_util:.0f}%" if gpus else "--"; gpu_detail=(f"{len(gpus)} 张 · 显存 {format_bytes(gpu_used)} / {format_bytes(gpu_total)}" if gpus else "未检测到可用 NVIDIA 数据")
        disk=disks[0] if disks else {}; disk_value=f"{disk.get('percent',0):.0f}%" if disk else "--"; disk_detail=f"{len(disks)} 个挂载点 · {format_bytes(disk.get('free'))} 可用" if disk else "等待采样"
        grid.addWidget(self.system_card("CPU",f"{cpu.get('percent',0):.0f}%",f"{cpu.get('cores',0)} 核 · 负载 {cpu.get('load',0):.2f}{temp}","#2563eb","cpu"),0,0); grid.addWidget(self.system_card("内存",f"{memory.get('percent',0):.0f}%",memory_detail,"#7c3aed","memory"),0,1); grid.addWidget(self.system_card("GPU / 显存",gpu_value,gpu_detail,"#ea580c","gpu"),1,0); grid.addWidget(self.system_card("磁盘",disk_value,disk_detail,"#059669","disk"),1,1); outer.addLayout(grid)
        details=QFrame(); details.setMinimumHeight(55); details.setStyleSheet("background:white;border:1px solid #ccfbf1;border-radius:9px"); detail_grid=QGridLayout(details); detail_grid.setContentsMargins(12,10,12,10); detail_grid.setHorizontalSpacing(28)
        detail_grid.addWidget(QLabel("网络"),0,0); detail_grid.addWidget(QLabel(f"↓ {format_rate(network.get('download',0))}   ↑ {format_rate(network.get('upload',0))}"),1,0); detail_grid.addWidget(QLabel("磁盘读写"),0,1); detail_grid.addWidget(QLabel(f"读 {format_rate(disk_io.get('read',0))}   写 {format_rate(disk_io.get('write',0))}"),1,1); detail_grid.addWidget(QLabel("Swap"),0,2); detail_grid.addWidget(QLabel(f"{memory.get('swap_percent',0):.0f}% · {format_bytes(memory.get('swap_used'))} / {format_bytes(memory.get('swap_total'))}"),1,2)
        for i in range(3):detail_grid.itemAtPosition(0,i).widget().setStyleSheet("color:#64748b;font-size:10px;font-weight:700"); detail_grid.itemAtPosition(1,i).widget().setStyleSheet("color:#0f172a;font-size:11px;font-weight:600")
        outer.addWidget(details)
        disk_box=QFrame(); disk_box.setMinimumHeight(42+len(disks)*38); disk_box.setStyleSheet("background:white;border:1px solid #d1fae5;border-radius:9px"); disk_layout=QVBoxLayout(disk_box); disk_layout.setContentsMargins(12,9,12,9); disk_title=QLabel(f"全部磁盘挂载  ·  {len(disks)} 个"); disk_title.setStyleSheet("color:#065f46;font-weight:700"); disk_layout.addWidget(disk_title)
        for disk_item in disks:
            disk_row=QFrame(); disk_row.setMinimumHeight(34); disk_row.setStyleSheet("background:#f8fafc;border-radius:7px"); disk_row_layout=QVBoxLayout(disk_row); disk_row_layout.setContentsMargins(8,6,8,6); disk_line=QHBoxLayout(); mount_label=QLabel(disk_item.get("mount","/")); mount_label.setStyleSheet("color:#0f172a;font-size:10px;font-weight:700"); disk_line.addWidget(mount_label); source_label=QLabel(f"{disk_item.get('fstype','')}  ·  {disk_item.get('source','')}"); source_label.setStyleSheet("color:#94a3b8;font-size:9px"); disk_line.addWidget(source_label); disk_line.addStretch(); percent_label=QLabel(f"{disk_item.get('percent',0):.0f}%  ·  {format_bytes(disk_item.get('free'))} 可用"); percent_label.setStyleSheet("color:#047857;font-size:10px;font-weight:700"); disk_line.addWidget(percent_label); disk_row_layout.addLayout(disk_line); disk_bar=QProgressBar(); disk_bar.setTextVisible(False); disk_bar.setRange(0,100); disk_bar.setValue(max(0,min(100,int(disk_item.get('percent',0))))); disk_bar.setStyleSheet("QProgressBar{height:5px;border:0;border-radius:2px;background:#e2e8f0} QProgressBar::chunk{background:#10b981;border-radius:2px}"); disk_row_layout.addWidget(disk_bar); disk_layout.addWidget(disk_row)
        outer.addWidget(disk_box)
        if gpus:
            gpu_box=QFrame(); gpu_box.setStyleSheet("background:white;border:1px solid #fed7aa;border-radius:9px"); gpu_layout=QVBoxLayout(gpu_box); gpu_layout.setContentsMargins(12,9,12,9); gpu_layout.addWidget(QLabel("GPU 详情"))
            for gpu in gpus:
                row=QLabel(f"GPU {gpu.get('index')}  {gpu.get('name','未知')}    利用率 {gpu.get('percent',0):.0f}%    显存 {format_bytes(gpu.get('used'))}/{format_bytes(gpu.get('total'))}    温度 {gpu.get('temperature',0):.0f}°C    功耗 {gpu.get('power',0):.0f} W"); row.setStyleSheet("color:#475569;font-size:11px"); gpu_layout.addWidget(row)
            outer.addWidget(gpu_box)
        process_box=QFrame(); process_box.setStyleSheet("background:white;border:1px solid #dbe3ed;border-radius:9px"); process_layout=QVBoxLayout(process_box); process_layout.setContentsMargins(12,9,12,9); process_layout.addWidget(QLabel("高占用进程")); table=QTableWidget(min(5,len(metrics.get('processes',[]))),4); table.setHorizontalHeaderLabels(["进程","CPU","内存","PID"]); table.verticalHeader().setVisible(False); table.setEditTriggers(QAbstractItemView.NoEditTriggers); table.setSelectionMode(QAbstractItemView.NoSelection); table.setFocusPolicy(Qt.NoFocus); table.setShowGrid(False); table.setMinimumHeight(150); table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
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
            meta=QHBoxLayout(); account=QLabel(w["account"]); account.setStyleSheet("color:#4338ca;background:#eef2ff;padding:3px 8px;border-radius:5px;font-size:12px"); meta.addWidget(account); status=QLabel("待查看" if unread else state); status.setStyleSheet(f"color:{'#b91c1c' if unread else '#475569'};background:{'#fee2e2' if unread else '#f1f5f9'};padding:3px 8px;border-radius:5px;font-weight:{'700' if unread else '500'};font-size:12px"); meta.addWidget(status); meta.addStretch(); info.addLayout(meta); h.addLayout(info,1)
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
            if not available:disabled=menu.addAction("暂无可用额度账号"); disabled.setEnabled(False)
            selector.setMenu(menu); selector.setToolTip("先选择账号，再点聚焦应用切换"); h.addWidget(selector)
            create=QPushButton("加待办"); create.setToolTip("把这个项目加入今日待办"); create.clicked.connect(lambda _,x=w:self.prefill_todo(x)); h.addWidget(create)
            focus=QPushButton("切换并聚焦" if pending else ("查看" if unread else "聚焦")); focus.setStyleSheet("background:#ea580c;color:white;border:0" if pending else ("background:#dc2626;color:white;border:0" if unread else "background:#2563eb;color:white;border:0")); focus.clicked.connect(lambda _,x=w:self.focus(x["id"])); h.addWidget(focus); v.addWidget(card)
        self.box.addWidget(p)
    def account_panel(self):
        p=QFrame(); p.setStyleSheet("QFrame{background:#f0fdf9;border-radius:11px} QLabel{background:transparent;color:#065f46}"); v=QVBoxLayout(p); heading=QLabel("账号额度"); heading.setFont(QFont("Noto Sans CJK SC",14,QFont.Bold)); v.addWidget(heading); h=QHBoxLayout(); h.setSpacing(8)
        for profile in profiles():
            limits=profile.get("limits",{}); primary=limits.get("primary") or {}; secondary=limits.get("secondary") or {}
            card=QFrame(); card.setObjectName("quotaCard"); card.setStyleSheet("QFrame#quotaCard{background:white;border:1px solid #bbf7d0;border-radius:8px}"); c=QVBoxLayout(card); c.setContentsMargins(10,8,10,8); name=QLabel(profile.get("name","未命名")); name.setFont(QFont("Noto Sans CJK SC",12,QFont.Bold)); c.addWidget(name)
            for label,window in (("5 小时",primary),("每周",secondary)):
                value=window.get("remainingPercent"); row=QHBoxLayout(); caption=QLabel(label); caption.setStyleSheet("color:#64748b;font-size:10px"); row.addWidget(caption); row.addStretch(); number=QLabel(f"{value if value is not None else '--'}%"); number.setStyleSheet("color:#047857;font-size:10px;font-weight:700"); row.addWidget(number); c.addLayout(row); reset=QLabel(f"{remaining_label(window.get('resetsAt'))} · {reset_label(window.get('resetsAt'))}"); reset.setStyleSheet("color:#94a3b8;font-size:9px"); c.addWidget(reset); bar=QProgressBar(); bar.setTextVisible(False); bar.setRange(0,100); bar.setValue(value or 0); c.addWidget(bar)
            h.addWidget(card)
        h.addStretch(); v.addLayout(h); self.box.addWidget(p)
    def learning_panel(self):
        panel=QFrame(); panel.setObjectName("learningPanel"); panel.setStyleSheet("QFrame#learningPanel{background:#eff6ff;border:1px solid #bfdbfe;border-radius:11px} QLabel{background:transparent}"); v=QVBoxLayout(panel); v.setContentsMargins(14,13,14,14); v.setSpacing(9)
        head=QHBoxLayout(); title=QLabel("等待学习 · Robot Frontier"); title.setFont(QFont("Noto Sans CJK SC",16,QFont.Bold)); title.setStyleSheet("color:#172554"); head.addWidget(title); head.addStretch()
        needs_review=[w for w in self.windows if w.get("completed",0)>self.seen.get(w.get("path",""),0)]; state_text=f"● {self.running_count} 运行中 · {len(needs_review)} 待处理"; state=QLabel(state_text); state.setStyleSheet(f"color:{'#b91c1c' if needs_review else '#1d4ed8'};background:{'#fee2e2' if needs_review else '#dbeafe'};padding:4px 9px;border-radius:6px;font-weight:700"); head.addWidget(state); v.addLayout(head)
        if needs_review:
            alert=QFrame(); alert.setObjectName("workAlert"); alert.setStyleSheet("QFrame#workAlert{background:#fff1f2;border:1px solid #fda4af;border-radius:9px} QLabel{background:transparent}"); alerts=QVBoxLayout(alert); alerts.setContentsMargins(11,8,9,8); label=QLabel(f"有 {len(needs_review)} 个 Codex 任务已经完成，需要你处理"); label.setStyleSheet("color:#9f1239;font-weight:700"); alerts.addWidget(label)
            for window in needs_review:
                row=QHBoxLayout(); name=QLabel(window.get("folder","未命名项目")); name.setStyleSheet("color:#1e293b;font-weight:600"); row.addWidget(name,1); view=QPushButton("立即查看"); view.setStyleSheet("background:#dc2626;color:white;border:0;font-weight:700"); view.clicked.connect(lambda _,x=window:self.focus(x["id"])); row.addWidget(view); alerts.addLayout(row)
            v.addWidget(alert)
        controls=QHBoxLayout(); hint=QLabel("当前推荐："+self.learning_context.get("label","机器人前沿")+" · 只读增量，不做无限信息流"); hint.setStyleSheet("color:#475569;font-size:11px"); controls.addWidget(hint); controls.addStretch(); controls.addWidget(QLabel("学习时长"))
        duration=QComboBox(); duration.addItem("3 分钟",3); duration.addItem("5 分钟",5); duration.addItem("10 分钟",10); duration.addItem("20 分钟",20); duration.setCurrentIndex(duration.findData(getattr(self,"learning_minutes",5))); duration.currentIndexChanged.connect(lambda:self.set_learning_minutes(duration.currentData())); controls.addWidget(duration)
        refresh=QPushButton("获取最新"); refresh.setEnabled(not (self.feed_future and not self.feed_future.done())); refresh.setStyleSheet("background:#2563eb;color:white;border:0;font-weight:700"); refresh.clicked.connect(self.start_learning_feed); controls.addWidget(refresh); v.addLayout(controls)
        if self.feed_future and not self.feed_future.done():
            loading=QLabel("正在扫描论文、官方 Demo 和开源模型，并生成个性化摘要…"); loading.setAlignment(Qt.AlignCenter); loading.setStyleSheet("color:#1d4ed8;background:white;padding:22px;border-radius:9px;font-weight:700"); v.addWidget(loading)
        elif not self.feed_items:
            empty=QLabel("点击“获取最新”，生成第一份机器人前沿学习包"); empty.setAlignment(Qt.AlignCenter); empty.setStyleSheet("color:#64748b;background:white;padding:26px;border-radius:9px"); v.addWidget(empty)
        if self.feed_error:
            warning=QLabel("部分来源或 AI 摘要暂不可用，其他内容仍可正常阅读 · "+self.feed_error[:100]); warning.setWordWrap(True); warning.setStyleSheet("color:#b45309;background:#fffbeb;padding:7px 9px;border-radius:6px;font-size:10px"); v.addWidget(warning)
        for item in self.feed_items:
            card=QFrame(); card.setObjectName("learningCard"); card.setStyleSheet("QFrame#learningCard{background:white;border:1px solid #dbeafe;border-radius:9px}"); c=QVBoxLayout(card); c.setContentsMargins(12,10,12,10); c.setSpacing(6)
            top=QHBoxLayout(); name=QLabel(item.get("title","未命名内容")); name.setWordWrap(True); name.setFont(QFont("Noto Sans CJK SC",13,QFont.Bold)); name.setStyleSheet("color:#0f172a"); top.addWidget(name,1); badge_text="▶ Demo 视频" if item.get("kind")=="video" else ("◆ 开源模型" if item.get("kind")=="model" else f"{item.get('seconds',45)} 秒读完"); seconds=QLabel(badge_text); seconds.setStyleSheet(f"color:{'#b91c1c' if item.get('kind')=='video' else '#0369a1'};background:{'#fee2e2' if item.get('kind')=='video' else '#e0f2fe'};padding:3px 7px;border-radius:5px;font-size:10px;font-weight:700"); top.addWidget(seconds); c.addLayout(top)
            read_label="  ·  已读" if item.get("read") else ""; meta=QLabel(f"{item.get('published','日期未知')}  ·  {item.get('source','')}  ·  推荐分 {item.get('score','--')}{read_label}  ·  "+" / ".join(item.get("tags",[])[:3])); meta.setStyleSheet("color:#94a3b8;font-size:10px" if item.get("read") else "color:#64748b;font-size:10px"); c.addWidget(meta)
            reason=QLabel("推荐理由："+item.get("recommend_reason","机器人前沿探索")); reason.setWordWrap(True); reason.setStyleSheet("color:#047857;background:#ecfdf5;padding:4px 7px;border-radius:5px;font-size:10px"); c.addWidget(reason)
            summary=QLabel("解决什么："+item.get("summary","")); summary.setWordWrap(True); summary.setStyleSheet("color:#1e293b;font-size:12px;font-weight:600"); c.addWidget(summary)
            delta=QLabel("相对已有工作："+item.get("delta","")); delta.setWordWrap(True); delta.setStyleSheet("color:#4338ca;font-size:11px"); c.addWidget(delta)
            why=QLabel("为什么值得看："+item.get("why","")); why.setWordWrap(True); why.setStyleSheet("color:#475569;font-size:11px"); c.addWidget(why)
            actions=QHBoxLayout(); actions.addStretch(); original=QPushButton("播放视频" if item.get("kind")=="video" else ("打开模型" if item.get("kind")=="model" else "查看原文")); original.setStyleSheet("background:#dc2626;color:white;border:0" if item.get("kind")=="video" else ""); original.clicked.connect(lambda _,u=item.get("url",""):self.open_learning_url(u)); actions.addWidget(original); mark=QPushButton("已收藏" if item.get("saved") else "收藏深读"); mark.setStyleSheet("background:#ede9fe;color:#6d28d9;border:0" if item.get("saved") else ""); mark.clicked.connect(lambda _,u=item.get("url",""):self.toggle_learning_saved(u)); actions.addWidget(mark); c.addLayout(actions); v.addWidget(card)
        stats=self.feed_stats; storage=QLabel(f"有界存储：{stats.get('count',0)}/{stats.get('limit',1000)} 条 · 收藏 {stats.get('saved',0)} · 占用 {stats.get('bytes',0)/1024/1024:.1f} MB · 普通记录60天自动清理"); storage.setAlignment(Qt.AlignCenter); storage.setStyleSheet("color:#64748b;font-size:10px;padding:6px"); v.addWidget(storage)
        self.box.addWidget(panel)
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
        try:self.feed_items,self.feed_error,self.feed_stats=self.feed_future.result()
        except Exception as exc:self.feed_error=str(exc)
        self.feed_future=None
        if self.view_mode=="learn":self.refresh()
    def open_learning_url(self,url):
        if url:
            self.feed_store.mark_read(url)
            for item in self.feed_items:
                if item.get("url")==url:item["read"]=True
            subprocess.Popen(["xdg-open",url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); self.refresh()
    def toggle_learning_saved(self,url):
        if url:self.feed_store.toggle_saved(url)
        self.feed_items=self.feed_store.recent(12); self.feed_stats=self.feed_store.stats(); self.refresh()
    def todo_panel(self):
        today=datetime.now().strftime("%Y-%m-%d"); visible=[t for t in self.todos if not t.get("done") or t.get("done_date")==today]
        priority_order={"高":0,"中":1,"低":2}; visible.sort(key=lambda t:(bool(t.get("done")),priority_order.get(t.get("priority","中"),1),t.get("created_at","")))
        panel=QFrame(); panel.setObjectName("todoPanel"); panel.setStyleSheet("QFrame#todoPanel{background:#f5f3ff;border:1px solid #ddd6fe;border-radius:11px} QLabel{background:transparent}"); layout=QVBoxLayout(panel); layout.setContentsMargins(14,13,14,14); layout.setSpacing(9)
        head=QHBoxLayout(); title=QLabel("今日待办"); title.setFont(QFont("Noto Sans CJK SC",16,QFont.Bold)); title.setStyleSheet("color:#312e81"); head.addWidget(title); head.addStretch(); completed=sum(t.get("done") for t in visible); progress=QLabel(f"已完成 {completed}/{len(visible)}"); progress.setStyleSheet("color:#6d28d9;background:#ede9fe;padding:4px 9px;border-radius:6px;font-weight:700"); head.addWidget(progress); layout.addLayout(head)
        hint=QLabel("未完成事项会自动保留到第二天"); hint.setStyleSheet("color:#7c3aed;font-size:11px"); layout.addWidget(hint)
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
            card=QFrame(); card.setObjectName("todoCard"); card.setStyleSheet("QFrame#todoCard{background:white;border:1px solid #e9d5ff;border-radius:8px}"); line=QHBoxLayout(card); line.setContentsMargins(11,8,8,8)
            check=QCheckBox(); check.setChecked(bool(todo.get("done"))); check.setCursor(Qt.PointingHandCursor); check.stateChanged.connect(lambda state,t=todo:self.toggle_todo(t,state)); line.addWidget(check)
            text=QLabel(todo.get("text","")); text.setWordWrap(True); text.setStyleSheet("color:#94a3b8;text-decoration:line-through" if todo.get("done") else "color:#1e293b;font-size:13px;font-weight:600"); line.addWidget(text,1)
            if todo.get("project"):
                project=QLabel(todo["project"]); project.setStyleSheet("color:#4338ca;background:#eef2ff;padding:3px 7px;border-radius:5px;font-size:10px"); line.addWidget(project)
            priority=todo.get("priority","中"); fg,bg=colors.get(priority,colors["中"]); badge=QLabel(priority); badge.setStyleSheet(f"color:{fg};background:{bg};padding:3px 7px;border-radius:5px;font-size:10px;font-weight:700"); line.addWidget(badge)
            remove=QPushButton("×"); remove.setFixedSize(28,28); remove.setToolTip("删除待办"); remove.setStyleSheet("QPushButton{padding:0;border:0;background:transparent;color:#94a3b8;font-size:17px} QPushButton:hover{background:#fee2e2;color:#dc2626}"); remove.clicked.connect(lambda _,t=todo:self.delete_todo(t)); line.addWidget(remove); layout.addWidget(card)
        self.box.addWidget(panel)
    def add_todo(self):
        text=self.todo_input.text().strip()
        if not text:return
        project_path=self.todo_project.currentData() or ""; project=self.todo_project.currentText() if project_path else ""
        self.todos.append({"id":uuid.uuid4().hex,"text":text,"priority":self.todo_priority.currentText(),"project":project,"project_path":project_path,"done":False,"created_at":datetime.now().isoformat(timespec="seconds")}); self.save_todos(); self.refresh()
    def toggle_todo(self,todo,state):
        todo["done"]=bool(state); todo["done_date"]=datetime.now().strftime("%Y-%m-%d") if state else ""; self.save_todos(); self.refresh()
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
    def bridge_ready(self,w):
        now=time.time(); candidates=[BRIDGE_DIR/f"ready-{w['path'].encode('utf-8').hex()}.json",BRIDGE_DIR/f"ready-name-{w['folder'].encode('utf-8').hex()}.json"]
        candidates.extend(BRIDGE_DIR.glob("ready-active-*.json"))
        for ready in candidates:
            try:
                info=json.loads(ready.read_text(encoding="utf-8"))
                if now-info.get("at",0)/1000>=8:continue
                if ready.name.startswith("ready-active-"):
                    active=info.get("activeFile","")
                    if not active or not (active==w["path"] or active.startswith(w["path"].rstrip("/")+"/")):continue
                return True
            except Exception:pass
        return False
    def switch_account(self,w,profile,focus_after=False):
        if not profile:return
        if not self.bridge_ready(w):
            self.collapse(); subprocess.run(["wmctrl","-i","-a",w["id"]]); QTimer.singleShot(250,self.ensure_on_top)
            QMessageBox.warning(self,"该窗口需要重载一次","这个 VS Code 窗口还没有加载本地桥接。\n\n请执行一次“开发人员: 重新加载窗口”，然后重新选择账号并点聚焦。")
            return
        request_id=str(uuid.uuid4()); requests=BRIDGE_DIR/"requests"; requests.mkdir(parents=True,exist_ok=True)
        payload={"id":request_id,"targetPath":w["path"],"profileId":profile["id"],"profileName":profile.get("name","未命名")}
        (requests/f"{request_id}.json").write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
        self.pending_focus[request_id]=(w["id"],w["path"],profile.get("name","未命名"),0)
        self.pending_accounts.pop(w["path"],None); self.collapse(); subprocess.run(["wmctrl","-i","-a",w["id"]]); QTimer.singleShot(500,lambda rid=request_id:self.wait_switch_result(rid))
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
        for executor in (self.feed_executor,self.system_executor):
            try:executor.shutdown(wait=False,cancel_futures=True)
            except TypeError:executor.shutdown(wait=False)
        event.accept()

def main():
    app=QApplication(sys.argv); app.setApplicationName("codex-control-tower"); app.setApplicationDisplayName("Codex 任务总控台");
    if hasattr(app,"setDesktopFileName"):app.setDesktopFileName("codex-control-tower")
    app.setWindowIcon(QIcon(str(BASE/"assets/codex-control-tower.svg"))); app.setFont(QFont("Noto Sans CJK SC",13)); w=App(); w.show(); sys.exit(app.exec() if hasattr(app,"exec") else app.exec_())
