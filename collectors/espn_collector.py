"""FOSI ESPN collector: public site + core + CDN match acquisition, raw-first."""
import json,urllib.parse,time
from datetime import datetime,timezone
from pathlib import Path
CONFIG=Path("config/selected-scout.json");ROOT_BASE=Path("data/scouting")
SITE_BASES=["https://site.api.espn.com/apis/site/v2/sports/soccer","https://site.web.api.espn.com/apis/site/v2/sports/soccer"]
V2_BASES=["https://site.api.espn.com/apis/v2/sports/soccer","https://site.web.api.espn.com/apis/v2/sports/soccer"]
CORE_BASES=["https://sports.core.api.espn.com/v2/sports/soccer"]
CDN_BASE="https://cdn.espn.com/core/soccer"

def get(path,bases=SITE_BASES):
    last=None
    for base in bases:
        try:
            import urllib.request
            req=urllib.request.Request(base+path,headers={"User-Agent":"Mozilla/5.0 FOSI/2.1","Accept":"application/json","Referer":"https://www.espn.com/"})
            with urllib.request.urlopen(req,timeout=30) as r:return json.load(r),base
        except Exception as e:last=e
    raise last

def save(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

def try_get(path,bases):
    try:return get(path,bases)
    except Exception:return None,None

def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"));root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];raw=root/"raw"/"espn"
    st={"source":"espn","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"layers":{},"records":{},"errors":[],"routes_attempted":[]}
    league=str((cfg.get("provider_competition_ids") or {}).get("espn") or "pol.1");tid=str((cfg.get("provider_ids") or {}).get("espn") or "")
    schedule_events={}
    if tid:
        for page in range(10):
            path=f"/all/teams/{urllib.parse.quote(tid)}/schedule?limit=100&offset={page*100}"
            try:
                payload,base=get(path);st["routes_attempted"].append({"path":path,"status":"success","base":base});save(raw/"schedule"/f"page-{page}.json",payload)
                batch=payload.get("events",[])
                for e in batch:
                    if e.get("id"):schedule_events[str(e["id"])]=e
                if not batch or len(batch)<100:break
            except Exception as e:
                st["routes_attempted"].append({"path":path,"status":"error","error":str(e)});break
        events=list(schedule_events.values());save(raw/"schedule.json",{"events":events});st["layers"]["matches"]="available" if events else "pending";st["records"]["schedule_events"]=len(events)
    else:events=[]
    for name,path,bases in [("team.json",f"/all/teams/{urllib.parse.quote(tid)}",SITE_BASES),("roster.json",f"/all/teams/{urllib.parse.quote(tid)}/roster",SITE_BASES),("injuries.json",f"/all/teams/{urllib.parse.quote(tid)}/injuries",SITE_BASES),("record.json",f"/all/teams/{urllib.parse.quote(tid)}/record",SITE_BASES)]:
        if not tid:continue
        payload,_=try_get(path,bases)
        if payload is not None:
            save(raw/name,payload);key=name[:-5];st["layers"]["team" if key=="team" else key]="available";st["records"][key]=1
    for name,path,bases in [("teams.json",f"/{league}/teams",SITE_BASES),("standings.json",f"/{league}/standings",V2_BASES),("news.json",f"/{league}/news",SITE_BASES)]:
        payload,_=try_get(path,bases)
        if payload is not None:
            save(raw/name,payload);key=name[:-5];st["layers"]["competition" if key=="teams" else key]="available";st["records"][key]=len(payload.get("articles",[])) if key=="news" else 1
    summaries=0;core_counts={"event":0,"competition":0,"plays":0,"situation":0,"probabilities":0,"predictor":0,"competitor_stats":0,"competitor_roster":0,"cdn_game":0}
    for event in events:
        eid=str(event.get("id") or "")
        if not eid:continue
        match_dir=raw/"matches"/eid
        summary=match_dir/"summary.json"
        if summary.exists():
            try:sp=json.loads(summary.read_text(encoding="utf-8"));summaries+=1
            except Exception:sp={}
        else:
            sp=None
            for path in [f"/{league}/summary?event={urllib.parse.quote(eid)}",f"/all/summary?event={urllib.parse.quote(eid)}"]:
                payload,_=try_get(path,SITE_BASES)
                if payload is not None:save(summary,payload);sp=payload;summaries+=1;break
        # Core event and competition IDs are linked from the public event model where possible.
        core_event_path=f"/leagues/{league}/events/{eid}"
        ce,_=try_get(core_event_path,CORE_BASES)
        if ce is not None:save(match_dir/"core-event.json",ce);core_counts["event"]+=1
        comp_id=eid
        if isinstance(sp,dict):
            comps=sp.get("competitions") or []
            if comps and isinstance(comps[0],dict):comp_id=str(comps[0].get("id") or eid)
        for kind,path in [("competition",f"/leagues/{league}/events/{eid}/competitions/{comp_id}"),("plays",f"/leagues/{league}/events/{eid}/competitions/{comp_id}/plays?limit=400"),("situation",f"/leagues/{league}/events/{eid}/competitions/{comp_id}/situation"),("probabilities",f"/leagues/{league}/events/{eid}/competitions/{comp_id}/probabilities?limit=400"),("predictor",f"/leagues/{league}/events/{eid}/competitions/{comp_id}/predictor")]:
            dest=match_dir/("core-"+kind+".json")
            if dest.exists():core_counts[kind]+=1;continue
            payload,_=try_get(path,CORE_BASES)
            if payload is not None:save(dest,payload);core_counts[kind]+=1
            time.sleep(.03)
        # Resolve competitor-level stats and event roster from the competition model.
        comp_file=match_dir/"core-competition.json"
        comp_payload=None
        if comp_file.exists():
            try:comp_payload=json.loads(comp_file.read_text(encoding="utf-8"))
            except Exception:comp_payload=None
        competitors=(comp_payload or {}).get("competitors",[])
        if not competitors and isinstance(sp,dict):competitors=sp.get("competitors",[])
        for c in competitors:
            cid=str((c or {}).get("id") or (c or {}).get("team",{}).get("id") or "")
            if not cid:continue
            for kind,suffix in [("competitor-stats","statistics"),("competitor-roster","roster")]:
                dest=match_dir/(kind+"-"+cid+".json")
                if dest.exists():core_counts[kind]+=1;continue
                payload,_=try_get(f"/leagues/{league}/events/{eid}/competitions/{comp_id}/competitors/{cid}/{suffix}",CORE_BASES)
                if payload is not None:save(dest,payload);core_counts[kind]+=1
        # ESPN CDN game package is a high-value aggregate fallback: boxscore + plays + probabilities.
        cdn=match_dir/"cdn-game.json"
        if not cdn.exists():
            payload,_=try_get(f"/core/soccer/game?xhr=1&gameId={urllib.parse.quote(eid)}&league={urllib.parse.quote(league)}",["https://cdn.espn.com"])
            if payload is not None:save(cdn,payload);core_counts["cdn_game"]+=1
    save(raw/"events.json",{"events":events});st["records"]["match_summaries"]=summaries;st["records"].update(core_counts);st["layers"]["events"]="available" if summaries or core_counts["plays"] else st["layers"].get("matches","pending");st["layers"]["stats"]="available" if core_counts["competitor_stats"] or summaries else "partial";st["layers"]["play_by_play"]="available" if core_counts["plays"] else "partial";st["layers"]["probabilities"]="available" if core_counts["probabilities"] else "partial";st["layers"]["cdn"]="available" if core_counts["cdn_game"] else "partial";st["status"]="success" if not st["errors"] else ("partial" if st["records"] else "error");save(root/"source-status-espn.json",st)
if __name__=="__main__":main()
