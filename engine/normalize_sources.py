"""Normalize FOSI RAW provider data into a stable, evidence-first model."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")
PLAYER_FIELDS = {
    "minutes": ("minutes", "minsPlayed", "minutesPlayed"), "starts": ("starts", "started"),
    "appearances": ("appearances", "apps", "appearancesTotal"), "goals": ("goals", "goalsTotal"),
    "assists": ("assists", "assistsTotal"), "rating": ("rating", "avgRating", "averageRating"),
    "shots": ("shots", "shotsTotal"), "shots_on_target": ("shotsOnTarget", "shotsOnTargetTotal"),
    "xg": ("xg", "expectedGoals"), "xgot": ("xgot", "expectedGoalsOnTarget"),
    "key_passes": ("keyPasses", "keyPassesTotal"), "passes": ("passes", "totalPasses"),
    "accurate_passes": ("accuratePasses", "passesAccurate"), "tackles": ("tackles", "tacklesTotal"),
    "interceptions": ("interceptions", "interceptionsTotal"), "duels": ("duels", "duelsTotal"),
    "recoveries": ("recoveries", "ballRecoveries"), "turnovers": ("turnovers", "possessionLost"),
    "fouls": ("fouls", "foulsCommitted"), "yellow_cards": ("yellowCards", "yellowCard"),
    "red_cards": ("redCards", "redCard"),
}

def load(path: Path) -> Any: return json.loads(path.read_text(encoding="utf-8"))

def first(d: dict, *keys, default=None):
    if not isinstance(d, dict): return default
    for key in keys:
        if key in d and d[key] is not None: return d[key]
    return default

def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values(): yield from walk(v)
    elif isinstance(node, list):
        for v in node: yield from walk(v)

def deep_first(node, keys):
    wanted={k.lower() for k in keys}
    for obj in walk(node):
        for k,v in obj.items():
            if k.lower() in wanted and v is not None: return v
    return None

def find_lists(node: Any, wanted: set[str], found=None):
    found = found if found is not None else {}
    if isinstance(node, dict):
        for k,v in node.items():
            if k.lower() in wanted and isinstance(v,list): found.setdefault(k.lower(),[]).extend(v)
            find_lists(v,wanted,found)
    elif isinstance(node,list):
        for v in node: find_lists(v,wanted,found)
    return found

def source_meta(source, raw_path, provider_id=None):
    return {"source":source,"raw_path":raw_path,"provider_id":str(provider_id) if provider_id is not None else None,"retrieved_at":datetime.now(timezone.utc).isoformat()}

def normalize_match(payload, raw_path, source):
    general=payload.get("general") or {}; header=payload.get("header") or {}
    if not isinstance(general,dict) or not isinstance(header,dict): return None
    teams=header.get("teams") if isinstance(header.get("teams"),dict) else {}
    home=teams.get("home") if isinstance(teams.get("home"),dict) else first(header,"homeTeam",default={})
    away=teams.get("away") if isinstance(teams.get("away"),dict) else first(header,"awayTeam",default={})
    mid=first(general,"matchId","id")
    if mid is None:return None
    hs=first(home,"score","goals"); ass=first(away,"score","goals")
    result="D" if isinstance(hs,(int,float)) and isinstance(ass,(int,float)) and hs==ass else "W" if isinstance(hs,(int,float)) and isinstance(ass,(int,float)) and hs>ass else "L" if isinstance(hs,(int,float)) and isinstance(ass,(int,float)) else None
    return {"fosi_id":f"match:{source}:{mid}","provider":source,"provider_id":str(mid),"date":first(general,"matchTime","utcTime","date","startTime"),"competition":first(general,"leagueName","competitionName"),"round":first(general,"matchRound","round"),"home_team":{"id":first(home,"id","teamId"),"name":first(home,"name","longName")},"away_team":{"id":first(away,"id","teamId"),"name":first(away,"name","longName")},"score":{"home":hs,"away":ass},"result_for_home":result,"source_meta":source_meta(source,raw_path,mid)}

def normalize_players(payload, raw_path, source):
    result=[]; lists=find_lists(payload,{"players","lineup","lineups","playerdata","squad"}); seen=set()
    for values in lists.values():
        for p in values:
            if not isinstance(p,dict): continue
            pid=first(p,"id","playerId","player_id"); name=first(p,"name","playerName","fullName")
            if pid is None and name is None: continue
            key=str(pid or name)
            if key in seen: continue
            seen.add(key); stats={}
            for canonical,aliases in PLAYER_FIELDS.items():
                v=deep_first(p,aliases)
                if isinstance(v,(int,float)) and not isinstance(v,bool): stats[canonical]=v
                elif isinstance(v,str):
                    try: stats[canonical]=float(v.replace(",",".").replace("%",""))
                    except ValueError: pass
            result.append({"fosi_id":f"player:{source}:{key}","provider":source,"provider_id":str(pid) if pid is not None else None,"name":name,"position":first(p,"position","role","positionName"),"team_id":first(p,"teamId","team_id"),"stats":stats,"source_meta":source_meta(source,raw_path,pid)})
    return result

def normalize_event_like(payload, raw_path, source):
    out={"shots":[],"events":[],"spatial_actions":[]}; lists=find_lists(payload,{"shotmap","shots","incidents","events","passes"}); mid=deep_first(payload,("matchId","match_id"))
    for key,values in lists.items():
        for item in values:
            if not isinstance(item,dict): continue
            iid=first(item,"id","eventId","shotId"); record=dict(item); record["fosi_id"]=f"{key}:{source}:{iid}" if iid is not None else f"{key}:{source}:{mid}:{len(out[key if key in out else 'events'])}"; record["provider"]=source; record["provider_id"]=str(iid) if iid is not None else None; record["match_id"]=str(mid) if mid is not None else None; record["source_meta"]=source_meta(source,raw_path,iid)
            if key in {"shotmap","shots"}: out["shots"].append(record)
            elif key=="passes": out["spatial_actions"].append(record)
            else: out["events"].append(record)
    return out

def normalize_file(payload, raw_path, source): return normalize_match(payload,raw_path,source),normalize_players(payload,raw_path,source),normalize_event_like(payload,raw_path,source)

def main():
    cfg=load(CONFIG); root=ROOT/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"]; raw_root=root/"raw"; out_root=root/"normalized"; out_root.mkdir(parents=True,exist_ok=True)
    matches=[];players=[];events=[];shots=[];spatial=[];records=0
    for path in sorted(raw_root.rglob("*.json")) if raw_root.exists() else []:
        if "source-status" in path.name or path.name.startswith("status-"): continue
        try: payload=load(path)
        except Exception: continue
        source=path.relative_to(raw_root).parts[0]; rel=str(path.relative_to(ROOT)).replace("\\","/"); match,ps,ev=normalize_file(payload,rel,source)
        if match: matches.append(match)
        players.extend(ps);events.extend(ev["events"]);shots.extend(ev["shots"]);spatial.extend(ev["spatial_actions"]);records+=1
    def dedupe(rows):
        seen=set();out=[]
        for row in rows:
            key=row.get("fosi_id") or json.dumps(row,sort_keys=True,ensure_ascii=False)
            if key not in seen:seen.add(key);out.append(row)
        return out
    bundle={"schema_version":"1.1","model":"FOSI normalized","generated_at":datetime.now(timezone.utc).isoformat(),"scope":{"country":cfg["country"],"competition":cfg["competition"],"team":cfg["team"],"team_id":cfg["team_id"]},"method":"normalized-from-raw","counts":{},"matches":dedupe(matches),"players":dedupe(players),"events":dedupe(events),"shots":dedupe(shots),"spatial_actions":dedupe(spatial)}
    bundle["counts"]={k:len(bundle[k]) for k in ("matches","players","events","shots","spatial_actions")}; (out_root/"fosi.json").write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding="utf-8"); print(f"FOSI normalized: {records} RAW files -> {bundle['counts']}")
if __name__=="__main__":main()
