"""Rebuild FotMob player-match history from cached playerData.recentMatches.

This intentionally rewrites the derived player-match files on every run so an
older failed/empty endpoint result cannot become permanently sticky.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    cfg = load(CONFIG)
    root = ROOT / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    raw = root / "raw" / "fotmob"
    players_dir = raw / "players"
    out_dir = raw / "player-matches"
    league_id = str((cfg.get("provider_competition_ids") or {}).get("fotmob") or ("196" if cfg.get("competition") == "Ekstraklasa" else ""))

    profiles = rows = files = skipped = 0
    errors = []
    for path in sorted(players_dir.glob("*.json")) if players_dir.exists() else []:
        pid = path.stem
        # The team itself can appear in recursively discovered IDs; it is not a player.
        if str(pid) == str((cfg.get("provider_ids") or {}).get("fotmob")):
            continue
        try:
            payload = load(path)
            recent = payload.get("recentMatches") if isinstance(payload, dict) else None
            recent = recent if isinstance(recent, list) else []
            filtered = [r for r in recent if not league_id or str(r.get("leagueId")) == league_id]
            dedup = {}
            for match in filtered:
                mid = match.get("id") or match.get("matchId")
                if mid is not None:
                    dedup[str(mid)] = match
            result = {
                "player_id": str(pid),
                "source": "playerData.recentMatches",
                "league_id": league_id or None,
                "matches": list(dedup.values()),
                "count": len(dedup),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            save(out_dir / f"{pid}.json", result)
            profiles += 1
            files += 1
            rows += len(dedup)
        except Exception as exc:
            errors.append({"player_id": pid, "error": str(exc)})

    status = {
        "source": "fotmob",
        "status": "success" if not errors else "partial",
        "source_of_truth": "playerData.recentMatches",
        "league_id": league_id or None,
        "profiles_processed": profiles,
        "player_match_files_written": files,
        "player_match_rows": rows,
        "errors": errors,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save(root / "source-status-player-history.json", status)
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
