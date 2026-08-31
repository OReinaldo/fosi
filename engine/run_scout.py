"""Run FOSI acquisition, spatial indexing and quality pipeline for selected target."""
import json, subprocess
from pathlib import Path
from quality import score

CONFIG = Path("config/selected-scout.json")

def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not cfg.get("enabled") or not cfg.get("team"):
        print("FOSI: no active scouting target; nothing to do")
        return
    target = (cfg.get("team_id") or cfg["team"].lower().replace(" ", "-"))
    root = Path("data/scouting") / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / target
    root.mkdir(parents=True, exist_ok=True)
    previous = None
    previous_path = root / "status.json"
    if previous_path.exists():
        try: previous = json.loads(previous_path.read_text(encoding="utf-8"))
        except Exception: previous = None
    subprocess.run(["python", "collectors/fotmob_collector.py"], check=True)
    subprocess.run(["python", "engine/spatial.py"], check=True)
    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    status["data_score"] = score(status.get("layers", {}))
    status["selected_target"] = cfg
    status["update_mode"] = "incremental" if previous else "initial"
    (root / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
