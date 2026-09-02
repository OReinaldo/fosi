"""Build deterministic FOSI metrics from normalized evidence."""
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CFG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def metric(value, observed, total, unit=None, status=None):
    return {"value": value, "observed": observed, "total": total,
            "coverage": round(observed / total, 3) if total else 0,
            "unit": unit, "status": status or ("observed" if observed else "unavailable")}


def team_score(m, team):
    h, a, s = m.get("home_team") or {}, m.get("away_team") or {}, m.get("score") or {}
    if h.get("name") == team: return num(s.get("home")), num(s.get("away"))
    if a.get("name") == team: return num(s.get("away")), num(s.get("home"))
    return None, None


def owner(item):
    t = item.get("team")
    if isinstance(t, dict): return t.get("name") or t.get("longName") or t.get("id")
    return item.get("teamName") or item.get("team_name")


def match_id(item):
    for k in ("matchId", "match_id", "eventId", "event_id", "gameId"):
        if item.get(k) is not None: return str(item[k])
    return None


def xg(item):
    for k in ("xg", "expectedGoals", "expected_goals", "expectedGoal"):
        v = num(item.get(k))
        if v is not None: return v
    return None


def main():
    cfg = load(CFG)
    root = ROOT / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    src = root / "normalized" / "fosi.json"
    if not src.exists(): raise SystemExit("Normalized FOSI data not found")
    data, team = load(src), cfg["team"]
    matches = [m for m in data.get("matches", []) if m.get("score")]
    matches.sort(key=lambda m: m.get("date") or "", reverse=True)
    gf, ga, form = [], [], []
    for m in matches:
        f, a = team_score(m, team)
        if f is not None and a is not None:
            gf.append(f); ga.append(a); form.append("W" if f > a else "D" if f == a else "L")

    shots = data.get("shots", [])
    xgf, xga, by_match = [], [], defaultdict(lambda: {"for": 0.0, "against": 0.0, "for_shots": 0, "against_shots": 0})
    xg_observed = 0
    for shot in shots:
        v = xg(shot)
        if v is None: continue
        xg_observed += 1
        who, mid = owner(shot), match_id(shot)
        ours = who == team or str(who) == str((cfg.get("provider_ids") or {}).get("fotmob"))
        if ours:
            xgf.append(v)
            if mid: by_match[mid]["for"] += v; by_match[mid]["for_shots"] += 1
        elif who:
            xga.append(v)
            if mid: by_match[mid]["against"] += v; by_match[mid]["against_shots"] += 1

    n = len(matches)
    metrics = {
        "form": metric("".join(form[:5]) or None, min(5, len(form)), min(5, n), "result-code"),
        "goals_for": metric(sum(gf) if gf else None, len(gf), n, "goals"),
        "goals_against": metric(sum(ga) if ga else None, len(ga), n, "goals"),
        "goals_for_per_match": metric(round(sum(gf)/len(gf), 2) if gf else None, len(gf), n, "goals/match"),
        "goals_against_per_match": metric(round(sum(ga)/len(ga), 2) if ga else None, len(ga), n, "goals/match"),
        "xg": metric(round(sum(xgf), 2) if xgf else None, len(xgf), xg_observed, "goals"),
        "xga": metric(round(sum(xga), 2) if xga else None, len(xga), xg_observed, "goals"),
        "xg_per_match": metric(round(sum(xgf)/n, 2) if xgf and n else None, len(xgf), n, "goals/match", "derived" if xgf else None),
        "xga_per_match": metric(round(sum(xga)/n, 2) if xga and n else None, len(xga), n, "goals/match", "derived" if xga else None),
        "matches_sample": metric(n, n, n, "matches"),
        "players_count": metric(len(data.get("players", [])), len(data.get("players", [])), len(data.get("players", [])), "players"),
        "events_count": metric(len(data.get("events", [])), len(data.get("events", [])), len(data.get("events", [])), "events"),
        "shots_count": metric(len(shots), len(shots), len(shots), "shots"),
        "shots_with_xg": metric(xg_observed, xg_observed, len(shots), "shots"),
        "spatial_actions_count": metric(len(data.get("spatial_actions", [])), len(data.get("spatial_actions", [])), len(data.get("spatial_actions", [])), "actions"),
    }
    out = {
        "schema_version": "1.1", "model": "FOSI metrics",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"country": cfg["country"], "competition": cfg["competition"], "team": team, "team_id": cfg["team_id"]},
        "method": "deterministic-from-normalized", "source_normalized": str(src).replace("\\", "/"),
        "metrics": metrics, "xg_by_match": dict(by_match), "recent_matches": matches[:20],
        "coverage": {"normalized_records": sum(len(data.get(k, [])) for k in ("matches", "players", "events", "shots", "spatial_actions"))}
    }
    (root / "normalized" / "metrics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v["value"] for k, v in metrics.items()}, ensure_ascii=False))

if __name__ == "__main__": main()
