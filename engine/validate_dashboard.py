"""Validate the public FOSI payload without hard-coding one club."""
import json
from pathlib import Path

p = Path("dashboard/data.json")
d = json.loads(p.read_text(encoding="utf-8"))
required = ["schema_version", "generated_at", "status", "team", "metrics", "matches", "players", "data_quality", "sources"]
missing = [k for k in required if k not in d]
if missing:
    raise SystemExit(f"Missing dashboard fields: {', '.join(missing)}")
if not d["team"].get("id") or not d["team"].get("name"):
    raise SystemExit("Dashboard team identity is incomplete")
if not isinstance(d["matches"], list) or not isinstance(d["players"], list):
    raise SystemExit("matches/players must be arrays")
if not isinstance(d["data_quality"], dict) or not isinstance(d["sources"], list):
    raise SystemExit("Invalid data_quality/sources")
print(f"FOSI dashboard payload valid: schema={d['schema_version']} team={d['team']['name']} matches={len(d['matches'])} status={d['status']}")
