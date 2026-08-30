"""Publish a conservative, verified-data dashboard payload."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("data/scouting/poland/ekstraklasa/pogon-szczecin")
OUT = Path("dashboard/data.json")


def team_name(x):
    return (x or {}).get("name") or (x or {}).get("longName") or "—"


def extract_match(detail):
    general = detail.get("general", {}) if isinstance(detail, dict) else {}
    home, away = general.get("homeTeam", {}), general.get("awayTeam", {})
    facts = detail.get("content", {}).get("matchFacts", {})
    return {
        "id": detail.get("id") or facts.get("matchId"),
        "date": general.get("matchTimeUTC") or general.get("utcTime"),
        "home": team_name(home), "away": team_name(away),
        "finished": bool(general.get("finished")),
        "score": facts.get("score", {}).get("scoreStr") if isinstance(facts.get("score"), dict) else None,
    }


def main():
    status = json.loads((ROOT / "status.json").read_text())
    raw = json.loads((ROOT / "raw_team.json").read_text())
    team = raw.get("team", raw) if isinstance(raw, dict) else {}
    matches = []
    for path in sorted((ROOT / "matches").glob("*.json")):
        try:
            matches.append(extract_match(json.loads(path.read_text())))
        except Exception:
            pass
    payload = {
        "schema_version": "0.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "verified_partial" if matches else "awaiting_verified_ingestion",
        "team": {"id":"pogon-szczecin", "name":team.get("name") or "Pogoń Szczecin", "competition":"Ekstraklasa", "country":"Poland"},
        "metrics": {},
        "matches": matches,
        "players": [],
        "threat_score": None,
        "data_quality": {"score": status.get("data_score", 0), "layers": status.get("layers", {})},
        "insights": [],
        "sources": [{"provider":"FotMob", "type":"team + match details"}],
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
