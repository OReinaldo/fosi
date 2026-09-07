"""Merge FotMob league-season deep-stat evidence into normalized FOSI.

Player tables are filtered to the selected team. Team tables are preserved as
`team_season_stats` with per-field provenance. The discovered internal FotMob
season id is preferred and older duplicate season directories never overwrite a
value already observed from the preferred season.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
CONFIG=Path("config/selected-scout.json"); ROOT=Path("data/scouting")

def load(path): return json.loads(path.read_text(encoding="utf-8"))
def save(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def value_from_row(row):
    stat=row.get("statValue")
    if isinstance(stat,dict): return stat.get("value")
    return stat if isinstance(stat,(int,float,str)) and stat not in ("") else None

def source_meta(path,season_dir,pid=None):
    meta={"source":"fotmob","raw_path":str(path),"season":season_dir.name}
    if pid is not None: meta["provider_player_id"]=pid
    return meta

def row_team_id(row):
    tid=row.get("id",row.get("teamId",row.get("team_id")))
    for key in ("team","teamData","teamInfo"):
        obj=row.get(key)
        if isinstance(obj,dict): tid=obj.get("id",obj.get("teamId",tid))
    return tid

def main():
    cfg=load(CONFIG); root=ROOT/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"]; raw=root/"raw"/"fotmob"/"deepstats"; normalized_path=root/"normalized"/"fosi.json"
    if not normalized_path.exists() or not raw.exists(): print(json.dumps({"status":"skipped","reason":"normalized FOSI or deepstats RAW missing"})); return
    data=load(normalized_path); target_team=str((cfg.get("provider_ids") or {}).get("fotmob") or ""); players=data.get("players") or []; by_pid={str(p.get("provider_id")):p for p in players if p.get("provider_id") is not None}
    team_stats=data.setdefault("team_season_stats",{}); team_sources=data.setdefault("team_season_stats_source",{}); team_meta=data.setdefault("team_season_stats_meta",{})
    season_dirs=[p for p in raw.iterdir() if p.is_dir()]
    preferred=str(cfg.get("fotmob_internal_season_id") or "37304")
    season_dirs=sorted(season_dirs,key=lambda p:(p.name!=preferred,p.name))
    merged_rows=values_merged=player_tables=team_tables=0
    preferred_used=False
    for season_dir in season_dirs:
        player_dir=season_dir/"players"
        for path in sorted(player_dir.glob("*.json")) if player_dir.exists() else []:
            try: payload=load(path)
            except Exception: continue
            rows=payload.get("statsData") if isinstance(payload,dict) else None
            if not isinstance(rows,list): continue
            used=False; stat_name=path.stem
            for row in rows:
                if not isinstance(row,dict) or str(row.get("teamId",row.get("team_id")))!=target_team: continue
                pid=str(row.get("id")) if row.get("id") is not None else None
                if not pid: continue
                player=by_pid.get(pid)
                if player is None:
                    player={"fosi_id":f"player:fotmob:{pid}","provider":"fotmob","provider_id":pid,"name":row.get("name"),"position":row.get("position"),"team_id":target_team,"stats":{},"source_meta":{"source":"fotmob","raw_path":str(path),"provider_id":pid,"retrieved_at":datetime.now(timezone.utc).isoformat()}}; players.append(player); by_pid[pid]=player; merged_rows+=1
                value=value_from_row(row)
                if value is None: continue
                player.setdefault("season_stats",{})[stat_name]=value; player.setdefault("season_stats_source",{})[stat_name]=source_meta(path,season_dir,pid); values_merged+=1; used=True
            if used: player_tables+=1
        team_dir=season_dir/"teams"
        for path in sorted(team_dir.glob("*.json")) if team_dir.exists() else []:
            try: payload=load(path)
            except Exception: continue
            rows=payload.get("statsData") if isinstance(payload,dict) else None
            if not isinstance(rows,list): continue
            used=False; stat_name=path.stem
            for row in rows:
                if not isinstance(row,dict) or str(row_team_id(row))!=target_team: continue
                value=value_from_row(row)
                if value is None or stat_name in team_stats: continue
                team_stats[stat_name]=value; team_sources[stat_name]=source_meta(path,season_dir); team_sources[stat_name]["provider_team_id"]=target_team; team_meta[stat_name]={"season":season_dir.name,"preferred_internal_season":season_dir.name==preferred,"provider_team_id":target_team}; values_merged+=1; used=True
            if used:
                team_tables+=1
                if season_dir.name==preferred: preferred_used=True
    data["players"]=players; data["team_season_stats"]=team_stats; data["team_season_stats_source"]=team_sources; data["team_season_stats_meta"]=team_meta
    data.setdefault("provenance",{})["deepstats_enrichment"]={"source":"fotmob","season":cfg.get("season"),"internal_season_id":preferred,"team_provider_id":target_team,"preferred_season_used":preferred_used,"player_tables_used":player_tables,"team_tables_used":team_tables,"team_stats_fields":len(team_stats),"values_merged":values_merged,"players_added":merged_rows,"updated_at":datetime.now(timezone.utc).isoformat()}
    save(normalized_path,data); print(json.dumps({"status":"success","preferred_season":preferred,"team_stats_fields":len(team_stats),"player_tables_used":player_tables,"team_tables_used":team_tables,"values_merged":values_merged,"players_added":merged_rows},ensure_ascii=False))

if __name__=="__main__": main()
