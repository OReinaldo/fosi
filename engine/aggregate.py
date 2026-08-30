"""Build dashboard-ready aggregates without inventing unavailable metrics."""
from statistics import mean

def aggregate_matches(matches):
    finished = [m for m in matches if m.get("status", {}).get("finished")]
    gf, ga = [], []
    for m in finished:
        h, a = m.get("home", {}), m.get("away", {})
        hs, aws = h.get("score"), a.get("score")
        if not isinstance(hs, (int,float)) or not isinstance(aws, (int,float)):
            continue
        if m.get("team_side") == "home": gf.append(hs); ga.append(aws)
        elif m.get("team_side") == "away": gf.append(aws); ga.append(hs)
    return {
        "matches": len(finished),
        "goals_for": sum(gf) if gf else None,
        "goals_against": sum(ga) if ga else None,
        "goals_for_avg": round(mean(gf), 2) if gf else None,
        "goals_against_avg": round(mean(ga), 2) if ga else None,
    }
