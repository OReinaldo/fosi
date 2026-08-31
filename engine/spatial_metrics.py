"""Provider-agnostic spatial metric helpers for FOSI."""
from collections import defaultdict

def pct(n, d):
    return round(100 * n / d, 1) if d else None

def event_summary(events):
    out = defaultdict(int)
    for e in events or []:
        t = str(e.get("type") or e.get("eventType") or "").lower()
        out[t] += 1
    return dict(out)

def spatial_actions(events, action_types):
    rows = []
    for e in events or []:
        t = str(e.get("type") or e.get("eventType") or "").lower()
        if t not in action_types:
            continue
        x = e.get("x") if e.get("x") is not None else e.get("posX")
        y = e.get("y") if e.get("y") is not None else e.get("posY")
        if x is None or y is None:
            continue
        rows.append({"type": t, "x": x, "y": y, "player_id": e.get("playerId")})
    return rows

def pass_profile(passes):
    total = len(passes or [])
    good = sum(1 for p in passes or [] if p.get("accurate") is True or p.get("outcome") in {"complete", "successful"})
    return {"attempted": total, "successful": good, "success_pct": pct(good, total)}

def player_profiles(events):
    by_player = defaultdict(list)
    for e in events or []:
        if e.get("playerId") is not None:
            by_player[e["playerId"]].append(e)
    return {pid: {"events": len(es), "summary": event_summary(es)} for pid, es in by_player.items()}
