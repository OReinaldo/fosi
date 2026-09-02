"""Build deterministic FOSI metrics from normalized evidence.

The engine is deliberately conservative: it calculates only metrics for which
normalized records contain enough evidence. Missing data stays null and every
metric carries coverage/provenance metadata so the dashboard cannot confuse
observed values with estimates.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

CFG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")
OUT_NAME = "metrics.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def avg(values):
    vals = [float(v) for v in values if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 2) if vals else None


def metric(value, observed, source_records=None, unit=None):
    return {
        "value": value,
        "observed": observed,
        "unit": unit,
        "coverage": round(observed / source_records, 3) if source_records else 0,
    }


def infer_team_score(match, team):
    h, a = match.get("home_team", {}), match.get("away_team", {})
    score = match.get("score", {}) or {}
    if h.get("name") == team:
        return score.get("home"), score.get("away")
    if a.get("name") == team:
        return score.get("away"), score.get("home")
    return None, None


def numeric_from_raw(record, keys):
    for key in keys:
        value = record.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def main():
    cfg = load(CFG)
    root = ROOT / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    normalized_path = root / "normalized" / "fosi.json"
    if not normalized_path.exists():
        raise SystemExit("Normalized FOSI data not found; run normalize_sources.py first")
    data = load(normalized_path)
    matches = [m for m in data.get("matches", []) if m.get("score")]
    matches.sort(key=lambda m: m.get("date") or "", reverse=True)
    team = cfg["team"]

    gf, ga, xgf, xga = [], [], [], []
    for m in matches:
        f, a = infer_team_score(m, team)
        if isinstance(f, (int, float)) and isinstance(a, (int, float)):
            gf.append(f); ga.append(a)

    # xG is not guaranteed to be normalized yet. Search normalized shot/event
    # records conservatively for provider-native xG-like fields.
    shots = data.get("shots", [])
    for shot in shots:
        value = numeric_from_raw(shot, ("xg", "expectedGoals", "expected_goals", "expectedGoal"))
        if value is None:
            continue
        team_name = shot.get("teamName") or shot.get("team", {}).get("name") if isinstance(shot.get("team"), dict) else shot.get("teamName")
        if team_name == team:
            xgf.append(value)
        elif team_name:
            xga.append(value)

    recent = matches[:10]
    form = []
    for m in recent[:5]:
        f, a = infer_team_score(m, team)
        if isinstance(f, (int, float)) and isinstance(a, (int, float)):
            form.append("W" if f > a else "D" if f == a else "L")

    metrics = {
        "form": metric("".join(form) or None, len(form), min(5, len(matches)), "result-code"),
        "goals_for": metric(sum(gf) if gf else None, len(gf), len(matches), "goals"),
        "goals_against": metric(sum(ga) if ga else None, len(ga), len(matches), "goals"),
        "xg": metric(avg(xgf), len(xgf), len(shots), "goals") if shots else metric(None, 0, 0, "goals"),
        "xga": metric(avg(xga), len(xga), len(shots), "goals") if shots else metric(None, 0, 0, "goals"),
        "matches_sample": metric(len(matches), len(matches), len(matches), "matches"),
        "players_count": metric(len(data.get("players", [])), len(data.get("players", [])), len(data.get("players", [])), "players"),
        "events_count": metric(len(data.get("events", [])), len(data.get("events", [])), len(data.get("events", [])), "events"),
        "shots_count": metric(len(shots), len(shots), len(shots), "shots"),
        "spatial_actions_count": metric(len(data.get("spatial_actions", [])), len(data.get("spatial_actions", [])), len(data.get("spatial_actions", [])), "actions"),
    }

    bundle = {
        "schema_version": "1.0",
        "model": "FOSI metrics",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"country": cfg["country"], "competition": cfg["competition"], "team": cfg["team"], "team_id": cfg["team_id"]},
        "method": "deterministic-from-normalized",
        "source_normalized": str(normalized_path).replace("\\", "/"),
        "metrics": metrics,
        "coverage": {"normalized_records": sum(len(data.get(k, [])) for k in ("matches", "players", "events", "shots", "spatial_actions"))},
        "recent_matches": recent,
    }
    (root / "normalized" / OUT_NAME).write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print("FOSI metrics:", {k: v["value"] for k, v in metrics.items()})


if __name__ == "__main__":
    main()
