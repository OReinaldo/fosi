"""FOSI ESPN collector: resilient public soccer acquisition with all-soccer fallbacks."""
import json,urllib.parse
from datetime import datetime,timezone
from pathlib import Path
CONFIG=Path("config/selected-scout.json");ROOT_BASE=Path("data/scouting")
SITE_BASES=["https://site.api.espn.com/apis/site/v2/sports/soccer","https://site.web.api.espn.com/apis/site/v2/sports/soccer"]
V2_BASES=["https://site.api.espn.com/apis/v2/sports/soccer","https://site.web.api.espn.com/apis/v2/sports/soccer"]
def get(path,bases=SITE_BASES):
    last=None
    for base in bases:
        try:
            import urllib.request
            req=urllib.request.Request(base+path,headers={"User-Agent":"Mozilla/5.0 FOSI/2.0","Accept":"application/json","Referer":"https://www.espn.com/"})
            with urllib.request.urlopen(req,timeout=30) as r:return json.load(r),base
        except Exception as e:last=e
    raise last
def save(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"));root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];raw=root/"raw"/"espn"
    st={"source":"espn","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"layers":{},"records":{},"errors":[],"routes_attempted":[]}
    league=str((cfg.get("provider_competition_ids") or {}).get("espn") or "pol.1");tid=str((cfg.get("provider_ids") or {}).get("espn") or "")
    schedule_events={}
    if tid:
        # ESPN's all-soccer team schedule is more reliable than competition-specific routes.
        for page in range(10):
            paths=[f"/all/teams/{urllib.parse.quote(tid)}/schedule?limit=100&offset={page*100}",f"/all/teams/{urllib.parse.quote(tid)}/schedule?limit=100&offset={page*100}&fixture=true"]
            got=False
            for path in paths:
                try:
                    payload,base=get(path);st["routes_attempted"].append({"path":path,"status":"success","base":base});save(raw/"schedule"/f"page-{page}.json",payload)
                    for e in payload.get("events",[]):
                        if e.get("id"):schedule_events[str(e["id"])]=e
                    got=True
                    if not payload.get("events") or not payload.get("pageIndex") and page>0:break
                    break
                except Exception as e:st["routes_attempted"].append({"path":path,"status":"error","error":str(e)})
            if not got:break
        events=list(schedule_events.values());save(raw/"schedule.json",{"events":events});st["layers"]["matches"]="available" if events else "pending";st["records"]["schedule_events"]=len(events)
    for name,path in [("team.json",f"/all/teams/{urllib.parse.quote(tid)}"),("roster.json",f"/all/teams/{urllib.parse.quote(tid)}/roster"),("injuries.json",f"/all/teams/{urllib.parse.quote(tid)}/injuries"),("record.json",f"/all/teams/{urllib.parse.quote(tid)}/record")]:
        if not tid:continue
        try:payload,_=get(path);save(raw/name,payload);key=name[:-5];st["layers"]["team" if key=="team" else key]="available";st["records"][key]=1
        except Exception as e:st["errors"].append({"layer":name[:-5],"error":str(e)})
    for name,path,bases in [("teams.json",f"/{league}/teams",SITE_BASES),("standings.json",f"/{league}/standings",V2_BASES),("news.json",f"/{league}/news",SITE_BASES)]:
        try:payload,_=get(path,bases);save(raw/name,payload);key=name[:-5];st["layers"]["competition" if key=="teams" else key]="available";st["records"][key]=len(payload.get("articles",[])) if key=="news" else 1
        except Exception as e:st["errors"].append({"layer":name[:-5],"error":str(e)})
    summaries=0
    for event in events:
        eid=str(event.get("id") or "");dest=raw/"matches"/eid/"summary.json"
        if not eid:continue
        if dest.exists():summaries+=1;continue
        done=False
        for path in [f"/{league}/summary?event={urllib.parse.quote(eid)}",f"/all/summary?event={urllib.parse.quote(eid)}"]:
            try:payload,_=get(path);save(dest,payload);summaries+=1;done=True;break
            except Exception:pass
        if not done:st["errors"].append({"match_id":eid,"layer":"summary","error":"all summary routes failed"})
    save(raw/"events.json",{"events":events});st["records"]["match_summaries"]=summaries;st["layers"]["events"]="available" if summaries else st["layers"].get("matches","pending");st["layers"]["stats"]="available" if summaries else "pending";st["status"]="success" if not st["errors"] else ("partial" if st["records"] else "error");save(root/"source-status-espn.json",st)
if __name__=="__main__":main()
