"""Normalize spatial/event payloads into dashboard-ready buckets.
Provider schemas vary, so raw payloads are retained and this layer records
only fields that can be identified safely."""
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
                    if any(str(n).lower()==lk for n in names): found[bucket]+=1
                walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(node);return found
def main():
    for status_path in ROOT.glob("**/status.json"):
        root=status_path.parent; counts={k:0 for k in KEYS}; matches=list((root/"matches").glob("*.json")) if (root/"matches").exists() else []
        for p in matches:
            try:
                c=find_keys(json.loads(p.read_text()))
                for k,v in c.items():counts[k]+=v
            except Exception:pass
        (root/"spatial_index.json").write_text(json.dumps({"matches_scanned":len(matches),"detected_sections":counts},indent=2))
if __name__=="__main__":main()
