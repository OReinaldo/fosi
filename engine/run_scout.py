"""Run FOSI acquisition, spatial indexing and quality pipeline for selected target."""
import json, subprocess
from pathlib import Path
from quality import score
CONFIG=Path("config/selected-scout.json")
def main():
    cfg=json.loads(CONFIG.read_text())
    if not cfg.get("enabled") or not cfg.get("team"):
        print("FOSI: no active scouting target; nothing to do");return
    subprocess.run(["python","collectors/fotmob_collector.py"],check=True)
    subprocess.run(["python","engine/spatial.py"],check=True)
    root=Path("data/scouting")/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"]
    status=json.loads((root/"status.json").read_text());status["data_score"]=score(status.get("layers",{}));status["selected_target"]=cfg
    (root/"status.json").write_text(json.dumps(status,indent=2,ensure_ascii=False))
if __name__=="__main__":main()
