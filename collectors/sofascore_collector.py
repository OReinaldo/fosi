"""FOSI SofaScore collector with raw preservation and resume-safe acquisition."""
import json,time,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
BASE="https://api.sofascore.com/api/v1";CONFIG=Path("config/selected-scout.json");ROOT_BASE=Path("data/scouting")
def get_json(path):
    req=urllib.request.Request(BASE+path,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json","Referer":"https://www.sofascore.com/"})
    with urllib.request.urlopen(req,timeout=45) as r:return json.load(r)
def save(path,payload):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
def resolve_team(name):
    data=get_json("/search/all?q="+urllib.parse.quote(name));exact=fallback=None
    for item in data.get("results",[]):
        ent=item.get("entity") or {}
        if item.get("type")=="team":
            n=str(ent.get("name","") or "");tid=ent.get("id")
            if n.lower()==name.lower():exact=str(tid);break
            if name.lower() in n.lower():fallback=str(tid)
    return exact or fallback,data
def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"))
    if not cfg.get("enabled") or not cfg.get("team"):return
    root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];raw=root/"raw"/"sofascore";st={"source":"sofascore","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"team":cfg["team"],"layers":{},"records":{},"errors":[]}
    try:
        tid=str((cfg.get("provider_ids") or {}).get("sofascore") or "")
        if not tid:tid,search=resolve_team(cfg["team"]);save(raw/"search.json",search)
        if not tid:raise RuntimeError("SofaScore team id could not be resolved")
        save(raw/"team.json",get_json(f"/team/{tid}"));st["layers"]["team"]="available";st["records"]["team"]=1;st["team_id"]=tid
        squad=get_json(f"/team/{tid}/players");save(raw/"squad.json",squad);st["layers"]["players"]="available";st["records"]["players"]=len(squad.get("players",[]))
        events=[]
        for page in range(20):
            p=get_json(f"/team/{tid}/events/last/{page}");save(raw/"events"/f"last-{page}.json",p);batch=p.get("events",[]);events.extend(batch)
            if not p.get("hasNextPage") or not batch:break
            time.sleep(.25)
        events=list({str(e.get("id")):e for e in events if e.get("id")}.values());save(raw/"events.json",{"events":events});st["layers"]["matches"]="available" if events else "pending";st["records"]["matches"]=len(events)
        counts={"event":0,"statistics":0,"incidents":0,"lineups":0,"graph":0,"shotmap":0}
        for e in events:
            eid=str(e["id"])
            for suffix,key,fn in [("","event","event.json"),("/statistics","statistics","statistics.json"),("/incidents","incidents","incidents.json"),("/lineups","lineups","lineups.json"),("/graph","graph","graph.json"),("/shotmap","shotmap","shotmap.json")]:
                dest=raw/"matches"/eid/fn
                try:
                    if dest.exists():counts[key]+=1;continue
                    save(dest,get_json(f"/event/{eid}{suffix}"));counts[key]+=1
                except Exception as exc:st["errors"].append({"match_id":eid,"layer":key,"error":str(exc)})
                time.sleep(.08)
        st["layers"].update({"events":"available" if counts["incidents"] else "partial","stats":"available" if counts["statistics"] else "partial","spatial":"available" if counts["shotmap"] else "partial"});st["records"].update(counts);st["status"]="success" if not st["errors"] else "partial"
    except Exception as exc:st["status"]="error";st["errors"].append({"fatal":str(exc)})
    save(root/"source-status-sofascore.json",st)
if __name__=="__main__":main()
