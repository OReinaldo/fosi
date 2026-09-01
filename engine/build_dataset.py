"""Build a compact dashboard dataset from the active scouting cache."""
import json
from pathlib import Path
from datetime import datetime, timezone

CFG=Path("config/selected-scout.json")
OUT=Path("dashboard/data.json")

def main():
    cfg=json.loads(CFG.read_text(encoding="utf-8"))
    root=Path("data/scouting")/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"]
    status=json.loads((root/"status.json").read_text(encoding="utf-8")) if (root/"status.json").exists() else {}
    matches=[]
    for p in sorted((root/"matches").glob("*.json"), reverse=True):
        try:
            d=json.loads(p.read_text(encoding="utf-8")); m=d.get("header",d.get("match",d))
            matches.append({"id":p.stem,"raw":m})
        except Exception: pass
    payload={"version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"scouting":{"country":cfg["country"],"competition":cfg["competition"],"team":cfg["team"],"team_id":cfg["team_id"],"status":status.get("status","pending"),"data_score":status.get("data_score",0),"layers":status.get("layers",{}),"last_update":status.get("last_successful_update")},"matches":matches}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__":main()
