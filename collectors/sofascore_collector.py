"""SofaScore acquisition with mirror fallback, season backfill and raw preservation."""
import json,time,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
BASES=["https://api.sofascore.com/api/v1","https://www.sofascore.app/api/v1","https://www.sofascore.com/api/v1"]
CONFIG=Path("config/selected-scout.json");ROOT_BASE=Path("data/scouting")
def get_json(path):
    last=None
    for base in BASES:
        try:
            req=urllib.request.Request(base+path,headers={"User-Agent":"Mozilla/5.0 FOSI/1.0","Accept":"application/json","Referer":"https://www.sofascore.com/"})
            with urllib.request.urlopen(req,timeout=45) as r:return json.load(r),base
        except Exception as e:last=e
    raise last
def save(path,payload):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"));
    if not cfg.get("enabled") or not cfg.get("team"):return
    root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];raw=root/"raw"/"sofascore";st={"source":"sofascore","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"team":cfg["team"],"layers":{},"records":{},"errors":[],"attempted_bases":BASES}
    try:
        tid=str((cfg.get("provider_ids") or {}).get("sofascore") or "")
        if not tid:raise RuntimeError("SofaScore team id not configured")
        data,base=get_json(f"/team/{tid}");save(raw/"team.json",data);st["base_used"]=base;st["layers"]["team"]="available";st["records"]["team"]=1;st["team_id"]=tid
        try:
            squad,base=get_json(f"/team/{tid}/players");save(raw/"squad.json",squad);st["layers"]["players"]="available";st["records"]["players"]=len(squad.get("players",[]))
        except Exception as e:st["errors"].append({"layer":"players","error":str(e)})
        events=[]
        for page in range(40):
            try:p,base=get_json(f"/team/{tid}/events/last/{page}")
            except Exception as e:st["errors"].append({"layer":"matches","page":page,"error":str(e)});break
            save(raw/"events"/f"last-{page}.json",p);batch=p.get("events",[]);events.extend(batch)
            if not p.get("hasNextPage") or not batch:break
            time.sleep(.2)
        events=list({str(e.get("id")):e for e in events if e.get("id")}.values());save(raw/"events.json",{"events":events});st["layers"]["matches"]="available" if events else "pending";st["records"]["matches"]=len(events)
        tournament_id=str((cfg.get("provider_competition_ids") or {}).get("sofascore") or "202")
        season_id=None
        try:
            seasons,_=get_json(f"/unique-tournament/{tournament_id}/seasons");save(raw/"competition-seasons.json",seasons)
            season_rows=seasons.get("seasons",[]);wanted=str(cfg.get("season") or "2026/2027")
            for s in season_rows:
                if str(s.get("name") or s.get("year")) in {wanted,wanted[:4],"26/27"}:season_id=str(s.get("id"));break
            if not season_id and season_rows:season_id=str(season_rows[0].get("id"))
            if season_id:
                for endpoint,name in [(f"/unique-tournament/{tournament_id}/season/{season_id}/standings/total","standings.json"),(f"/unique-tournament/{tournament_id}/season/{season_id}/statistics","competition-statistics.json")]:
                    try:payload,_=get_json(endpoint);save(raw/name,payload)
                    except Exception as e:st["errors"].append({"layer":"competition","endpoint":endpoint,"error":str(e)})
                for page in range(20):
                    try:payload,_=get_json(f"/unique-tournament/{tournament_id}/season/{season_id}/events/last/{page}");save(raw/"competition-events"/f"last-{page}.json",payload)
                    except Exception as e:st["errors"].append({"layer":"competition-events","page":page,"error":str(e)});break
                    if not payload.get("hasNextPage") or not payload.get("events"):break
                    time.sleep(.15)
                st["layers"]["competition"]="available";st["records"]["competition_season_id"]=season_id
        except Exception as e:st["errors"].append({"layer":"competition","error":str(e)})
        counts={"event":0,"statistics":0,"incidents":0,"lineups":0,"graph":0,"shotmap":0}
        for e in events:
            eid=str(e["id"])
            for suffix,key,fn in [("","event","event.json"),("/statistics","statistics","statistics.json"),("/incidents","incidents","incidents.json"),("/lineups","lineups","lineups.json"),("/graph","graph","graph.json"),("/shotmap","shotmap","shotmap.json")]:
                dest=raw/"matches"/eid/fn
                try:
                    if dest.exists():counts[key]+=1;continue
                    payload,_=get_json(f"/event/{eid}{suffix}");save(dest,payload);counts[key]+=1
                except Exception as exc:st["errors"].append({"match_id":eid,"layer":key,"error":str(exc)})
                time.sleep(.05)
        st["layers"].update({"events":"available" if counts["incidents"] else "partial","stats":"available" if counts["statistics"] else "partial","spatial":"available" if counts["shotmap"] else "partial"});st["records"].update(counts);st["status"]="success" if not st["errors"] else "partial"
    except Exception as exc:st["status"]="error";st["errors"].append({"fatal":str(exc)})
    save(root/"source-status-sofascore.json",st)
if __name__=="__main__":main()
