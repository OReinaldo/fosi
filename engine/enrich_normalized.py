"""Second-pass enrichment of normalized FOSI data from preserved RAW evidence."""
import json
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")
NUMERIC = (int, float)


def load(p): return json.loads(p.read_text(encoding="utf-8"))

def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values(): yield from walk(v)
    elif isinstance(node, list):
        for v in node: yield from walk(v)

def val(obj, keys):
    if not isinstance(obj, dict): return None
    wanted={str(k).lower() for k in keys}
    for k,v in obj.items():
        if str(k).lower() in wanted and v is not None: return v
    return None

def number(v):
    if isinstance(v,bool): return None
    if isinstance(v,NUMERIC): return float(v)
    if isinstance(v,str):
        try: return float(v.replace(",",".").replace("%","").strip())
        except ValueError: return None
    return None

def deep(node, keys):
    wanted={str(k).lower() for k in keys}
    for obj in walk(node):
        for k,v in obj.items():
            if str(k).lower() in wanted and v is not None: return v
    return None

def nested_id(item, keys):
    v=val(item,keys)
    if v is not None: return str(v)
    wanted={str(k).lower() for k in keys}
    for obj in walk(item):
        v=val(obj,keys)
        if v is not None: return str(v)
        if "playerid" in wanted or "player_id" in wanted:
            player=obj.get("player")
            if isinstance(player,dict) and player.get("id") is not None: return str(player["id"])
        if any(x in wanted for x in ("matchid","match_id","eventid","event_id")):
            match=obj.get("match")
            if isinstance(match,dict):
                mv=val(match,("matchId","match_id","eventId","event_id"))
                if mv is not None: return str(mv)
    return None

def player_identity(item):
    pid=nested_id(item,("playerId","player_id"))
    pobj=item.get("player") if isinstance(item,dict) else None
    if pid is None and isinstance(pobj,dict) and pobj.get("id") is not None: pid=str(pobj["id"])
    if pid is None and isinstance(item,dict) and item.get("playerOfTheMatch"):
        potm=item["playerOfTheMatch"]
        if isinstance(potm,dict) and potm.get("id") is not None: pid=str(potm["id"])
    name=None
    if isinstance(pobj,dict): name=pobj.get("name") or pobj.get("fullName") or pobj.get("shortName")
    n=item.get("name") if isinstance(item,dict) else None
    if isinstance(n,dict): name=name or n.get("fullName") or " ".join(x for x in (n.get("firstName"),n.get("lastName")) if x)
    name=name or val(item,("playerName","player_name","fullName"))
    return pid,name

STAT_ALIASES={
 "rating":{"rating","rating_title"},"minutes":{"minutes_played","minutes"},
 "goals":{"goals"},"assists":{"assists"},"accurate_passes":{"accurate_passes"},
 "passes":{"passes"},"key_passes":{"key_passes","chances_created"},"shots":{"shots"},
 "shots_on_target":{"shots_on_target"},"xg":{"xg","expected_goals"},"xgot":{"xgot","expected_goals_on_target"},
 "touches":{"touches"},"touches_opp_box":{"touches_opp_box"},"final_third_entries":{"passes_into_final_third","final_third_entries"},
 "long_balls":{"long_balls"},"accurate_long_balls":{"long_balls_accurate","accurate_long_balls"},
 "turnovers":{"dispossessed","possession_lost","turnovers"},"defensive_actions":{"defensive_actions"},
 "tackles":{"tackles","tackles_total"},"blocks":{"shot_blocks","blocks"},"clearances":{"clearances"},
 "interceptions":{"interceptions"},"recoveries":{"recoveries","ball_recoveries"},"dribbled_past":{"dribbled_past"},
 "ground_duels_won":{"ground_duels_won"},"aerial_duels_won":{"aerials_won"},"duels_won":{"duel_won"},
 "was_fouled":{"was_fouled"},"fouls":{"fouls","fouls_committed"},"yellow_cards":{"yellow_cards","yellow_card"},"red_cards":{"red_cards","red_card"}
}

def canonical_stat(key,title):
    raw=str(key or title or "").strip().lower().replace(" ","_")
    candidates={raw, raw.rsplit(".",1)[-1]}
    for canonical,aliases in STAT_ALIASES.items():
        if candidates & {str(a).lower() for a in aliases}: return canonical
    return None

def structured_player_stats(item):
    """Parse FotMob's {title,key,stats:{display:{key,stat:{value,total}}}} blocks."""
    out={}
    sections=item.get("stats") if isinstance(item,dict) else None
    if not isinstance(sections,list): return out
    for section in sections:
        groups=section.get("stats") if isinstance(section,dict) else None
        if not isinstance(groups,dict): continue
        for title,entry in groups.items():
            if not isinstance(entry,dict): continue
            st=entry.get("stat") if isinstance(entry.get("stat"),dict) else entry
            if not isinstance(st,dict): continue
            canonical=canonical_stat(entry.get("key"),title)
            if not canonical: continue
            value=number(st.get("value"))
            if value is None: continue
            out[canonical]=value
            if st.get("total") is not None:
                total=number(st.get("total"))
                if total is not None: out[f"{canonical}_total"]=total
    return out

def player_stats(item):
    out=structured_player_stats(item)
    aliases={
      "minutes":("minutes","minsPlayed","minutesPlayed","minutes_played"),"starts":("starts","started"),
      "goals":("goals","goalsTotal"),"assists":("assists","assistsTotal"),"rating":("rating","avgRating","averageRating"),
      "shots":("shots","shotsTotal","totalShots"),"shots_on_target":("shotsOnTarget","shotsOnTargetTotal","shots_on_target"),
      "xg":("xg","expectedGoals","expected_goals"),"xgot":("xgot","expectedGoalsOnTarget","expected_goals_on_target"),
      "key_passes":("keyPasses","keyPassesTotal","key_passes","chances_created"),"passes":("passes","totalPasses","total_passes"),
      "accurate_passes":("accuratePasses","passesAccurate","accurate_passes"),"tackles":("tackles","tacklesTotal"),
      "interceptions":("interceptions","interceptionsTotal"),"duels":("duels","duelsTotal"),"recoveries":("recoveries","ballRecoveries"),
      "turnovers":("turnovers","possessionLost","dispossessed"),"fouls":("fouls","foulsCommitted"),
      "yellow_cards":("yellowCards","yellowCard"),"red_cards":("redCards","redCard"),"touches":("touches",),
      "touches_opp_box":("touches_opp_box","touchesInOppBox"),"final_third_entries":("passes_into_final_third","passesIntoFinalThird","finalThirdEntries","final_third_entries"),
      "long_balls":("longBalls","longBallsTotal"),"accurate_long_balls":("accurateLongBalls","longBallsAccurate"),
      "clearances":("clearances",),"blocks":("shot_blocks","blocks"),"defensive_actions":("defensive_actions","defensiveActions"),
      "dribbled_past":("dribbledPast",),"ground_duels":("groundDuels","groundDuelsTotal"),"aerial_duels":("aerialDuels","aerialDuelsTotal"),"was_fouled":("wasFouled",)
    }
    for canonical,keys in aliases.items():
        if canonical in out: continue
        n=number(deep(item,keys))
        if n is not None: out[canonical]=n
    return out

def add_player_match(store,pid,mid,team_id,stats,source,raw_path,name=None):
    if not pid or not mid or not stats: return False
    key=f"player_match:{source}:{pid}:{mid}"
    row=store.get(key)
    if row is None:
        row={"fosi_id":key,"provider":source,"provider_id":str(pid),"player_id":str(pid),"match_id":str(mid),"team_id":str(team_id) if team_id is not None else None,"stats":{},"source_meta":{"source":source,"raw_path":raw_path,"provider_id":str(pid),"retrieved_at":datetime.now(timezone.utc).isoformat()}}
        if name: row["player_name"]=str(name)
        store[key]=row
    for k,v in stats.items(): row.setdefault("stats",{})[k]=v
    return True

def spatial_type(item,path):
    text=(path+" "+" ".join(str(k) for k in item.keys())).lower()
    for token,name in (("pass","pass"),("heatmap","heatmap"),("dribble","dribble"),("carry","carry"),("tackle","tackle"),("interception","interception"),("recover","recovery"),("defend","defensive"),("touch","touch")):
        if token in text:return name
    return "spatial_action"

def main():
    cfg=load(CONFIG)
    root=ROOT/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"]
    norm=root/"normalized"/"fosi.json"; raw=root/"raw"
    if not norm.exists(): raise SystemExit("Normalized FOSI data not found")
    data=load(norm)
    player_matches={str(x.get("fosi_id")):x for x in data.get("player_matches",[]) if isinstance(x,dict) and x.get("fosi_id")}
    spatial={str(x.get("fosi_id")):x for x in data.get("spatial_actions",[]) if isinstance(x,dict) and x.get("fosi_id")}
    assets=[];asset_seen=set();files=0;match_detail_rows=0;history_rows=0
    for path in sorted(raw.rglob("*.json")) if raw.exists() else []:
        if "source-status" in path.name or path.name.startswith("status-"): continue
        try: payload=load(path)
        except Exception: continue
        files+=1; source=path.relative_to(raw).parts[0] if path.relative_to(raw).parts else "unknown"; rel=str(path.relative_to(ROOT)).replace("\\","/")
        is_history="player-matches" in path.parts; is_detail=source=="fotmob" and "matches" in path.parts; detail_mid=path.stem if is_detail else None
        for idx,obj in enumerate(walk(payload)):
            if not isinstance(obj,dict): continue
            pid,pname=player_identity(obj); mid=nested_id(obj,("matchId","match_id","eventId","event_id","gameId")) or detail_mid; stats=player_stats(obj); team_id=val(obj,("teamId","team_id"))
            if is_detail and pid and mid and stats and ("stats" in obj or "playerOfTheMatch" in obj):
                if add_player_match(player_matches,pid,mid,team_id,stats,source,rel,pname): match_detail_rows+=1
            if is_history and pid and mid and stats:
                if add_player_match(player_matches,pid,mid,team_id,stats,source,rel,pname): history_rows+=1
            x=number(val(obj,("x","posX","xPos","normalizedX","xCoordinate"))); y=number(val(obj,("y","posY","yPos","normalizedY","yCoordinate")))
            if x is not None and y is not None and 0<=x<=100 and 0<=y<=100 and not any(k in obj for k in ("isOnTarget","expectedGoals","shotType")):
                aid=nested_id(obj,("id","eventId","actionId","playerId")) or str(idx); key=f"spatial:{source}:{mid or 'unknown'}:{aid}:{idx}"
                spatial.setdefault(key,{"fosi_id":key,"provider":source,"provider_id":aid,"match_id":mid,"player_id":pid,"x":x,"y":y,"action_type":spatial_type(obj,rel),"data":obj,"source_meta":{"source":source,"raw_path":rel,"provider_id":aid,"retrieved_at":datetime.now(timezone.utc).isoformat()}})
        if "heatmaps" in path.parts or "maps" in path.parts:
            key=(source,rel)
            if key not in asset_seen:
                asset_seen.add(key); assets.append({"source":source,"asset_type":"heatmap" if "heatmap" in path.name.lower() or "heatmaps" in path.parts else "map","match_id":path.stem,"raw_path":rel,"format":"json","status":"raw-preserved"})
    data["player_matches"]=list(player_matches.values()); data["spatial_actions"]=list(spatial.values()); data["spatial_assets"]=assets
    data["counts"]={k:len(data.get(k,[])) for k in ("competitions","matches","lineups","players","player_matches","events","shots","spatial_actions","spatial_assets")}
    data["enrichment"]={"generated_at":datetime.now(timezone.utc).isoformat(),"raw_files_scanned":files,"match_detail_player_stat_rows_seen":match_detail_rows,"player_history_rows_seen":history_rows,"method":"structured-fotmob-player-stat-blocks","no_raw_mutation":True}
    norm.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(data["counts"],ensure_ascii=False))

if __name__=="__main__": main()
