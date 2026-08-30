"""Fail CI if the public dashboard payload violates the FOSI contract."""
import json
from pathlib import Path

p = Path("dashboard/data.json")
d = json.loads(p.read_text())
required = ["schema_version", "generated_at", "status", "team", "metrics", "matches", "players", "data_quality", "sources"]
missing = [k for k in required if k not in d]
if missing:
    raise SystemExit(f"Missing dashboard fields: {', '.join(missing)}")
if d["team"].get("id") != "pogon-szczecin":
    raise SystemExit("Unexpected team id")
if not isinstance(d["matches"], list) or not isinstance(d["players"], list):
    raise SystemExit("matches/players must be arrays")
print(f"FOSI dashboard payload valid: schema={d['schema_version']} matches={len(d['matches'])} status={d['status']}")
