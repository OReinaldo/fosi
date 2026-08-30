"""Source registry and provenance helpers for FOSI."""
import json
from pathlib import Path

CONFIG = Path("config/sources.json")

def load_sources():
    return json.loads(CONFIG.read_text(encoding="utf-8"))["sources"]

def provenance(source_id, retrieved_at, confidence, fields):
    return {"source": source_id, "retrieved_at": retrieved_at, "confidence": confidence, "fields": fields}
