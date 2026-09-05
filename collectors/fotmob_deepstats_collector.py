"""Acquire FotMob league-season deep-stat tables as preserved RAW evidence.

This is intentionally best-effort: if FotMob exposes the route without additional
browser/session requirements, FOSI keeps the returned tables. Failed/unavailable
requests are recorded and never converted into fabricated statistics.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://www.fotmob.com/api/data"
CONFIG = Path("config/selected-scout.json")
ROOT_BASE = Path("data/scouting")

PLAYER_STATS = [
    "goals", "assists", "expected_goals", "expected_assists", "shots",
    "shots_on_target", "rating", "key_passes", "accurate_passes", "passes",
    "tackles", "interceptions", "recoveries", "duels_won", "duels",
    "fouls", "possession_lost", "touches", "final_third_entries",
    "successful_dribbles", "big_chances_created", "minutes_played"
]
TEAM_STATS = [
    "goals", "expected_goals", "shots", "shots_on_target", "possession",
    "passes", "accurate_passes", "key_passes", "tackles", "interceptions",
    "recoveries", "duels_won", "duels", "fouls", "possession_lost",
    "corners", "free_kicks", "clean_sheets"
]

def get_json(path):
    req = urllib.request.Request(
        BASE + path,
        headers={"User-Agent": "Mozilla/5.0 FOSI/1.2", "Accept": "application/json", "Referer": "https://www.fotmob.com/"},
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)

def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)

def season_candidates(payload, season_label):
    """Find FotMob's internal numeric season id without assuming its value."""
    target = str(season_label).replace(" ", "").lower()
    candidates = []
    for obj in walk(payload):
        if not isinstance(obj, dict):
            continue
        sid = obj.get("id")
        if sid is None or not str(sid).isdigit():
            continue
        text = " ".join(str(obj.get(k, "")) for k in ("name", "label", "title", "season", "seasonName", "displayName", "year"))
        compact = text.replace(" ", "").lower()
        if target in compact or (str(season_label)[:4] in compact and "season" in compact):
            candidates.append(str(sid))
    # Preserve order, then try a season object found under common mapping keys.
    out = []
    for x in candidates:
        if x not in out:
            out.append(x)
    return out

def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    root = ROOT_BASE / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    raw = root / "raw" / "fotmob"
    league_path = raw / "league.json"
    status = {
        "source": "fotmob",
        "status": "collecting",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "route": "/leagueseasondeepstats",
        "records": {"player_tables": 0, "team_tables": 0, "rows": 0},
        "season_candidates": [],
        "errors": [],
    }
    if not league_path.exists():
        status["status"] = "unavailable"
        status["errors"].append("raw/fotmob/league.json is missing")
        save(raw / "source-status-fotmob-deepstats.json", status)
        return
    league = json.loads(league_path.read_text(encoding="utf-8"))
    league_id = str((cfg.get("provider_competition_ids") or {}).get("fotmob") or "")
    season = str(cfg.get("season") or "2026/2027")
    candidates = season_candidates(league, season)
    # Some payloads expose only a numeric season in a seasons mapping. Try explicit
    # values found anywhere in the league response before falling back to the year.
    if not candidates:
        for obj in walk(league):
            if isinstance(obj, dict):
                for key in ("seasonId", "season_id", "currentSeasonId"):
                    value = obj.get(key)
                    if value is not None and str(value).isdigit():
                        candidates.append(str(value))
    candidates = list(dict.fromkeys(candidates))
    status["season_candidates"] = candidates
    if not league_id:
        status["status"] = "unavailable"
        status["errors"].append("provider competition id is missing")
        save(raw / "source-status-fotmob-deepstats.json", status)
        return

    season_params = candidates + [season, season[:4]]
    seen_params = []
    for season_param in season_params:
        if str(season_param) in seen_params:
            continue
        seen_params.append(str(season_param))
        for stat_type, stats in (("players", PLAYER_STATS), ("teams", TEAM_STATS)):
            for stat in stats:
                query = urllib.parse.urlencode({"id": league_id, "season": season_param, "type": stat_type, "stat": stat})
                out_path = raw / "deepstats" / str(season_param) / stat_type / (stat + ".json")
                if out_path.exists():
                    try:
                        payload = json.loads(out_path.read_text(encoding="utf-8"))
                        status["records"]["player_tables" if stat_type == "players" else "team_tables"] += 1
                        if isinstance(payload, dict):
                            for key in ("TopLists", "topLists", "stats", "rows", "data"):
                                value = payload.get(key)
                                if isinstance(value, list): status["records"]["rows"] += len(value)
                    except Exception:
                        pass
                    continue
                try:
                    payload = get_json("/leagueseasondeepstats?" + query)
                    if not isinstance(payload, (dict, list)):
                        raise ValueError("non-JSON-object response")
                    save(out_path, payload)
                    status["records"]["player_tables" if stat_type == "players" else "team_tables"] += 1
                    if isinstance(payload, dict):
                        for key in ("TopLists", "topLists", "stats", "rows", "data"):
                            value = payload.get(key)
                            if isinstance(value, list): status["records"]["rows"] += len(value)
                except Exception as exc:
                    status["errors"].append({"type": stat_type, "stat": stat, "season": str(season_param), "error": str(exc)})
    if status["records"]["player_tables"] or status["records"]["team_tables"]:
        status["status"] = "success" if not status["errors"] else "partial"
    else:
        status["status"] = "unavailable"
    save(raw / "source-status-fotmob-deepstats.json", status)
    print(json.dumps(status, ensure_ascii=False))

if __name__ == "__main__":
    main()
