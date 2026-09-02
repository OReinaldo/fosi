"""Build an evidence-first field inventory from FOSI RAW data.

The dictionary is generated from the actual files acquired for the selected scout.
It never invents fields and never modifies RAW. Each observed JSON path is tracked
with source file, type, occurrence count, and example values. This is the first
step toward the universal FOSI normalized model.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")
OUT = Path("data/fosi-data-dictionary.json")


def type_name(value):
    if value is None: return "null"
    if isinstance(value, bool): return "boolean"
    if isinstance(value, int) and not isinstance(value, bool): return "integer"
    if isinstance(value, float): return "number"
    if isinstance(value, str): return "string"
    if isinstance(value, list): return "array"
    if isinstance(value, dict): return "object"
    return type(value).__name__


def walk(value, path="$"):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        # Indexes are intentionally collapsed so the dictionary describes fields,
        # not the incidental number of array elements in a single response.
        if value:
            yield from walk(value[0], f"{path}[]")


def safe_example(value):
    if isinstance(value, (dict, list)):
        return f"<{type_name(value)}>"
    text = str(value)
    return text if len(text) <= 160 else text[:157] + "..."


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    root = ROOT / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    raw_root = root / "raw"
    fields = {}
    files_seen = 0
    source_files = []

    for path in sorted(raw_root.rglob("*.json")) if raw_root.exists() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        files_seen += 1
        rel = str(path.relative_to(raw_root)).replace("\\", "/")
        source = rel.split("/", 1)[0]
        source_files.append(rel)
        for field_path, value in walk(payload):
            rec = fields.setdefault(field_path, {"path": field_path, "types": Counter(), "occurrences": 0, "sources": set(), "files": set(), "example": None})
            rec["types"][type_name(value)] += 1
            rec["occurrences"] += 1
            rec["sources"].add(source)
            rec["files"].add(rel)
            if rec["example"] is None and not isinstance(value, (dict, list)):
                rec["example"] = safe_example(value)

    output = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"country": cfg["country"], "competition": cfg["competition"], "team": cfg["team"], "team_id": cfg["team_id"]},
        "method": "observed-from-raw",
        "files_seen": files_seen,
        "source_files": source_files,
        "fields": []
    }
    for path, rec in sorted(fields.items()):
        output["fields"].append({
            "path": path,
            "types": dict(rec["types"]),
            "occurrences": rec["occurrences"],
            "sources": sorted(rec["sources"]),
            "file_count": len(rec["files"]),
            "example": rec["example"]
        })
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=list), encoding="utf-8")
    print(f"FOSI dictionary: {len(output['fields'])} observed paths across {files_seen} RAW files -> {OUT}")


if __name__ == "__main__":
    main()
