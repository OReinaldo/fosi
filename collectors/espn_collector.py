"""FOSI ESPN collector: public site + core + CDN match acquisition, raw-first.

The collector uses several public schedule routes because ESPN's team schedule
endpoint can be incomplete for football competitions. League scoreboard is used
as an observed fallback and then filtered to the selected team.
"""
import json, urllib.parse, time
from datetime import datetime, timezone
from pathlib import Path
CONFIG=Path("config/selected-scout.json"); ROOT_BASE=Path("data/scouting")
SITE_BASES=["https://site.api.espn.com/apis/site/v2/sports/soccer","https://site.web.api.espn.com/apis/site/v2/sports/soccer"]
V2_BASES=["https://site.api.espn.com/apis/v2/sports/soccer","https://site.web.api.espn.com/apis/v2/sports/soccer"]
CORE_BASES=["https://sports.core.api.espn.com/v2/sports/soccer"]
CDN_BASE="https://cdn.espn.com"

def get(path,bases=SITE_BASES):
    last=None
    for base in bases:
        try:
            import urllib.request
            req=urllib.request.Request(base+path,headers={"User-Agent":"Mozilla/5.0 FOSI/2.2","Accept":"application/json","Referer":"https://www.espn.com/"})
            with urllib.request.urlopen(req,timeout=30) as r:return json.load(r),base
        except Exception as e:last=e
    raise last

def save(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

def try_get(path,bases):
    try:return get(path,bases)
    except Exception:return None,None

def merge_events(dst, payload):
    if not isinstance(payload,dict): return
    for e in payload.get("events",[]) or []:
        if e.get("id"): dst[str(e["id"])]=e

def event_has_team(event, team_id):
    for c in (event.get("competitions") or []):
        for comp in (c.get("competitors") or []):
            if str(comp.get("id") or comp.get("team",{}).get("id") or "")==str(team_id): return True
    return False

def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8")); root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"]; raw=root/"raw"/"espn"
    st={"source":"espn","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"layers":{},"records":{},"errors":[],"routes_attempted":[]}
    league=str((cfg.get("provider_competition_ids") or {}).get("espn") or "pol.1"); tid=str((cfg.get("provider_ids") or {}).get("espn") or "")
    schedule_events={}
    if tid:
        routes=[]
        for page in range(5): routes.append(f"/all/teams/{urllib.parse.quote(tid)}/schedule?limit=100&offset={page*100}")
        for year in sorted({str(cfg.get("season", "2026/2027"))[:4],str(int(str(cfg.get("season", "2026/2027"))[:4])-1)}):
            routes.append(f"/all/teams/{urllib.parse.quote(tid)}/schedule?limit=100&dates={year}")
        for path in routes:
            payload,base=try_get(path,SITE_BASES)
            if payload is not None:
                merge_events(schedule_events,payload); st["routes_attempted"].append({"path":path,"status":"success","base":base})
            else: st["routes_attempted"].append({"path":path,"status":"unavailable"})
        # Public league scoreboard fallback: this is often richer than the team feed.
        for dates in ("2026","20260701-20270630"):
            path=f"/{league}/scoreboard?limit=100&dates={dates}"
            payload,base=try_get(path,SITE_BASES)
            if payload is not None:
                before=len(schedule_events)
                for e in payload.get("events",[]) or []:
                    if event_has_team(e,tid): schedule_events[str(e["id"])] = e
                st["routes_attempted"].append({"path":path,"status":"success","base":base,"team_events_added":len(schedule_events)-before})
            else: st["routes_attempted"].append({"path":path,"status":"unavailable"})
        events=list(schedule_events.values()); save(raw/"schedule.json",{"events":events}); st["layers"]["matches"]="available" if events else "pending"; st["records"]["schedule_events"]=len(events)
    else: events=[]
    for name,path,bases in [("team.json",f"/all/teams/{urllib.parse.quote(tid)}",SITE_BASES),("roster.json",f"/all/teams/{urllib.parse.quote(tid)}/roster",SITE_BASES),("injuries.json",f"/all/teams/{urllib.parse.quote(tid)}/injuries",SITE_BASES),("record.json",f"/all/teams/{urllib.parse.quote(tid)}/record",SITE_BASES),("statistics.json",f"/all/teams/{urllib.parse.quote(tid)}/statistics",SITE_BASES),("transactions.json",f"/all/teams/{urllib.parse.quote(tid)}/transactions",SITE_BASES)]:
        if not tid: continue
        payload,_=try_get(path,bases)
        if payload is not None:
            save(raw/name,payload); key=name[:-5]; st["layers"]["team" if key=="team" else key]="available"; st["records"][key]=1
    for name,path,bases in [("teams.json",f"/{league}/teams",SITE_BASES),("standings.json",f"/{league}/standings",V2_BASES),("news.json",f"/{league}/news",SITE_BASES)]:
        payload,_=try_get(path,bases)
        if payload is not None:
            save(raw/name,payload); key=name[:-5]; st["layers"]["competition" if key=="teams" else key]="available"; st["records"][key]=len(payload.get("articles",[])) if key=="news" else 1
    summaries=0; core_counts={"event":0,"competition":0,"plays":0,"situation":0,"probabilities":0,"predictor":0,"competitor_stats":0,"competitor_roster":0,"cdn_game":0}
    for event in events:
        eid=str(event.get("id") or "");
        if not eid: continue
        match_dir=raw/"matches"/eid; summary=match_dir/"summary.json"; sp=None
        if summary.exists():
            try: sp=json.loads(summary.read_text(encoding="utf-8")); summaries+=1
            except Exception: sp=None
        if sp is None:
            for path in [f"/{league}/summary?event={urllib.parse.quote(eid)}",f"/all/summary?event={urllib.parse.quote(eid)}"]:
                payload,_=try_get(path,SITE_BASES)
                if payload is not None: save(summary,payload); sp=payload; summaries+=1; break
        core_event_path=f"/leagues/{league}/events/{eid}"; ce,_=try_get(core_event_path,CORE_BASES)
        if ce is not None: save(match_dir/"core-event.json",ce); core_counts["event"]+=1
        comp_id=eid
        if isinstance(sp,dict) and sp.get("competitions"):
            comp_id=str((sp["competitions"][0] or {}).get("id") or eid)
        for kind,path in [("competition",f"/leagues/{league}/events/{eid}/competitions/{comp_id}"),("plays",f"/leagues/{league}/events/{eid}/competitions/{comp_id}/plays?limit=400"),("situation",f"/leagues/{league}/events/{eid}/competitions/{comp_id}/situation"),("probabilities",f"/leagues/{league}/events/{eid}/competitions/{comp_id}/probabilities?limit=400"),("predictor",f"/leagues/{league}/events/{eid}/competitions/{comp_id}/predictor")]:
            dest=match_dir/("core-"+kind+".json")
            if dest.exists(): core_counts[kind]+=1; continue
            payload,_=try_get(path,CORE_BASES)
            if payload is not None: save(dest,payload); core_counts[kind]+=1
            time.sleep(.03)
        comp_file=match_dir/"core-competition.json"; comp_payload=None
        if comp_file.exists():
            try: comp_payload=json.loads(comp_file.read_text(encoding="utf-8"))
            except Exception: pass
        competitors=(comp_payload or {}).get("competitors",[]) or ((sp or {}).get("competitors",[]) if isinstance(sp,dict) else [])
        for c in competitors:
            cid=str((c or {}).get("id") or (c or {}).get("team",{}).get("id") or "")
            if not cid: continue
            for kind,suffix in [("competitor-stats","statistics"),("competitor-roster","roster")]:
                dest=match_dir/(kind+"-"+cid+".json")
                if dest.exists(): core_counts[kind]+=1; continue
                payload,_=try_get(f"/leagues/{league}/events/{eid}/competitions/{comp_id}/competitors/{cid}/{suffix}",CORE_BASES)
                if payload is not None: save(dest,payload); core_counts[kind]+=1
        cdn=match_dir/"cdn-game.json"
        if not cdn.exists():
            payload,_=try_get(f"/core/soccer/game?xhr=1&gameId={urllib.parse.quote(eid)}&league={urllib.parse.quote(league)}",[CDN_BASE])
            if payload is not None: save(cdn,payload); core_counts["cdn_game"]+=1
    save(raw/"events.json",{"events":events}); st["records"]["match_summaries"]=summaries; st["records"].update(core_counts)
    st["layers"]["events"]="available" if summaries or core_counts["plays"] else st["layers"].get("matches","pending")
    st["layers"]["stats"]="available" if core_counts["competitor_stats"] or st["records"].get("statistics") else "partial"
    st["layers"]["play_by_play"]="available" if core_counts["plays"] else "partial"; st["layers"]["probabilities"]="available" if core_counts["probabilities"] else "partial"; st["layers"]["cdn"]="available" if core_counts["cdn_game"] else "partial"
    st["status"]="success" if not st["errors"] else "partial"; save(root/"source-status-espn.json",st)

if __name__=="__main__": main()
