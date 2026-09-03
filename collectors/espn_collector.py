"""Optional ESPN public JSON collector. Unsupported leagues are recorded, never synthesized."""
import json,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
CONFIG=Path("config/selected-scout.json");ROOT_BASE=Path("data/scouting")
BASES=["https://site.api.espn.com/apis/site/v2/sports/soccer","https://site.web.api.espn.com/apis/site/v2/sports/soccer"]
def get(path):
    last=None
    for base in BASES:
        try:
            req=urllib.request.Request(base+path,headers={"User-Agent":"Mozilla/5.0 FOSI/1.0","Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=30) as r:return json.load(r),base
        except Exception as e:last=e
    raise last
def save(path,payload):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"));root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];raw=root/"raw"/"espn";st={"source":"espn","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"layers":{},"records":{},"errors":[]}
    league=str((cfg.get("provider_competition_ids") or {}).get("espn") or "pol.1")
    try:
        teams,base=get(f"/{league}/teams");save(raw/"teams.json",teams);st["base_used"]=base;st["layers"]["competition"]="available";st["records"]["teams"]=len(teams.get("sports",teams.get("teams",[]))) if isinstance(teams,dict) else 0
    except Exception as e:st["errors"].append({"layer":"competition","error":str(e)})
    try:
        team_id=str((cfg.get("provider_ids") or {}).get("espn") or "")
        if team_id:
            team,_=get(f"/{league}/teams/{urllib.parse.quote(team_id)}");save(raw/"team.json",team);st["layers"]["team"]="available";st["records"]["team"]=1
            schedule,_=get(f"/{league}/teams/{urllib.parse.quote(team_id)}/schedule");save(raw/"schedule.json",schedule);st["layers"]["matches"]="available";st["records"]["schedule_events"]=len(schedule.get("events",[]))
        else:
            st["errors"].append({"team":"ESPN team id not configured; league probe retained"})
    except Exception as e:st["errors"].append({"layer":"team/matches","error":str(e)})
    try:
        news,_=get(f"/{league}/news");save(raw/"news.json",news);st["layers"]["news"]="available";st["records"]["news_items"]=len(news.get("articles",[]))
    except Exception as e:st["errors"].append({"layer":"news","error":str(e)})
    st["status"]="success" if not st["errors"] else "partial" if st["records"] else "error";save(root/"source-status-espn.json",st)
if __name__=="__main__":main()
