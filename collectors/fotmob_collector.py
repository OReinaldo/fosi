"""Minimal FotMob collector for FOSI.

The collector intentionally keeps provider access isolated so additional sources can
be added later without changing the FOSI data model.
"""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TEAM_ID = "8023"  # Pogoń Szczecin provider id
BASE = "https://www.fotmob.com/api"
OUT = Path("data/scouting/poland/ekstraklasa/pogon-szczecin")


def get_json(path: str):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "FOSI/0.2"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    status = {
        "team_id": "pogon-szczecin",
        "team_name": "Pogoń Szczecin",
        "provider_ids": {"fotmob": TEAM_ID},
        "collector": "fotmob",
        "status": "collecting",
        "started_at": started,
    }
    (OUT / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False))

    try:
        team = get_json(f"/teams?id={TEAM_ID}")
        (OUT / "raw_team.json").write_text(json.dumps(team, indent=2, ensure_ascii=False))
        status.update({
            "status": "success",
            "last_successful_update": datetime.now(timezone.utc).isoformat(),
            "layers": {"team": "ready", "players": "source-loaded", "matches": "source-loaded", "stats": "source-loaded", "events": "pending", "spatial": "pending", "video": "pending"},
        })
    except Exception as exc:
        status.update({"status": "error", "error": str(exc)})

    (OUT / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
