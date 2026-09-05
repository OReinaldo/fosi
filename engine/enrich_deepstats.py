"""Merge preserved FotMob league-season deep-stat evidence into normalized FOSI players.

The RAW deep-stat tables are league-wide. This pass filters rows to the selected
FotMob team and merges only observed values, retaining source provenance. It never
creates zeroes for missing values and never replaces RAW evidence.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    cfg = load(CONFIG)
    root = ROOT / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    raw = root / "raw" / "fotmob" / "deepstats"
    normalized_path = root / "normalized" / "fosi.json"
    if not normalized_path.exists() or not raw.exists():
        print(json.dumps({"status": "skipped", "reason": "normalized FOSI or deepstats RAW missing"}))
        return

    data = load(normalized_path)
    target_team = str((cfg.get("provider_ids") or {}).get("fotmob") or "")
    players = data.get("players") or []
    by_pid = {str(p.get("provider_id")): p for p in players if p.get("provider_id") is not None}

    # Prefer the discovered numeric season directory; fall back to all numeric
    # season directories so incremental runs remain robust if discovery changes.
    season_dirs = sorted([p for p in raw.iterdir() if p.is_dir()], key=lambda p: p.name == "37304", reverse=True)
    merged_rows = 0
    values_merged = 0
    tables_used = 0

    for season_dir in season_dirs:
        for stat_type in ("players",):
            for path in sorted((season_dir / stat_type).glob("*.json")) if (season_dir / stat_type).exists() else []:
                try:
                    payload = load(path)
                except Exception:
                    continue
                rows = payload.get("statsData") if isinstance(payload, dict) else None
                if not isinstance(rows, list):
                    continue
                used_table = False
                stat_name = path.stem
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("teamId")) != target_team:
                        continue
                    pid = str(row.get("id")) if row.get("id") is not None else None
                    player = by_pid.get(pid)
                    if player is None:
                        # Deep stats can contain a current-season player not yet
                        # present in the squad payload. Preserve it as a player
                        # only when the row is explicitly assigned to the target team.
                        player = {
                            "fosi_id": f"player:fotmob:{pid}",
                            "provider": "fotmob",
                            "provider_id": pid,
                            "name": row.get("name"),
                            "position": row.get("position"),
                            "team_id": target_team,
                            "stats": {},
                            "source_meta": {
                                "source": "fotmob",
                                "raw_path": str(path),
                                "provider_id": pid,
                                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            },
                        }
                        players.append(player)
                        by_pid[pid] = player
                        merged_rows += 1
                    value = ((row.get("statValue") or {}).get("value") if isinstance(row.get("statValue"), dict) else None)
                    if value is None:
                        continue
                    player.setdefault("season_stats", {})[stat_name] = value
                    player.setdefault("season_stats_source", {})[stat_name] = {
                        "source": "fotmob",
                        "raw_path": str(path),
                        "season": season_dir.name,
                        "provider_player_id": pid,
                        "provider_team_id": target_team,
                    }
                    values_merged += 1
                    used_table = True
                if used_table:
                    tables_used += 1

    data["players"] = players
    data.setdefault("provenance", {})["deepstats_enrichment"] = {
        "source": "fotmob",
        "season": cfg.get("season"),
        "team_provider_id": target_team,
        "tables_used": tables_used,
        "values_merged": values_merged,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save(normalized_path, data)
    print(json.dumps({"status": "success", "tables_used": tables_used, "values_merged": values_merged, "players_added": merged_rows}, ensure_ascii=False))


if __name__ == "__main__":
    main()
