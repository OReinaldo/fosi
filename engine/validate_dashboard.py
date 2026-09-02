"""Validate the public FOSI payload and enforce evidence-first display data."""
import json
from pathlib import Path

p = Path("dashboard/data.json")
d = json.loads(p.read_text(encoding="utf-8"))
required = ["schema_version", "generated_at", "status", "team", "metrics", "metric_meta", "matches", "players", "data_quality", "sources"]
missing = [k for k in required if k not in d]
if missing: raise SystemExit(f"Missing dashboard fields: {', '.join(missing)}")
if not d["team"].get("id") or not d["team"].get("name"): raise SystemExit("Dashboard team identity is incomplete")
if not isinstance(d["matches"], list) or not isinstance(d["players"], list): raise SystemExit("matches/players must be arrays")
if not isinstance(d["data_quality"], dict) or not isinstance(d["sources"], list): raise SystemExit("Invalid data_quality/sources")
if not isinstance(d["metric_meta"], dict): raise SystemExit("metric_meta must be an object")
for key, meta in d["metric_meta"].items():
    if not isinstance(meta, dict): continue
    value, observed = meta.get("value"), meta.get("observed", 0)
    if value is not None and not isinstance(observed, (int, float)): raise SystemExit(f"Invalid observed count for metric: {key}")
    if observed == 0 and value is not None: raise SystemExit(f"Metric has value without evidence: {key}")
if d.get("threat_score") is not None: raise SystemExit("Threat score must remain null until evidence-backed")
print(f"FOSI dashboard payload valid: schema={d['schema_version']} team={d['team']['name']} matches={len(d['matches'])} status={d['status']}")
