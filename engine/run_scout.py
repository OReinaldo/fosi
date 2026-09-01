"""Run the FOSI multi-source acquisition pipeline for the selected target."""
import json, subprocess
from datetime import datetime, timezone
from pathlib import Path
from quality import score
CONFIG=Path("config/selected-scout.json"); ROOT=Path("data/scouting")
def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"))
    if not cfg.get("enabled") or not cfg.get("team"): print("FOSI: no active scouting target; nothing to do"); return
    target=cfg.get("team_id") or cfg["team"].lower().replace(" ","-");root=ROOT/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/target;root.mkdir(parents=True,exist_ok=True)
    previous=(root/"master-status.json").exists();results=[]
    for collector in ["collectors/fotmob_collector.py","collectors/sofascore_collector.py","collectors/understat_collector.py"]:
        p=subprocess.run(["python",collector],capture_output=True,text=True);results.append({"collector":collector,"returncode":p.returncode,"stdout":p.stdout[-2000:],"stderr":p.stderr[-4000:]})
        if p.returncode:print(p.stderr);raise subprocess.CalledProcessError(p.returncode,collector)
    statuses={"sources":[],"layers":{},"target":cfg,"updated_at":datetime.now(timezone.utc).isoformat(),"update_mode":"incremental" if previous else "initial","collectors":results}
    for p in root.glob("source-status-*.json"):
        try:
            s=json.loads(p.read_text(encoding="utf-8"));statuses["sources"].append(s)
            for layer,state in s.get("layers",{}).items():
                old=statuses["layers"].get(layer);rank={"available":4,"ready":4,"partial":2,"pending":1,"not_available":0,"not_applicable":0,"error":0}
                if old is None or rank.get(state,0)>rank.get(old,0):statuses["layers"][layer]=state
        except Exception as exc:statuses.setdefault("errors",[]).append(str(exc))
    statuses["data_score"]=score(statuses["layers"]);out=json.dumps(statuses,ensure_ascii=False,indent=2);(root/"master-status.json").write_text(out,encoding="utf-8");(root/"status.json").write_text(out,encoding="utf-8");print(out)
if __name__=="__main__":main()
