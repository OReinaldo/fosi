"""FOSI FotMob collector: full available match payloads for the active target."""
import json, urllib.request
from datetime import datetime, timezone
from pathlib import Path
BASE="https://www.fotmob.com/api/data"; CONFIG=Path("config/selected-scout.json"); ROOT_BASE=Path("data/scouting")
def get_json(path):
    req=urllib.request.Request(BASE+path,headers={"User-Agent":"Mozilla/5.0 FOSI/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=45) as r:return json.load(r)
def walk_matches(node):
    out=[]
    if isinstance(node,dict):
        if {"id","home","away"}.issubset(node) and isinstance(node["home"],dict) and isinstance(node["away"],dict):out.append(node)
        for v in node.values():out+=walk_matches(v)
    elif isinstance(node,list):
        for v in node:out+=walk_matches(v)
    return out
def finished(m):
    s=m.get("status") or {};return bool(s.get("finished") or (s.get("reason") or {}).get("short") in {"FT","AET","PEN"})
def team_match(m,name):
    ns=[(m.get("home") or {}).get("name"),(m.get("home") or {}).get("longName"),(m.get("away") or {}).get("name"),(m.get("away") or {}).get("longName")]
    return any(name.lower() in str(x).lower() for x in ns if x)
def main():
    cfg=json.loads(CONFIG.read_text())
    if not cfg.get("enabled") or not cfg.get("team"):return
    team_name=cfg["team"];team_id=str(cfg["provider_ids"].get("fotmob",""))
    if not team_id:raise RuntimeError("No FotMob provider id for selected team")
    slug=f'{cfg["country"].lower().replace(" ","-")}/{cfg["competition"].lower().replace(" ","-")}/{cfg["team_id"]}';root=ROOT_BASE/slug;(root/"matches").mkdir(parents=True,exist_ok=True)
    status={"team_id":cfg["team_id"],"team_name":team_name,"competition":cfg["competition"],"country":cfg["country"],"provider_ids":cfg["provider_ids"],"collector":"fotmob","status":"collecting","started_at":datetime.now(timezone.utc).isoformat()}
    try:
        team=get_json(f"/teams?id={team_id}&ccode3=POL");(root/"raw_team.json").write_text(json.dumps(team,ensure_ascii=False,indent=2))
        matches={str(m["id"]):m for m in walk_matches(team) if team_match(m,team_name) and finished(m)};matches=sorted(matches.values(),key=lambda m:str((m.get("status") or {}).get("utcTime") or m.get("timeTS") or ""),reverse=True)
        errors=[]
        for m in matches:
            mid=str(m["id"])
            try:(root/"matches"/f"{mid}.json").write_text(json.dumps(get_json(f"/matchDetails?matchId={mid}"),ensure_ascii=False,indent=2))
            except Exception as e:errors.append({"match_id":mid,"error":str(e)})
        status.update({"status":"success","last_successful_update":datetime.now(timezone.utc).isoformat(),"match_count":len(matches),"match_detail_errors":errors,"layers":{"team":"ready","matches":"ready" if matches else "pending","players":"source-loaded","stats":"source-loaded","events":"source-loaded","spatial":"source-loaded","video":"pending"}})
    except Exception as e:status.update({"status":"error","error":str(e)})
    (root/"status.json").write_text(json.dumps(status,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
