"""Configurable, bounded research feed for embodied AI.

Retrieval is intentionally broad. User interests affect ranking and reading
depth, never candidate eligibility. Quality and scope gates run before a
global multi-channel allocator, so weak items are not inserted to fill quota.
"""
import hashlib, json, math, os, re, sqlite3, time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE=Path(__file__).resolve().parent
DB=BASE/"learning.db"
PREFERENCES_PATH=BASE/"learning_preferences.json"
ENGINE_VERSION=2
CHANNEL_LABELS={"core":"核心关注","adjacent":"相邻方向","major":"重大更新","emerging":"新趋势","serendipity":"探索发现"}
OPEN_TOPIC_RULES={
    "tactile_intelligence":("触觉智能",("tactile","touch sensing","visuotactile","force feedback")),
    "robot_memory":("机器人记忆",("robot memory","embodied memory","episodic memory","spatial memory")),
    "humanoid":("人形机器人",("humanoid","whole-body control","whole body control","bimanual")),
    "simulation":("仿真与 Sim2Real",("simulation","sim2real","sim-to-real","digital twin","synthetic environment")),
    "action_representation":("动作表示",("action tokenizer","action representation","action chunking","flow matching","diffusion policy","latent action")),
    "robot_agent":("机器人 Agent",("robot agent","agentic robot","tool-using robot","long-horizon planning")),
}

def _clamp(value,low=0.0,high=1.0):return max(low,min(high,float(value or 0)))
def _number(value,default=0.0):
    try:return float(value)
    except (TypeError,ValueError):return default
def _env(name):
    if os.environ.get(name):return os.environ[name]
    try:
        for line in (BASE/".env").read_text(encoding="utf-8").splitlines():
            key,sep,value=line.partition("=")
            if sep and key.strip()==name:return value.strip().strip('"').strip("'")
    except Exception:pass
    return ""

def load_preferences(path=PREFERENCES_PATH):
    """Load the user-owned preferences file with conservative fallbacks."""
    fallback={
        "scope":{"domain":"embodied_ai","label":"具身智能前沿","hard_exclude":[],"soft_exclude":[]},
        "interests":{},"recent_interests":{},"reference_works":[],
        "feed_mix":{"core":.4,"adjacent":.15,"major":.2,"emerging":.15,"serendipity":.1},
        "presentation":{"session_items":6,"video_preference":.55,"minimum_qualified_videos":2},
        "discovery":{"interest_can_filter_candidates":False,"allow_unknown_topics":True,"major_can_override_interest":True,"prefer_empty_over_filler":True,"minimum_quality":.65,"minimum_scope_relevance":.5},
        "retrieval":{"github_queries":[],"huggingface_queries":[],"youtube_channels":[]},
    }
    try:data=json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return fallback
    if not isinstance(data,dict):return fallback
    for key,value in fallback.items():
        if key not in data or not isinstance(data[key],type(value)):data[key]=value
        elif isinstance(value,dict):
            for child,default in value.items():data[key].setdefault(child,default)
    return data

def _field_value(value,default=.5):
    if isinstance(value,dict):value=value.get("value",default)
    return _clamp(_number(value,default))
def _field_confidence(value,default=.5):return _clamp(_number(value.get("confidence",default),default)) if isinstance(value,dict) else default
def _active_recent(preferences):
    today=datetime.now(timezone.utc).date(); rows=[]
    for name,entry in preferences.get("recent_interests",{}).items():
        try:
            created=datetime.strptime(entry.get("created_at",""),"%Y-%m-%d").date(); expires=int(entry.get("expires_days",30))
            if today>created+timedelta(days=expires):continue
        except Exception:continue
        rows.append((name,[str(x).lower() for x in entry.get("aliases",[])],_clamp(entry.get("weight",.5))))
    return rows

def context_profile(text):
    """Reduce local project context to topic identifiers; never expose paths."""
    preferences=load_preferences(); lower=(text or "").lower(); matched=[]; terms=[]
    for name,entry in preferences.get("interests",{}).items():
        aliases=[str(x).lower() for x in entry.get("aliases",[])]
        if any(alias in lower for alias in aliases):matched.append(name); terms.extend(aliases)
    for name,aliases,_ in _active_recent(preferences):
        if any(alias in lower for alias in aliases):matched.append(name); terms.extend(aliases)
    labels=[preferences.get("interests",{}).get(name,{}).get("label",name) for name in matched[:2]]
    return {"label":" · ".join(labels) if labels else preferences.get("scope",{}).get("label","具身智能前沿"),"terms":list(dict.fromkeys(terms))[:16],"topics":list(dict.fromkeys(matched))[:6]}

def _request_json(url,timeout=20,data=None,headers=None):
    request_headers={"User-Agent":"Codex-Control-Tower/0.3","Accept":"application/json"}; request_headers.update(headers or {})
    return json.loads(urlopen(Request(url,data=data,headers=request_headers),timeout=timeout).read())

def _arxiv(query,limit,sort_by="submittedDate"):
    url="https://export.arxiv.org/api/query?"+urlencode({"search_query":query,"start":0,"max_results":limit,"sortBy":sort_by,"sortOrder":"descending"})
    root=ET.fromstring(urlopen(Request(url,headers={"User-Agent":"Codex-Control-Tower/0.3 (personal research reader)"}),timeout=25).read()); ns={"a":"http://www.w3.org/2005/Atom"}; rows=[]
    for entry in root.findall("a:entry",ns):
        link=next((x.get("href") for x in entry.findall("a:link",ns) if x.get("rel")=="alternate"),entry.findtext("a:id",default="",namespaces=ns)); raw_id=link.rstrip("/").split("/")[-1]; arxiv_id=re.sub(r"v\d+$","",raw_id)
        authors=[x.findtext("a:name",default="",namespaces=ns) for x in entry.findall("a:author",ns)]; categories=[x.get("term","") for x in entry.findall("a:category",ns)]
        rows.append({"kind":"paper","source":"arXiv","title":" ".join(entry.findtext("a:title",default="",namespaces=ns).split()),"abstract":" ".join(entry.findtext("a:summary",default="",namespaces=ns).split()),"published":entry.findtext("a:published",default="",namespaces=ns)[:10],"url":link,"external_id":arxiv_id,"authors":authors,"categories":categories})
    return rows

def arxiv_candidates(context,limit=70):
    # The first lane is deliberately broad; context only adds recall later.
    rows=_arxiv("cat:cs.RO",limit)
    broad='(cat:cs.RO OR cat:cs.CV OR cat:cs.AI OR cat:cs.LG) AND (all:"embodied ai" OR all:"robot learning" OR all:"vision language action" OR all:"vision language navigation" OR all:"robot foundation model" OR all:"world model" OR all:"robot policy")'
    try:rows+=_arxiv(broad,35)
    except Exception:pass
    focused=[term for term in context.get("terms",[]) if len(term)>3][:4]
    if focused:
        query='(cat:cs.RO OR cat:cs.CV OR cat:cs.AI OR cat:cs.LG) AND ('+" OR ".join(f'all:"{term}"' for term in focused)+')'
        try:rows+=_arxiv(query,15,"relevance")
        except Exception:pass
    return dedupe(rows)

def github_candidates(preferences,limit=40):
    rows=[]; queries=preferences.get("retrieval",{}).get("github_queries",[])[:6]; token=_env("GITHUB_TOKEN"); headers={"Accept":"application/vnd.github+json"}
    if token:headers["Authorization"]="Bearer "+token
    for query in queries:
        try:
            url="https://api.github.com/search/repositories?"+urlencode({"q":f"{query} in:name,description,readme archived:false","sort":"stars","order":"desc","per_page":12})
            for repo in _request_json(url,headers=headers).get("items",[]):
                description=repo.get("description") or ""; topics=repo.get("topics") or []
                rows.append({"kind":"repo","source":"GitHub","title":repo.get("full_name") or repo.get("name",""),"abstract":description+(" 主题："+", ".join(topics) if topics else ""),"published":(repo.get("created_at") or "")[:10],"updated":(repo.get("pushed_at") or "")[:10],"url":repo.get("html_url"),"external_id":str(repo.get("id","")),"stars":repo.get("stargazers_count",0) or 0,"forks":repo.get("forks_count",0) or 0,"open_source":True,"owner":((repo.get("owner") or {}).get("login") or ""),"topics":topics})
        except Exception:pass
    rows=dedupe(rows); rows.sort(key=lambda item:(item.get("stars",0),item.get("updated","")),reverse=True); return rows[:limit]

def huggingface_candidates(preferences,limit=32):
    rows=[]; searches=preferences.get("retrieval",{}).get("huggingface_queries",[])[:6]
    for query in searches:
        try:
            url="https://huggingface.co/api/models?"+urlencode({"search":query,"sort":"trendingScore","direction":-1,"limit":12,"full":"true"})
            for model in _request_json(url):
                model_id=model.get("id") or model.get("modelId"); tags=model.get("tags") or []; updated=(model.get("lastModified") or "")[:10]
                description=f"开源模型仓库；任务标签：{', '.join(tags[:14])}。下载 {model.get('downloads',0)}，点赞 {model.get('likes',0)}，趋势分 {model.get('trendingScore',0)}。"
                rows.append({"kind":"model","source":"Hugging Face","title":model_id,"abstract":description,"published":updated,"url":"https://huggingface.co/"+model_id,"external_id":model_id,"downloads":model.get("downloads",0) or 0,"likes":model.get("likes",0) or 0,"trending":model.get("trendingScore",0) or 0,"open_source":True,"tags":tags,"owner":model_id.split("/",1)[0] if model_id else ""})
        except Exception:pass
    rows=dedupe(rows); rows.sort(key=lambda item:(item.get("trending",0),item.get("likes",0),item.get("downloads",0)),reverse=True); return rows[:limit]

def video_candidates(preferences,limit=30):
    channels=preferences.get("retrieval",{}).get("youtube_channels",[]); atom="http://www.w3.org/2005/Atom"; media="http://search.yahoo.com/mrss/"; yt="http://www.youtube.com/xml/schemas/2015"; rows=[]
    for channel in channels:
        source=channel.get("name","官方频道"); channel_id=channel.get("channel_id",""); keywords=[str(x).lower() for x in channel.get("keywords",[])]
        if not channel_id:continue
        try:
            root=ET.fromstring(urlopen(Request("https://www.youtube.com/feeds/videos.xml?channel_id="+channel_id,headers={"User-Agent":"Codex-Control-Tower/0.3"}),timeout=18).read())
            for entry in root.findall(f"{{{atom}}}entry"):
                title=entry.findtext(f"{{{atom}}}title",default=""); desc=entry.findtext(f"{{{media}}}group/{{{media}}}description",default=""); candidate_text=(title+" "+desc).lower()
                if keywords and not any(word in candidate_text for word in keywords):continue
                video_id=entry.findtext(f"{{{yt}}}videoId",default=""); thumbnail=entry.find(f"{{{media}}}group/{{{media}}}thumbnail")
                rows.append({"kind":"video","source":source,"title":title,"abstract":" ".join(desc.split())[:2200],"published":entry.findtext(f"{{{atom}}}published",default="")[:10],"url":"https://www.youtube.com/watch?v="+video_id,"external_id":video_id,"thumbnail":thumbnail.get("url") if thumbnail is not None else "","official":True})
        except Exception:pass
    rows.sort(key=lambda item:item.get("published",""),reverse=True); return rows[:limit]

def enrich_papers(items):
    papers=[item for item in items if item.get("kind")=="paper" and item.get("external_id")][:100]
    if not papers:return
    try:
        payload=json.dumps({"ids":["ARXIV:"+item["external_id"] for item in papers]}).encode(); fields="externalIds,citationCount,influentialCitationCount,publicationDate,openAccessPdf"
        data=_request_json("https://api.semanticscholar.org/graph/v1/paper/batch?"+urlencode({"fields":fields}),timeout=25,data=payload,headers={"Content-Type":"application/json"})
        for item,metadata in zip(papers,data):
            if not metadata:continue
            item["citations"]=metadata.get("citationCount",0) or 0; item["influential_citations"]=metadata.get("influentialCitationCount",0) or 0
            if metadata.get("openAccessPdf"):item["open_source"]=True
    except Exception:pass

def dedupe(items):
    seen=set(); rows=[]
    for item in items:
        key=item.get("url") or re.sub(r"\W+","",item.get("title","").lower())
        if not key or key in seen:continue
        seen.add(key); rows.append(item)
    return rows

def _text(item):
    fields=(item.get("title",""),item.get("abstract","")," ".join(item.get("authors",[]))," ".join(item.get("topics",[]))," ".join(item.get("tags",[])))
    return " ".join(str(value) for value in fields).lower().replace("π","pi")
def _days_old(date):
    try:return max(0,(datetime.now(timezone.utc).date()-datetime.strptime(date,"%Y-%m-%d").date()).days)
    except Exception:return 365
def _reference_matches(item,preferences):
    text=_text(item); matches=[]
    for reference in preferences.get("reference_works",[]):
        aliases=[reference.get("name","")]+reference.get("aliases",[])
        if any(str(alias).lower().replace("π","pi") in text for alias in aliases if alias):matches.append(reference)
    return matches
def _title_reference_names(item,preferences):
    title=(item.get("title") or "").lower().replace("π","pi"); names=set()
    for reference in preferences.get("reference_works",[]):
        aliases=[reference.get("name","")]+reference.get("aliases",[])
        if any(str(alias).lower().replace("π","pi") in title for alias in aliases if alias):names.add(reference.get("name"))
    return names
def _title_tokens(title):
    text=(title or "").lower().replace("π","pi"); tokens=set(re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)?",text)); stop={"a","an","the","for","of","to","and","with","in","on","from","using","robot","robotics","model","learning","ai","github","official","demo"}
    return {token for token in tokens if token not in stop and len(token)>2}

def merge_events(items,preferences):
    """Merge paper/repo/model/video resources that describe one release."""
    groups=[]
    for item in dedupe(items):
        tokens=_title_tokens(item.get("title","")); references={x.get("name") for x in _reference_matches(item,preferences)}; title_references=_title_reference_names(item,preferences); match=None
        for group in groups:
            overlap=len(tokens & group["tokens"]); union=len(tokens | group["tokens"]) or 1; same_title_reference=bool(title_references & group["title_references"])
            if same_title_reference or (overlap>=3 and overlap/union>=.58):match=group; break
        if match is None:groups.append({"items":[item],"tokens":tokens,"references":references,"title_references":title_references})
        else:match["items"].append(item); match["tokens"]|=tokens; match["references"]|=references; match["title_references"]|=title_references
    events=[]; priority={"paper":4,"repo":3,"model":2,"video":1}
    for group in groups:
        resources=[{key:child.get(key) for key in ("kind","source","title","url","thumbnail") if child.get(key)} for child in group["items"]]
        primary=max(group["items"],key=lambda child:(priority.get(child.get("kind"),0),len(child.get("abstract","")))); event=dict(primary); event["resources"]=resources; event["sources"]=list(dict.fromkeys(child.get("source","") for child in group["items"] if child.get("source"))); event["source_count"]=len(event["sources"]); event["has_video"]=any(child.get("kind")=="video" for child in group["items"]); event["video_url"]=next((child.get("url") for child in group["items"] if child.get("kind")=="video"),"")
        descriptions=list(dict.fromkeys(child.get("abstract","") for child in group["items"] if child.get("abstract"))); event["abstract"]=" ".join(descriptions[:3])[:4200]
        for metric in ("stars","forks","downloads","likes","trending","citations","influential_citations","views"):event[metric]=max((_number(child.get(metric)) for child in group["items"]),default=0)
        event["open_source"]=any(child.get("open_source") for child in group["items"]); events.append(event)
    return events

def _topics(item,preferences):
    text=_text(item); matched=[]; labels={}
    for name,entry in preferences.get("interests",{}).items():
        aliases=[str(x).lower() for x in entry.get("aliases",[])]; labels[name]=entry.get("label",name)
        if any(alias in text for alias in aliases):matched.append(name)
    for name,(label,aliases) in OPEN_TOPIC_RULES.items():
        labels[name]=label
        if any(alias in text for alias in aliases) and name not in matched:matched.append(name)
    if not matched and any(word in text for word in ("robot learning","robot policy","embodied ai","foundation model","physical ai","language-conditioned robot")):matched.append("open_embodied"); labels["open_embodied"]="新具身方向"
    return matched,labels
def _scope_relevance(item,topics):
    text=_text(item); configured=any(topic not in OPEN_TOPIC_RULES and topic!="open_embodied" for topic in topics)
    if configured:return _clamp(.76+.05*(len(topics)-1))
    if topics:return _clamp(.66+.04*(len(topics)-1))
    if ("robot" in text or "embodied" in text or "physical ai" in text) and any(word in text for word in ("learn","policy","model","language","agent","reason","foundation","world")):return .60
    if "robot" in text or "robotic" in text:return .30
    return .12
def _source_authority(item):
    source=(item.get("source") or "").lower(); owner=(item.get("owner") or "").lower(); text=_text(item); official_names=("google deepmind","nvidia developer","nvidia research","physical intelligence","boston dynamics","openvla"); trusted_owners=("openvla","nvidia","google-deepmind","physical-intelligence","huggingface","lerobot")
    if item.get("official") or any(name in source for name in official_names):return .94
    if any(owner==name or owner.startswith(name) for name in trusted_owners):return .90
    if any(name in text for name in ("physical intelligence","google deepmind","nvidia","stanford","berkeley","mit csail","carnegie mellon")):return .76
    return {"arxiv":.62,"github":.55,"hugging face":.48}.get(source,.50)
def _engagement(item):
    values=[]
    if item.get("stars") is not None:values.append(_clamp(math.log10(_number(item.get("stars"))+1)/4.3))
    if item.get("downloads") is not None:values.append(_clamp(math.log10(_number(item.get("downloads"))+1)/6.0))
    if item.get("likes") is not None:values.append(_clamp(math.log10(_number(item.get("likes"))+1)/3.0))
    if item.get("citations") is not None:values.append(_clamp(math.log10(_number(item.get("citations"))+1)/3.0))
    if item.get("views") is not None:values.append(_clamp(math.log10(_number(item.get("views"))+1)/6.0))
    if item.get("trending") is not None:values.append(_clamp(_number(item.get("trending"))/10.0))
    return max(values,default=0)
def _momentum(item,previous):
    if not previous:return _engagement(item)*.45
    scores=[]; scales={"stars":120,"downloads":3000,"likes":40,"citations":12,"views":10000}
    for key,scale in scales.items():
        delta=max(0,_number(item.get(key))-_number(previous.get(key)))
        if delta:scores.append(_clamp(math.log1p(delta)/math.log1p(scale)))
    return max(scores,default=0)

def score_event(item,context,preferences,previous_heat=None,was_read=False):
    topics,labels=_topics(item,preferences); relevance=_scope_relevance(item,topics); authority=_source_authority(item); engagement=_engagement(item); momentum=_momentum(item,previous_heat); freshness=_clamp(1-_days_old(item.get("published",""))/120); source_diversity=_clamp((item.get("source_count",1)-1)/3); references=_reference_matches(item,preferences)
    evidence=.90 if item.get("kind")=="paper" else (.78 if item.get("official") or item.get("has_video") else .45); completeness=_clamp(len(item.get("abstract",""))/900); quality=_clamp(.30+.25*authority+.20*engagement+.15*evidence+.10*completeness+(.05 if item.get("open_source") else 0))
    configured=preferences.get("interests",{}); interest_values=[]; knowledge_values=[]
    for topic in topics:
        entry=configured.get(topic)
        if not entry:continue
        interest_values.append(_field_value(entry.get("interest"),.5)); knowledge=entry.get("knowledge",{}); confidence=_field_confidence(knowledge,.5); knowledge_values.append(_field_value(knowledge,.5)*confidence+.5*(1-confidence))
    interest=max(interest_values,default=.22); knowledge=max(knowledge_values,default=.15)
    for name,aliases,weight in _active_recent(preferences):
        if any(alias in _text(item) for alias in aliases):interest=max(interest,weight); topics.append(name); labels[name]=name
    if set(context.get("topics",[])) & set(topics):interest=_clamp(interest+.08)
    novelty=_clamp(1-knowledge); heat=_clamp(.30*engagement+.25*momentum+.25*authority+.10*source_diversity+.10*freshness)
    if authority>=.88 and freshness>=.82:heat=max(heat,.75)
    if references:heat=max(heat,min(.78,.62+.08*max(_number(x.get("weight"),.5) for x in references)))
    overall=quality*(.30*relevance+.25*interest+.20*novelty+.25*heat)
    channels={
        "core":quality*(.45*interest+.30*relevance+.15*(1-abs(knowledge-.72))+.10*heat),
        "adjacent":quality*(.40*relevance+.25*(1-abs(interest-.55))+.20*novelty+.15*heat),
        "major":quality*(.60*heat+.25*relevance+.15*authority),
        "emerging":quality*(.32*momentum+.22*freshness+.20*novelty+.14*source_diversity+.12*relevance),
        "serendipity":quality*(.35*novelty+.25*relevance+.25*quality+.15*(1-interest)),
    }
    if heat<.62:channels["major"]*=.48
    if momentum<.38 and not (freshness>.90 and source_diversity>.2):channels["emerging"]*=.55
    if was_read:overall*=.62
    primary=max(channels,key=channels.get)
    if references and authority>=.88 and heat>=.68:primary="major"
    topic_labels=[labels.get(topic,topic) for topic in list(dict.fromkeys(topics))[:3]]; signals=[]
    if authority>=.88:signals.append("官方/重点团队")
    if item.get("source_count",1)>1:signals.append(f"{item['source_count']} 个来源")
    if item.get("stars"):signals.append(f"GitHub {int(item['stars'])}★")
    if item.get("downloads"):signals.append(f"HF {int(item['downloads'])} 下载")
    if item.get("citations"):signals.append(f"{int(item['citations'])} 引用")
    if momentum>.38:signals.append("热度上升")
    if not signals:signals.append("通过质量门槛")
    item.update({"topics":list(dict.fromkeys(topics)),"topic_labels":topic_labels,"references":[x.get("name") for x in references],"quality":round(quality,3),"relevance":round(relevance,3),"interest":round(interest,3),"knowledge":round(knowledge,3),"novelty":round(novelty,3),"heat":round(heat,3),"momentum":round(momentum,3),"channel_scores":{key:round(value,3) for key,value in channels.items()},"primary_channel":primary,"channel_label":CHANNEL_LABELS[primary],"score":round(overall*100,1),"signals":signals[:4],"recommend_reason":f"{CHANNEL_LABELS[primary]} · "+(" / ".join(topic_labels) if topic_labels else "未知新方向"),"difficulty":"进阶" if knowledge>.72 else ("入门" if knowledge<.35 else "中等")})
    return item

def _soft_allocate(candidates,count,preferences):
    mix=preferences.get("feed_mix",{}); presentation=preferences.get("presentation",{}); selected=[]; channel_counts={key:0 for key in CHANNEL_LABELS}; source_counts={}; topic_counts={}; video_count=0; minimum_videos=max(0,int(presentation.get("minimum_qualified_videos",0))); video_preference=_clamp(presentation.get("video_preference",.5)); pool=list(candidates)
    while pool and len(selected)<count:
        remaining_slots=count-len(selected); videos_needed=max(0,minimum_videos-video_count); best=None; best_rank=-1; best_channel="core"
        for item in pool:
            adjusted={}
            for channel,value in item.get("channel_scores",{}).items():
                target=max(.01,_number(mix.get(channel,.1))*count); deficit=max(0,target-channel_counts.get(channel,0))/target; adjusted[channel]=value*(1+.35*deficit)
            channel=max(adjusted,key=adjusted.get); rank=.55*(item.get("score",0)/100)+.45*adjusted[channel]; has_video=item.get("has_video") or item.get("kind")=="video"
            if has_video:rank+=.08*video_preference
            if has_video and videos_needed and remaining_slots<=videos_needed:rank+=.22
            rank-=.07*source_counts.get(item.get("source",""),0); first_topic=(item.get("topics") or [""])[0]; rank-=.065*topic_counts.get(first_topic,0)
            if item.get("read"):rank-=.18
            if rank>best_rank:best=item; best_rank=rank; best_channel=channel
        if best is None:break
        best["allocation_channel"]=best_channel; selected.append(best); pool.remove(best); channel_counts[best_channel]+=1; source_counts[best.get("source","")]=source_counts.get(best.get("source",""),0)+1; first_topic=(best.get("topics") or [""])[0]; topic_counts[first_topic]=topic_counts.get(first_topic,0)+1
        if best.get("has_video") or best.get("kind")=="video":video_count+=1
    return selected

class Store:
    def __init__(self,path=DB):self.path=Path(path); self.init()
    def connect(self):
        con=sqlite3.connect(self.path,timeout=5); con.execute("PRAGMA journal_mode=WAL"); return con
    @contextmanager
    def session(self):
        con=self.connect()
        try:
            with con:yield con
        finally:con.close()
    def _column(self,con,table,name,declaration):
        columns={row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        if name not in columns:con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
    def init(self):
        with self.session() as con:
            con.execute("CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY,url TEXT UNIQUE,kind TEXT,source TEXT,title TEXT,published TEXT,score REAL,payload TEXT,first_seen INTEGER,last_seen INTEGER,read_at INTEGER DEFAULT 0,saved INTEGER DEFAULT 0)")
            self._column(con,"items","dismissed","INTEGER DEFAULT 0"); self._column(con,"items","feedback","TEXT DEFAULT ''"); self._column(con,"items","engine_version","INTEGER DEFAULT 1")
            con.execute("CREATE INDEX IF NOT EXISTS idx_items_last ON items(last_seen DESC)"); con.execute("CREATE TABLE IF NOT EXISTS feedback_events (id INTEGER PRIMARY KEY AUTOINCREMENT,url TEXT,action TEXT,created_at INTEGER)"); con.execute("CREATE TABLE IF NOT EXISTS heat_snapshots (url TEXT,bucket INTEGER,stars REAL DEFAULT 0,downloads REAL DEFAULT 0,likes REAL DEFAULT 0,citations REAL DEFAULT 0,views REAL DEFAULT 0,PRIMARY KEY(url,bucket))"); con.execute("CREATE INDEX IF NOT EXISTS idx_heat_url ON heat_snapshots(url,bucket DESC)")
    def known(self):
        with self.session() as con:return {row[0]:{"read":bool(row[1]),"dismissed":bool(row[2]),"feedback":row[3] or ""} for row in con.execute("SELECT url,read_at,dismissed,feedback FROM items")}
    def previous_heat(self,url):
        with self.session() as con:row=con.execute("SELECT stars,downloads,likes,citations,views FROM heat_snapshots WHERE url=? ORDER BY bucket DESC LIMIT 1",(url,)).fetchone()
        return dict(zip(("stars","downloads","likes","citations","views"),row)) if row else None
    def snapshot_heat(self,items):
        bucket=int(time.time())//21600*21600
        with self.session() as con:
            for item in items:
                if item.get("url"):con.execute("INSERT OR REPLACE INTO heat_snapshots(url,bucket,stars,downloads,likes,citations,views) VALUES(?,?,?,?,?,?,?)",(item["url"],bucket,_number(item.get("stars")),_number(item.get("downloads")),_number(item.get("likes")),_number(item.get("citations")),_number(item.get("views"))))
    def upsert(self,items):
        now=int(time.time())
        with self.session() as con:
            for item in items:
                ident=hashlib.sha1((item.get("url") or item.get("title","")).encode()).hexdigest(); payload=json.dumps(item,ensure_ascii=False)
                con.execute("INSERT INTO items(id,url,kind,source,title,published,score,payload,first_seen,last_seen,engine_version) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET kind=excluded.kind,source=excluded.source,title=excluded.title,published=excluded.published,score=excluded.score,payload=excluded.payload,last_seen=excluded.last_seen,engine_version=excluded.engine_version",(ident,item.get("url"),item.get("kind"),item.get("source"),item.get("title"),item.get("published"),item.get("score",0),payload,now,now,ENGINE_VERSION))
        self.cleanup()
    def recent(self,limit=12):
        with self.session() as con:rows=con.execute("SELECT payload,read_at,saved,dismissed,engine_version FROM items WHERE dismissed=0 ORDER BY last_seen DESC,score DESC LIMIT ?",(max(limit*5,60),)).fetchall()
        result=[]
        for payload,read_at,saved,dismissed,engine_version in rows:
            try:item=json.loads(payload)
            except Exception:continue
            if engine_version<ENGINE_VERSION and not saved:continue
            item["read"]=bool(read_at); item["saved"]=bool(saved); item["dismissed"]=bool(dismissed); result.append(item)
            if len(result)>=limit:break
        return result
    def mark_read(self,url):
        with self.session() as con:con.execute("UPDATE items SET read_at=? WHERE url=?",(int(time.time()),url))
    def toggle_saved(self,url):
        with self.session() as con:
            row=con.execute("SELECT saved FROM items WHERE url=?",(url,)).fetchone(); value=0 if row and row[0] else 1; con.execute("UPDATE items SET saved=? WHERE url=?",(value,url)); return bool(value)
    def feedback(self,url,action):
        dismissed=1 if action=="dismissed" else 0
        with self.session() as con:con.execute("UPDATE items SET feedback=?,dismissed=? WHERE url=?",(action,dismissed,url)); con.execute("INSERT INTO feedback_events(url,action,created_at) VALUES(?,?,?)",(url,action,int(time.time())))
    def cleanup(self,max_items=1000,max_age_days=60):
        cutoff=int(time.time())-max_age_days*86400; heat_cutoff=int(time.time())-180*86400
        with self.session() as con:
            con.execute("DELETE FROM items WHERE saved=0 AND last_seen<?",(cutoff,)); con.execute("DELETE FROM heat_snapshots WHERE bucket<?",(heat_cutoff,)); count=con.execute("SELECT count(*) FROM items").fetchone()[0]
            if count>max_items:con.execute("DELETE FROM items WHERE id IN (SELECT id FROM items WHERE saved=0 ORDER BY last_seen ASC,score ASC LIMIT ?)",(count-max_items,))
    def stats(self):
        with self.session() as con:count,saved=con.execute("SELECT count(*),sum(saved) FROM items WHERE dismissed=0").fetchone()
        size=sum(path.stat().st_size for path in self.path.parent.glob(self.path.name+"*") if path.is_file()); return {"count":count,"saved":saved or 0,"bytes":size,"limit":1000}

def _digest(items,context,preferences):
    key=_env("DEEPSEEK_API_KEY")
    if not key:raise RuntimeError("未配置 DeepSeek API Key")
    compact=[]
    for index,item in enumerate(items):compact.append({"index":index,"channel":item.get("primary_channel"),"source":item.get("sources") or [item.get("source")],"title":item.get("title"),"description":item.get("abstract","")[:2200],"published":item.get("published"),"signals":item.get("signals"),"topics":item.get("topic_labels"),"reference_matches":item.get("references"),"user_knowledge":item.get("knowledge"),"resources":item.get("resources",[])})
    anchors=[entry.get("name") for entry in preferences.get("reference_works",[])[:10]]
    prompt=f"""你是具身智能研究情报编辑。候选已由宽召回和真实质量信号选出，你不得因未知术语或不像用户旧兴趣而贬低它。
用户当前项目上下文只是弱信号：{context.get('label')}。已知参照坐标（不是白名单）：{anchors}。
输出严格 JSON 数组，每项包含 index、summary、delta、why、seconds、tags、difficulty。summary 不超过 48 字，delta 不超过 60 字，why 不超过 48 字。seconds 取 20/30/45/60，tags 最多 3 个，difficulty 取入门/中等/进阶。必须忠于输入证据，不得编造热度、实验或开源情况。
候选：
"""+json.dumps(compact,ensure_ascii=False)
    payload={"model":"deepseek-v4-flash","messages":[{"role":"system","content":"只输出合法 JSON，用简体中文，忠于证据。"},{"role":"user","content":prompt}],"thinking":{"type":"disabled"},"temperature":.15,"max_tokens":4000,"stream":False}
    response=json.loads(urlopen(Request("https://api.deepseek.com/chat/completions",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Authorization":"Bearer "+key}),timeout=55).read()); text=response["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):text=text.split("\n",1)[1].rsplit("```",1)[0]
    return {int(item["index"]):item for item in json.loads(text)}

def build_feed(count,context):
    preferences=load_preferences(); store=Store(); known=store.known(); candidates=[]; errors=[]
    for loader in (lambda:arxiv_candidates(context),lambda:github_candidates(preferences),lambda:huggingface_candidates(preferences),lambda:video_candidates(preferences)):
        try:candidates.extend(loader())
        except Exception as exc:errors.append(str(exc))
    enrich_papers(candidates); events=merge_events(candidates,preferences); scored=[]; discovery=preferences.get("discovery",{}); quality_gate=_number(discovery.get("minimum_quality"),.65); relevance_gate=_number(discovery.get("minimum_scope_relevance"),.5)
    for event in events:
        state=known.get(event.get("url"),{})
        if state.get("dismissed"):continue
        hard_exclude=[str(value).lower() for value in preferences.get("scope",{}).get("hard_exclude",[])]; text=_text(event)
        if any(value and value in text for value in hard_exclude):continue
        score_event(event,context,preferences,store.previous_heat(event.get("url")),state.get("read",False)); event["read"]=state.get("read",False)
        if event["quality"]>=quality_gate and event["relevance"]>=relevance_gate:scored.append(event)
    store.snapshot_heat(events); scored.sort(key=lambda item:item.get("score",0),reverse=True); selected=_soft_allocate(scored,count,preferences)
    try:digests=_digest(selected,context,preferences)
    except Exception as exc:digests={}; errors.append("AI摘要："+str(exc))
    for index,item in enumerate(selected):
        digest=digests.get(index,{}); fallback=(item.get("abstract") or "暂无摘要").strip(); item.update({"summary":digest.get("summary") or fallback[:150]+("…" if len(fallback)>150 else ""),"delta":digest.get("delta") or "需要打开原文确认相对已有工作的具体增量","why":digest.get("why") or " · ".join(item.get("signals",[])),"seconds":digest.get("seconds",45),"tags":digest.get("tags") or item.get("topic_labels",[])[:3],"difficulty":digest.get("difficulty") or item.get("difficulty","中等"),"engine_version":ENGINE_VERSION})
    store.upsert(selected); state={item["url"]:item for item in store.recent(1000)}
    for item in selected:
        local=state.get(item.get("url"),{}); item["read"]=local.get("read",False); item["saved"]=local.get("saved",False)
    return selected,"；".join(errors),store.stats()
