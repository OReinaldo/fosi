"""Normalize provider data into a stable FOSI summary model."""
import json
from pathlib import Path

ROOT = Path("data/scouting/poland/ekstraklasa/pogon-szczecin")


def main():
    raw = json.loads((ROOT / "raw_team.json").read_text())
    team = raw.get("team", raw)
    normalized = {
        "team": {
            "id": "pogon-szczecin",
            "name": team.get("name", "Pogoń Szczecin"),
            "country": "Poland",
            "competition": "Ekstraklasa"
        },
        "provider": "fotmob",
        "provider_team_id": "8023"
    }
    (ROOT / "normalized_team.json").write_text(json.dumps(normalized, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
