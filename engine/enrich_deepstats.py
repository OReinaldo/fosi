"""Merge preserved FotMob league-season deep-stat evidence into normalized FOSI.

Player tables are filtered to the selected team and merged into each player.
Team tables are also preserved in normalized data as `team_season_stats`, so
team-level deep statistics are not stranded in RAW. Only observed values are
copied; no zeroes or inferred values are created.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

CONFIG=Path("config/selected-scout.json")
ROOT=Path("data/scouting")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def value_from_row(row):
    stat=row.get("statValue")
    if isinstance(stat,dict):
        return stat.get("value")
    return None


def source_meta(path,season_dir,pid=None):
    meta={"source":"fotmob","raw_path":str(path),"season":season_dir.name}
    if pid is not None:
        meta["provider_player_id"]=pid
    return meta


def main():
    cfg=load(CONFIG)
    root=ROOT/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"]
    raw=root/"raw"/"fotmob"/"deepstats"
    normalized_path=root/"normalized"/"fosi.json"
    if not normalized_path.exists() or not raw.exists():
        print(json.dumps({"status":"skipped","reason":"normalized FOSI or deepstats RAW missing"}))
        return

    data=load(normalized_path)
    target_team=str((cfg.get("provider_ids") or {}).get("fotmob") or "")
    players=data.get("players") or []
    by_pid={str(p.get("provider_id")):p for p in players if p.get("provider_id") is not None}
    team_stats=data.setdefault("team_season_stats",{})
    team_sources=data.setdefault("team_season_stats_source",{})
    season_dirs=sorted([p for p in raw.iterdir() if p.is_dir()],key=lambda p:p.name=="37304",reverse=True)
    merged_rows=0
    values_merged=0
    player_tables=0
    team_tables=0

    # Prefer the discovered internal season id. Older duplicate display-year
    # directories are still read for resilience, but later writes may overwrite
    # only with another observed value, never with a fabricated one.
    for season_dir in season_dirs:
        player_dir=season_dir/"players"
        for path in sorted(player_dir.glob("*.json")) if player_dir.exists() else []:
            try: payload=load(path)
            except Exception: continue
            rows=payload.get("statsData") if isinstance(payload,dict) else None
            if not isinstance(rows,list): continue
            used=False
            stat_name=path.stem
            for row in rows:
                if not isinstance(row,dict) or str(row.get("teamId"))!=target_team: continue
                pid=str(row.get("id")) if row.get("id") is not None else None
                if not pid: continue
                player=by_pid.get(pid)
                if player is None:
                    player={"fosi_id":f"player:fotmob:{pid}","provider":"fotmob","provider_id":pid,"name":row.get("name"),"position":row.get("position"),"team_id":target_team,"stats":{},"source_meta":{"source":"fotmob","raw_path":str(path),"provider_id":pid,"retrieved_at":datetime.now(timezone.utc).isoformat()}}
                    players.append(player);by_pid[pid]=player;merged_rows+=1
                value=value_from_row(row)
                if value is None: continue
                player.setdefault("season_stats",{})[stat_name]=value
                player.setdefault("season_stats_source",{})[stat_name]=source_meta(path,season_dir,pid)
                values_merged+=1;used=True
            if used: player_tables+=1

        team_dir=season_dir/"teams"
        for path in sorted(team_dir.glob("*.json")) if team_dir.exists() else []:
            try: payload=load(path)
            except Exception: continue
            rows=payload.get("statsData") if isinstance(payload,dict) else None
            if not isinstance(rows,list): continue
            used=False
            stat_name=path.stem
            for row in rows:
                if not isinstance(row,dict): continue
                # Team deep-stat rows are league-wide. Match the selected team by
                # provider id, accepting common object/string representations.
                tid=row.get("id",row.get("teamId"))
                team_obj=row.get("team")
                if isinstance(team_obj,dict): tid=team_obj.get("id",tid)
                if str(tid)!=target_team: continue
                value=value_from_row(row)
                if value is None: continue
                team_stats[stat_name]=value
                team_sources[stat_name]=source_meta(path,season_dir)
                team_sources[stat_name]["provider_team_id"]=target_team
                values_merged+=1;used=True
            if used: team_tables+=1

    data["players"]=players
    data["team_season_stats"]=team_stats
    data["team_season_stats_source"]=team_sources
    data.setdefault("provenance",{})["deepstats_enrichment"]={"source":"fotmob","season":cfg.get("season"),"team_provider_id":target_team,"player_tables_used":player_tables,"team_tables_used":team_tables,"values_merged":values_merged,"players_added":merged_rows,"updated_at":datetime.now(timezone.utc).isoformat()}
    save(normalized_path,data)
    print(json.dumps({"status":"success","player_tables_used":player_tables,"team_tables_used":team_tables,"values_merged":values_merged,"players_added":merged_rows},ensure_ascii=False))

if __name__=="__main__": main()
