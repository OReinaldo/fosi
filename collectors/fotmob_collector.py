"""FOSI FotMob collector: team overview + recent match details."""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TEAM_ID = "8023"
TEAM_NAME = "Pogoń Szczecin"
BASE = "https://www.fotmob.com/api/data"
OUT = Path("data/scouting/poland/ekstraklasa/pogon-szczecin")


def get_json(path: str):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0 FOSI/0.3"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def walk_matches(node):
    found = []
    if isinstance(node, dict):
        if {"id", "home", "away"}.issubset(node) and isinstance(node.get("home"), dict) and isinstance(node.get("away"), dict):
            found.append(node)
        for value in node.values():
            found.extend(walk_matches(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(walk_matches(value))
    return found


def is_finished(match):
    status = match.get("status") or {}
    return bool(status.get("finished") or status.get("reason", {}).get("short") in {"FT", "AET", "PEN"})


def involves_team(match):
    names = [
        (match.get("home") or {}).get("name"), (match.get("home") or {}).get("longName"),
        (match.get("away") or {}).get("name"), (match.get("away") or {}).get("longName"),
    ]
    return any(TEAM_NAME.lower() in str(n).lower() for n in names if n)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    status = {"team_id":"pogon-szczecin","team_name":TEAM_NAME,"provider_ids":{"fotmob":TEAM_ID},"collector":"fotmob","status":"collecting","started_at":datetime.now(timezone.utc).isoformat()}
    try:
        team = get_json(f"/teams?id={TEAM_ID}&ccode3=POL")
        (OUT / "raw_team.json").write_text(json.dumps(team, indent=2, ensure_ascii=False))
        candidates = {str(m["id"]): m for m in walk_matches(team) if involves_team(m)}
        finished = [m for m in candidates.values() if is_finished(m)]
        finished.sort(key=lambda m: str((m.get("status") or {}).get("utcTime") or m.get("timeTS") or ""), reverse=True)
        selected = finished[:10]
        matches_dir = OUT / "matches"
        matches_dir.mkdir(exist_ok=True)
        for match in selected:
            mid = str(match["id"])
            try:
                detail = get_json(f"/matchDetails?matchId={mid}")
                (matches_dir / f"{mid}.json").write_text(json.dumps(detail, indent=2, ensure_ascii=False))
            except Exception as exc:
                (matches_dir / f"{mid}.error.json").write_text(json.dumps({"error":str(exc)}, indent=2))
        status.update({"status":"success","last_successful_update":datetime.now(timezone.utc).isoformat(),"layers":{"team":"ready","players":"source-loaded","matches":"ready" if selected else "source-loaded","stats":"ready" if selected else "pending","events":"ready" if selected else "pending","spatial":"source-loaded" if selected else "pending","video":"pending"},"recent_match_count":len(selected)})
    except Exception as exc:
        status.update({"status":"error","error":str(exc)})
    (OUT / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
