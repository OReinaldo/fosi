"""Acquire FotMob league-season deep-stat tables as preserved RAW evidence.

Best-effort only. The collector first discovers FotMob's internal numeric season id
from the public deep-stats response, then retries the requested stat tables with
that id. No protected headers, tokens or signatures are used.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://www.fotmob.com/api/data"
CONFIG = Path("config/selected-scout.json")
ROOT_BASE = Path("data/scouting")
PLAYER_STATS = ["goals","assists","expected_goals","expected_assists","shots","shots_on_target","rating","key_passes","accurate_passes","passes","tackles","interceptions","recoveries","duels_won","duels","fouls","possession_lost","touches","final_third_entries","successful_dribbles","big_chances_created","minutes_played"]
TEAM_STATS = ["goals","expected_goals","shots","shots_on_target","possession","passes","accurate_passes","key_passes","tackles","interceptions","recoveries","duels_won","duels","fouls","possession_lost","corners","free_kicks","clean_sheets"]


def get_json(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent":"Mozilla/5.0 FOSI/1.3","Accept":"application/json","Referer":"https://www.fotmob.com/"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values(): yield from walk(value)
    elif isinstance(node, list):
        for value in node: yield from walk(value)


def matching_season_ids(payload, season_label, league_id):
    wanted = str(season_label).replace(" ","").lower()
    ids=[]
    for obj in walk(payload):
        if not isinstance(obj,dict): continue
        sid=obj.get("id")
        name=obj.get("name") or obj.get("seasonName") or obj.get("displayName") or obj.get("title")
        lid=obj.get("leagueId") or obj.get("parentLeagueId")
        if sid is not None and str(sid).isdigit() and name and str(name).replace(" ","").lower()==wanted:
            if lid is None or str(lid)==str(league_id): ids.append(str(sid))
    return list(dict.fromkeys(ids))


def is_populated(payload):
    if not isinstance(payload,dict): return False
    for key in ("statsData","rows","data","players","teams"):
        value=payload.get(key)
        if isinstance(value,list) and value: return True
    return False


def row_count(payload):
    if not isinstance(payload,dict): return 0
    for key in ("statsData","rows","data","players","teams"):
        value=payload.get(key)
        if isinstance(value,list): return len(value)
    return 0


def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"))
    root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"]
    raw=root/"raw"/"fotmob"
    league_id=str((cfg.get("provider_competition_ids") or {}).get("fotmob") or "")
    season=str(cfg.get("season") or "2026/2027")
    status={"source":"fotmob","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"route":"/leagueseasondeepstats","records":{"player_tables":0,"team_tables":0,"rows":0,"nonempty_tables":0},"season_candidates":[],"errors":[]}
    if not league_id:
        status["status"]="unavailable"; status["errors"].append("provider competition id is missing"); save(raw/"source-status-fotmob-deepstats.json",status); return

    season_ids=[]
    # FotMob's league overview may not expose the internal season id. Its deepstats
    # response does, so use a public probe and then retry with the returned numeric id.
    probes=[season,season[:4]]
    for probe_season in probes:
        try:
            path="/leagueseasondeepstats?"+urllib.parse.urlencode({"id":league_id,"season":probe_season,"type":"players","stat":"goals"})
            probe=get_json(path)
            season_ids.extend(matching_season_ids(probe,season,league_id))
        except Exception as exc:
            status["errors"].append({"type":"season_discovery","season":probe_season,"error":str(exc)})
    league_path=raw/"league.json"
    if league_path.exists():
        try: season_ids.extend(matching_season_ids(json.loads(league_path.read_text(encoding="utf-8")),season,league_id))
        except Exception as exc: status["errors"].append({"type":"league_read","error":str(exc)})
    season_params=list(dict.fromkeys(season_ids+[season,season[:4]]))
    status["season_candidates"]=season_params

    for season_param in season_params:
        for stat_type,stats in (("players",PLAYER_STATS),("teams",TEAM_STATS)):
            for stat in stats:
                out_path=raw/"deepstats"/str(season_param)/stat_type/(stat+".json")
                payload=None
                if out_path.exists():
                    try: payload=json.loads(out_path.read_text(encoding="utf-8"))
                    except Exception: payload=None
                # Empty tables from display-year requests are retried with the internal id.
                if not is_populated(payload):
                    query=urllib.parse.urlencode({"id":league_id,"season":season_param,"type":stat_type,"stat":stat})
                    try:
                        payload=get_json("/leagueseasondeepstats?"+query)
                        if not isinstance(payload,(dict,list)): raise ValueError("non-JSON response")
                        save(out_path,payload)
                    except Exception as exc:
                        status["errors"].append({"type":stat_type,"stat":stat,"season":str(season_param),"error":str(exc)})
                        continue
                status["records"]["player_tables" if stat_type=="players" else "team_tables"]+=1
                rows=row_count(payload); status["records"]["rows"]+=rows
                if is_populated(payload): status["records"]["nonempty_tables"]+=1
    status["status"]=("success" if not status["errors"] else "partial") if status["records"]["nonempty_tables"] else "unavailable"
    save(raw/"source-status-fotmob-deepstats.json",status)
    print(json.dumps(status,ensure_ascii=False))


if __name__=="__main__": main()
