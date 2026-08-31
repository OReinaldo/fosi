"""Central registry and provenance helpers for FOSI acquisition."""
import json
from pathlib import Path

CONFIG = Path("config/data-sources.json")
FALLBACK = Path("config/sources.json")

def load_sources():
    path = CONFIG if CONFIG.exists() else FALLBACK
    data = json.loads(path.read_text(encoding="utf-8"))
    return [s for s in data.get("sources", []) if s.get("enabled", True)]

def requested_layers():
    out = []
    for source in load_sources():
        for layer in source.get("layers", []):
            out.append({"source": source["id"], "layer": layer, "priority": source.get("priority", 999)})
    return sorted(out, key=lambda x: (x["priority"], x["source"], x["layer"]))

def provenance(source_id, retrieved_at, confidence, fields):
    return {"source": source_id, "retrieved_at": retrieved_at, "confidence": confidence, "fields": fields}

if __name__ == "__main__":
    print(json.dumps(requested_layers(), ensure_ascii=False, indent=2))
