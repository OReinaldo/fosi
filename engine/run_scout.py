"""Run the current FOSI ingestion/normalization/quality pipeline."""
import json
import subprocess
from pathlib import Path
from quality import score

ROOT = Path("data/scouting/poland/ekstraklasa/pogon-szczecin")


def main():
    subprocess.run(["python", "collectors/fotmob_collector.py"], check=False)
    if (ROOT / "raw_team.json").exists():
        subprocess.run(["python", "engine/normalize.py"], check=True)
    status = json.loads((ROOT / "status.json").read_text())
    status["data_score"] = score(status.get("layers", {}))
    (ROOT / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
