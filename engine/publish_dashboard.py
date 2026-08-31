"""Build the dashboard payload from verified match-detail files only.

Missing provider fields are represented as null; partial data must never break
an automated scouting run.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from intelligence import build_insights

ROOT = Path("data/scouting/poland/ekstraklasa/pogon-szczecin")
OUT = Path("dashboard/data.json")
TEAM = "Pogoń Szczecin"


def team_name(x):
    return (x or {}).get("name") or (x or {}).get("longName") or "—"


def number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def extract_xg(detail):
    stats = detail.get("content", {}).get("stats", {}).get("Periods", {}).get("All", {}).get("stats", [])
    for block in stats if isinstance(stats, list) else []:
        for item in block.get("stats", []) if isinstance(block, dict) else []:
            if item.get("key") in {"expected_goals", "xg"}:
                vals = item.get("stats")
                if isinstance(vals, list) and len(vals) >= 2:
                    return number(vals[0]), number(vals[1])
    return None, None


def extract_match(detail):
    general = detail.get("general", {}) if isinstance(detail, dict) else {}
    home, away = general.get("homeTeam", {}) or {}, general.get("awayTeam", {}) or {}
    facts = detail.get("content", {}).get("matchFacts", {}) or {}
    score = facts.get("score", {}) if isinstance(facts.get("score"), dict) else {}
    hg, ag = score.get("homeScore"), score.get("awayScore")
    if hg is None or ag is None:
        try:
            parts = str(score.get("scoreStr", "")).split("-")
            hg, ag = int(parts[0].strip()), int(parts[1].strip())
        except (ValueError, TypeError, IndexError):
            hg = ag = None
    hn, an = team_name(home), team_name(away)
    xgh, xga = extract_xg(detail)
    return {
        "id": detail.get("id") or facts.get("matchId"),
        "date": general.get("matchTimeUTC") or general.get("utcTime"),
        "home": hn, "away": an,
        "finished": bool(general.get("finished")),
        "score": f"{hg} - {ag}" if hg is not None and ag is not None else score.get("scoreStr"),
        "goals_for": hg if hn == TEAM else ag if an == TEAM else None,
        "goals_against": ag if hn == TEAM else hg if an == TEAM else None,
        "xg_for": xgh if hn == TEAM else xga if an == TEAM else None,
        "xg_against": xga if hn == TEAM else xgh if an == TEAM else None,
    }


def main():
    status = json.loads((ROOT / "status.json").read_text())
    raw = json.loads((ROOT / "raw_team.json").read_text())
    team = raw.get("team", raw) if isinstance(raw, dict) else {}
    matches = []
    for path in (ROOT / "matches").glob("*.json"):
        try:
            m = extract_match(json.loads(path.read_text()))
            if m.get("finished") and m.get("id") is not None:
                matches.append(m)
        except Exception:
            continue
    matches.sort(key=lambda m: m.get("date") or "", reverse=True)
    recent = matches[:10]
    gf = sum(m["goals_for"] for m in recent if isinstance(m.get("goals_for"), (int, float)))
    ga = sum(m["goals_against"] for m in recent if isinstance(m.get("goals_against"), (int, float)))
    xgf = [m["xg_for"] for m in recent if isinstance(m.get("xg_for"), (int, float))]
    xga = [m["xg_against"] for m in recent if isinstance(m.get("xg_against"), (int, float))]
    form = ''.join(
        'W' if m.get("goals_for") is not None and m.get("goals_against") is not None and m["goals_for"] > m["goals_against"]
        else 'D' if m.get("goals_for") is not None and m.get("goals_against") is not None and m["goals_for"] == m["goals_against"]
        else 'L' if m.get("goals_for") is not None and m.get("goals_against") is not None else '?'
        for m in recent[:5]
    ) or None
    metrics = {
        "form": form,
        "goals_for": gf if recent else None,
        "goals_against": ga if recent else None,
        "xg": round(sum(xgf) / len(xgf), 2) if xgf else None,
        "xga": round(sum(xga) / len(xga), 2) if xga else None,
        "matches_sample": len(recent),
    }
    insights = build_insights({"xg_for": metrics["xg"], "xg_against": metrics["xga"]})
    threat = round(max(0, min(100, 50 + (metrics["xg"] - metrics["xga"]) * 12))) if xgf and xga else None
    payload = {
        "schema_version": "0.6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "verified_partial" if recent else "awaiting_verified_ingestion",
        "team": {"id": "pogon-szczecin", "name": team.get("name") or TEAM, "competition": "Ekstraklasa", "country": "Poland"},
        "metrics": metrics,
        "matches": recent,
        "players": [],
        "threat_score": threat,
        "insights": insights,
        "data_quality": {"score": status.get("data_score", 0), "layers": status.get("layers", {}), "sample_matches": len(recent)},
        "sources": [{"provider": "FotMob", "type": "team + match details", "retrieved": datetime.now(timezone.utc).isoformat()}],
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
