"""Bounded, contextual multi-source learning feed for robotics research."""
import hashlib, json, math, os, re, sqlite3, time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE=Path(__file__).resolve().parent
DB=BASE/"learning.db"

TOPIC_RULES={
    "VLN / 导航":(("vln","navigation","nav","map","mapping","topological","spatial"),("vision language navigation","embodied navigation","spatial reasoning","robot mapping")),
    "VLA / 操作":(("vla","lerobot","manipulation","grasp","aloha","openvla","pi0"),("vision language action","robot manipulation","imitation learning","cross embodiment")),
    "仿真 / Sim2Real":(("isaac","sim","simulation","gazebo","mujoco","sim2real","omniverse"),("robot simulation","sim to real","synthetic robot data")),
    "无人机 / 移动机器人":(("uav","drone","fly","quadrotor","ros","slam"),("aerial robotics","visual navigation","slam","mobile robot")),
}

def _env(name):
    if os.environ.get(name):return os.environ[name]
    try:
        for line in (BASE/".env").read_text(encoding="utf-8").splitlines():
            key,sep,value=line.partition("=")
            if sep and key.strip()==name:return value.strip().strip('"').strip("'")
    except Exception:pass
    return ""

def context_profile(text):
    lower=text.lower(); labels=[]; terms=[]
    for label,(needles,expansions) in TOPIC_RULES.items():
        if any(x in lower for x in needles):labels.append(label); terms.extend(expansions)
    if not labels:labels=["机器人前沿"]; terms.extend(("robot learning","embodied ai","vision language action"))
    # Never retain or upload raw folder names, paths, or conversation titles.
    return {"label":" · ".join(labels[:2]),"terms":list(dict.fromkeys(terms))[:12]}

def _request_json(url,timeout=20):
    return json.loads(urlopen(Request(url,headers={"User-Agent":"Codex-Control-Tower/0.2"}),timeout=timeout).read())

def _arxiv(query,limit,sort_by="submittedDate"):
    url="https://export.arxiv.org/api/query?"+urlencode({"search_query":query,"start":0,"max_results":limit,"sortBy":sort_by,"sortOrder":"descending"})
    root=ET.fromstring(urlopen(Request(url,headers={"User-Agent":"Codex-Control-Tower/0.2 (personal research reader)"}),timeout=20).read()); ns={"a":"http://www.w3.org/2005/Atom"}; rows=[]
    for entry in root.findall("a:entry",ns):
        link=next((x.get("href") for x in entry.findall("a:link",ns) if x.get("rel")=="alternate"),entry.findtext("a:id",default="",namespaces=ns)); arxiv_id=link.rstrip("/").split("/")[-1]
        rows.append({"kind":"paper","source":"arXiv","title":" ".join(entry.findtext("a:title",default="",namespaces=ns).split()),"abstract":" ".join(entry.findtext("a:summary",default="",namespaces=ns).split()),"published":entry.findtext("a:published",default="",namespaces=ns)[:10],"url":link,"external_id":arxiv_id})
    return rows

def arxiv_candidates(context,limit=28):
    base='(cat:cs.RO OR cat:cs.CV OR cat:cs.AI OR cat:cs.LG) AND (all:robot OR all:embodied OR all:"vision language action" OR all:"vision language navigation")'
    rows=_arxiv(base,limit)
    focused=[t for t in context.get("terms",[]) if " " in t][:4]
    if focused:
        query='(cat:cs.RO OR cat:cs.CV OR cat:cs.AI OR cat:cs.LG) AND ('+" OR ".join(f'all:"{x}"' for x in focused)+')'
        # A relevance lane complements the newest-first lane, so a highly
        # matching established work can surface even when it is not brand-new.
        try:rows+=_arxiv(query,12,"relevance")
        except Exception:pass
    return dedupe(rows)

def video_candidates(limit=12):
    channels=(("Google DeepMind","UCP7jMXSY2xbc3KCAE0MHQ-A",("robot","gemini robotics","embodied")),("Boston Dynamics","UC7vVhkEfw4nOGp8TyDk7RcQ",()),("NVIDIA Developer","UCBHcMCGaiJhv-ESTcWGJPcw",("robot","gr00t","isaac","physical ai","embodied")))
    atom="http://www.w3.org/2005/Atom"; media="http://search.yahoo.com/mrss/"; yt="http://www.youtube.com/xml/schemas/2015"; rows=[]
    for source,channel,keywords in channels:
        try:
            root=ET.fromstring(urlopen(Request("https://www.youtube.com/feeds/videos.xml?channel_id="+channel,headers={"User-Agent":"Codex-Control-Tower/0.2"}),timeout=15).read())
            for entry in root.findall(f"{{{atom}}}entry"):
                title=entry.findtext(f"{{{atom}}}title",default=""); desc=entry.findtext(f"{{{media}}}group/{{{media}}}description",default=""); text=(title+" "+desc).lower()
                if keywords and not any(x in text for x in keywords):continue
                video_id=entry.findtext(f"{{{yt}}}videoId",default="")
                rows.append({"kind":"video","source":source,"title":title,"abstract":" ".join(desc.split())[:1800],"published":entry.findtext(f"{{{atom}}}published",default="")[:10],"url":"https://www.youtube.com/watch?v="+video_id,"external_id":video_id})
        except Exception:pass
    rows.sort(key=lambda x:x["published"],reverse=True); return rows[:limit]

def huggingface_candidates(context,limit=15):
    searches=["robotics","vision language action"]
    if any("navigation" in x for x in context.get("terms",[])):searches.append("robot navigation")
    rows=[]
    for query in searches:
        try:
            url="https://huggingface.co/api/models?"+urlencode({"search":query,"sort":"trendingScore","direction":-1,"limit":8,"full":"true"})
            for model in _request_json(url):
                model_id=model.get("id") or model.get("modelId"); tags=model.get("tags") or []; updated=(model.get("lastModified") or "")[:10]
                description=f"开源模型仓库；任务标签：{', '.join(tags[:12])}。下载 {model.get('downloads',0)}，点赞 {model.get('likes',0)}，趋势分 {model.get('trendingScore',0)}。"
                rows.append({"kind":"model","source":"Hugging Face","title":model_id,"abstract":description,"published":updated,"url":"https://huggingface.co/"+model_id,"external_id":model_id,"downloads":model.get("downloads",0) or 0,"likes":model.get("likes",0) or 0,"trending":model.get("trendingScore",0) or 0,"open_source":True})
        except Exception:pass
    rows=dedupe(rows); rows.sort(key=lambda x:(x.get("trending",0),x.get("likes",0),x.get("downloads",0)),reverse=True); return rows[:limit]

def dedupe(items):
    seen=set(); rows=[]
    for item in items:
        key=(item.get("url") or re.sub(r"\W+","",item.get("title","").lower()))
        if not key or key in seen:continue
        seen.add(key); rows.append(item)
    return rows

def _days_old(date):
    try:return max(0,(datetime.now(timezone.utc).date()-datetime.strptime(date,"%Y-%m-%d").date()).days)
    except Exception:return 365

def score_item(item,context,was_read=False):
    text=(item.get("title","")+" "+item.get("abstract","")).lower(); hits=[x for x in context.get("terms",[]) if x.lower() in text]
    relevance=min(42,len(hits)*10); recency=max(0,25-_days_old(item.get("published",""))*0.7)
    if item.get("kind")=="video":impact=16
    elif item.get("kind")=="model":impact=min(25,6+math.log10(item.get("downloads",0)+1)*4+item.get("likes",0)*0.25+item.get("trending",0)*1.2)
    else:
        anchors=("openvla","π0","pi0","gr00t","gemini robotics","lerobot","droid","libero","open x-embodiment")
        impact=7+min(12,sum(x in text for x in anchors)*4)
    open_score=10 if item.get("open_source") or item.get("kind")=="model" else 0; read_penalty=35 if was_read else 0
    score=round(max(0,relevance+recency+impact+open_score-read_penalty),1)
    reasons=[]
    if hits:reasons.append("匹配当前项目："+"、".join(hits[:3]))
    if item.get("kind")=="model":reasons.append("开源趋势模型")
    elif item.get("kind")=="video":reasons.append("官方 Demo")
    elif _days_old(item.get("published",""))<=7:reasons.append("近7天新论文")
    return score,"；".join(reasons) or "机器人前沿探索"

class Store:
    def __init__(self,path=DB):self.path=path; self.init()
    def connect(self):
        con=sqlite3.connect(self.path,timeout=5); con.execute("PRAGMA journal_mode=WAL"); return con
    @contextmanager
    def session(self):
        con=self.connect()
        try:
            with con:yield con
        finally:con.close()
    def init(self):
        with self.session() as con:
            con.execute("CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY,url TEXT UNIQUE,kind TEXT,source TEXT,title TEXT,published TEXT,score REAL,payload TEXT,first_seen INTEGER,last_seen INTEGER,read_at INTEGER DEFAULT 0,saved INTEGER DEFAULT 0)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_items_last ON items(last_seen DESC)")
    def known(self):
        with self.session() as con:return {r[0]:bool(r[1]) for r in con.execute("SELECT url,read_at FROM items")}
    def upsert(self,items):
        now=int(time.time())
        with self.session() as con:
            for x in items:
                ident=hashlib.sha1((x.get("url") or x.get("title","")).encode()).hexdigest(); payload=json.dumps(x,ensure_ascii=False)
                con.execute("INSERT INTO items(id,url,kind,source,title,published,score,payload,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET kind=excluded.kind,source=excluded.source,title=excluded.title,published=excluded.published,score=excluded.score,payload=excluded.payload,last_seen=excluded.last_seen",(ident,x.get("url"),x.get("kind"),x.get("source"),x.get("title"),x.get("published"),x.get("score",0),payload,now,now))
        self.cleanup()
    def recent(self,limit=12):
        with self.session() as con:rows=con.execute("SELECT payload,read_at,saved FROM items ORDER BY last_seen DESC,score DESC LIMIT ?",(limit,)).fetchall()
        result=[]
        for payload,read_at,saved in rows:
            try:x=json.loads(payload); x["read"]=bool(read_at); x["saved"]=bool(saved); result.append(x)
            except Exception:pass
        return result
    def mark_read(self,url):
        with self.session() as con:con.execute("UPDATE items SET read_at=? WHERE url=?",(int(time.time()),url))
    def toggle_saved(self,url):
        with self.session() as con:
            row=con.execute("SELECT saved FROM items WHERE url=?",(url,)).fetchone(); value=0 if row and row[0] else 1; con.execute("UPDATE items SET saved=? WHERE url=?",(value,url)); return bool(value)
    def cleanup(self,max_items=1000,max_age_days=60):
        cutoff=int(time.time())-max_age_days*86400
        with self.session() as con:
            con.execute("DELETE FROM items WHERE saved=0 AND last_seen<?",(cutoff,)); count=con.execute("SELECT count(*) FROM items").fetchone()[0]
            if count>max_items:con.execute("DELETE FROM items WHERE id IN (SELECT id FROM items WHERE saved=0 ORDER BY last_seen ASC, score ASC LIMIT ?)",(count-max_items,))
    def stats(self):
        with self.session() as con:count,saved=con.execute("SELECT count(*),sum(saved) FROM items").fetchone()
        size=sum(p.stat().st_size for p in self.path.parent.glob(self.path.name+"*") if p.is_file()); return {"count":count,"saved":saved or 0,"bytes":size,"limit":1000}

def _digest(items,context):
    key=_env("DEEPSEEK_API_KEY")
    if not key:raise RuntimeError("未配置 DeepSeek API Key")
    compact=[{"index":i,"type":x["kind"],"source":x["source"],"title":x["title"],"description":x["abstract"][:1600],"published":x["published"],"signals":{"downloads":x.get("downloads"),"likes":x.get("likes"),"trending":x.get("trending")}} for i,x in enumerate(items)]
    prompt=f"""你是机器人研究前沿编辑。用户当前上下文：{context.get('label')}；相关词：{context.get('terms')}。对候选条目输出严格JSON数组，每项字段 index、summary、delta、why、seconds、tags。summary不超过45字；delta不超过55字，说明相对OpenVLA/π0/GR00T/VLN的具体增量；why不超过45字并指出限制；seconds取20/30/45/60；tags最多3个。只能依据所给描述，不得编造实验或影响力。候选：\n"""+json.dumps(compact,ensure_ascii=False)
    payload={"model":"deepseek-v4-flash","messages":[{"role":"system","content":"只输出合法JSON，忠于证据。"},{"role":"user","content":prompt}],"thinking":{"type":"disabled"},"temperature":0.2,"max_tokens":3500,"stream":False}
    req=Request("https://api.deepseek.com/chat/completions",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Authorization":"Bearer "+key}); response=json.loads(urlopen(req,timeout=50).read()); text=response["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):text=text.split("\n",1)[1].rsplit("```",1)[0]
    return {int(x["index"]):x for x in json.loads(text)}

def _diverse_pick(candidates,count):
    picked=[]
    for kind in ("paper","video","model"):
        item=next((x for x in candidates if x["kind"]==kind and x not in picked),None)
        if item:picked.append(item)
    picked.extend(x for x in candidates if x not in picked)
    return picked[:count]

def build_feed(count,context):
    store=Store(); known=store.known(); candidates=[]; errors=[]
    for loader in (lambda:arxiv_candidates(context),lambda:video_candidates(),lambda:huggingface_candidates(context)):
        try:candidates.extend(loader())
        except Exception as exc:errors.append(str(exc))
    candidates=dedupe(candidates)
    for item in candidates:
        was_read=known.get(item.get("url"),False)
        item["score"],item["recommend_reason"]=score_item(item,context,was_read)
        item["read"]=was_read
    candidates.sort(key=lambda x:x["score"],reverse=True); selected=_diverse_pick(candidates,count)
    try:digests=_digest(selected,context)
    except Exception as exc:digests={}; errors.append("AI摘要："+str(exc))
    for i,item in enumerate(selected):
        d=digests.get(i,{}); item.update({"summary":d.get("summary") or item["abstract"][:130]+"…","delta":d.get("delta") or "等待增量分析","why":d.get("why") or item["recommend_reason"],"seconds":d.get("seconds",45),"tags":d.get("tags") or [item["kind"],item["source"]]})
    store.upsert(selected)
    # Read/save state belongs to the local database, not the remote source payload.
    state={x["url"]:x for x in store.recent(1000)}
    for item in selected:
        local=state.get(item.get("url"),{})
        item["read"]=local.get("read",False); item["saved"]=local.get("saved",False)
    return selected,"；".join(errors),store.stats()
