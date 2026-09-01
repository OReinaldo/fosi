"""Scan all preserved raw provider payloads for spatial/event sections."""
import json
from pathlib import Path
ROOT=Path("data/scouting")
KEYS={"shots":["shots","shotmap","shotMap"],"passes":["passes","passing","passMap","passmap"],"possession":["possession","possessionStats"],"events":["events","incidentEvents","incidents"],"heatmaps":["heatmap","heatmaps","playerHeatmaps"]}
def find_keys(node):
    found={k:0 for k in KEYS}
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                lk=str(k).lower()
                for bucket,names in KEYS.items():
                    if any(str(n).lower()==lk for n in names):found[bucket]+=1
                walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(node);return found
def main():
    for status_path in ROOT.glob("**/master-status.json"):
        root=status_path.parent;counts={k:0 for k in KEYS};files=list((root/"raw").glob("**/*.json")) if (root/"raw").exists() else []
        for p in files:
            try:
                c=find_keys(json.loads(p.read_text(encoding="utf-8")))
                for k,v in c.items():counts[k]+=v
            except Exception:pass
        (root/"spatial_index.json").write_text(json.dumps({"files_scanned":len(files),"detected_sections":counts},indent=2),encoding="utf-8")
if __name__=="__main__":main()
