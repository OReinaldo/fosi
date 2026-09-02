"""Build deterministic FOSI metrics from normalized evidence.

Evidence-first: every metric is either observed in normalized provider data or
explicitly marked derived/unavailable. No missing field is converted to zero.
"""
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CFG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def num(v):
    if isinstance(v, bool): return None
    if isinstance(v, (int, float)): return float(v)
    if isinstance(v, str):
        try: return float(v.replace(",", ".").replace("%", "").strip())
        except ValueError: return None
    return None


def metric(value, observed, total, unit=None, status=None, source=None):
    return {"value": value, "observed": observed, "total": total,
            "coverage": round(observed / total, 3) if total else 0,
            "unit": unit, "status": status or ("observed" if observed else "unavailable"), "source": source}


def walk_values(node):
    if isinstance(node, dict):
        yield node
        for v in node.values(): yield from walk_values(v)
    elif isinstance(node, list):
        for v in node: yield from walk_values(v)


def deep_value(item, keys):
    wanted = {k.lower() for k in keys}
    for obj in walk_values(item):
        for k, v in obj.items():
            if k.lower() in wanted and v is not None: return v
    return None


def deep_values(item, keys):
    wanted = {k.lower() for k in keys}; out = []
    for obj in walk_values(item):
        for k, v in obj.items():
            if k.lower() in wanted and v is not None:
                n = num(v)
                if n is not None: out.append(n)
    return out


def team_ids(cfg):
    ids = {str(cfg.get("team_id")), str((cfg.get("provider_ids") or {}).get("fotmob")), str((cfg.get("provider_ids") or {}).get("sofascore"))}
    return {x for x in ids if x and x != "None"}


def belongs_to_team(item, cfg):
    ids = team_ids(cfg); name = str(cfg["team"]).strip().lower()
    for obj in walk_values(item):
        for k, v in obj.items():
            kl = k.lower()
            if kl in {"teamname", "team_name", "team"}:
                if isinstance(v, dict):
                    if str(v.get("name", "")).strip().lower() == name or str(v.get("id")) in ids: return True
                elif str(v).strip().lower() == name or str(v) in ids: return True
            elif kl in {"teamid", "team_id"} and str(v) in ids: return True
    return False


def has_explicit_other_team(item, cfg):
    """Detect a provider team attribution that is explicitly not ours."""
    ids = team_ids(cfg); name = str(cfg["team"]).strip().lower(); found = False
    for obj in walk_values(item):
        for k, v in obj.items():
            if k.lower() in {"teamname", "team_name", "team", "teamid", "team_id"}:
                if isinstance(v, dict):
                    val_name, val_id = str(v.get("name", "")).strip().lower(), str(v.get("id"))
                    if val_name or val_id != "None":
                        found = True
                        if val_name == name or val_id in ids: return False
                else:
                    found = True
                    if str(v).strip().lower() == name or str(v) in ids: return False
    return found


def match_id(item):
    value = deep_value(item, ("matchId", "match_id", "eventId", "event_id", "gameId"))
    return str(value) if value is not None else None


def xg(item): return num(deep_value(item, ("xg", "expectedGoals", "expected_goals", "expectedGoal")))
def xgot(item): return num(deep_value(item, ("xgot", "expectedGoalsOnTarget", "expected_goals_on_target", "expectedGoalOnTarget")))
def stat_value(item, keys): return num(deep_value(item, keys))


def classify_shot(item):
    x = stat_value(item, ("x", "xcoord", "xCoordinate", "shotX")); y = stat_value(item, ("y", "ycoord", "yCoordinate", "shotY"))
    if x is None or y is None or not (0 <= x <= 100 and 0 <= y <= 100): return None
    central = 40 <= y <= 60
    if x >= 83: return "box-central" if central else "box-wide"
    if x >= 67: return "final-third-central" if central else "final-third-wide"
    return "middle-third" if central else "wide"


def team_score(m, cfg):
    h, a, s = m.get("home_team") or {}, m.get("away_team") or {}, m.get("score") or {}
    ids = team_ids(cfg); name = str(cfg["team"]).strip().lower()
    def is_ours(t): return str(t.get("id")) in ids or str(t.get("name", "")).strip().lower() == name
    if is_ours(h): return num(s.get("home")), num(s.get("away"))
    if is_ours(a): return num(s.get("away")), num(s.get("home"))
    return None, None


def result_for(m, cfg):
    f, a = team_score(m, cfg)
    return None if f is None or a is None else ("W" if f > a else "D" if f == a else "L")


def main():
    cfg = load(CFG); root = ROOT / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    src = root / "normalized" / "fosi.json"
    if not src.exists(): raise SystemExit("Normalized FOSI data not found")
    data, team = load(src), cfg["team"]
    matches = [m for m in data.get("matches", []) if isinstance(m.get("score"), dict)]
    matches.sort(key=lambda m: m.get("date") or "", reverse=True)
    gf, ga, form = [], [], []; match_metrics = {}
    for m in matches:
        mid = str(m.get("provider_id") or m.get("fosi_id")); f, a = team_score(m, cfg); r = result_for(m, cfg)
        if f is not None and a is not None: gf.append(f); ga.append(a); form.append(r)
        match_metrics[mid] = {"match_id": mid, "date": m.get("date"), "competition": m.get("competition"), "home_team": m.get("home_team"), "away_team": m.get("away_team"), "score": m.get("score"), "result": r, "goals_for": f, "goals_against": a}

    shots = data.get("shots", []); xgf=[]; xga=[]; xgot_for=[]; xgot_against=[]; shot_zones=defaultdict(int); shot_counts=defaultdict(lambda:{"for":0,"against":0}); xg_by_match=defaultdict(lambda:{"for":0.0,"against":0.0,"for_shots":0,"against_shots":0,"for_xgot":0.0,"against_xgot":0.0})
    xg_for_obs=xg_against_obs=xgot_for_obs=xgot_against_obs=0; attributed=0
    for shot in shots:
        ours = belongs_to_team(shot, cfg); other = has_explicit_other_team(shot, cfg)
        if not ours and not other: continue
        attributed += 1; mid = match_id(shot); bucket = xg_by_match[mid or "unknown"]; side = "for" if ours else "against"; shot_counts[mid or "unknown"][side] += 1
        if ours:
            zone=classify_shot(shot)
            if zone: shot_zones[zone]+=1
        xv=xg(shot)
        if xv is not None:
            if ours: xgf.append(xv); xg_for_obs+=1; bucket["for"]+=xv; bucket["for_shots"]+=1
            else: xga.append(xv); xg_against_obs+=1; bucket["against"]+=xv; bucket["against_shots"]+=1
        ov=xgot(shot)
        if ov is not None:
            if ours: xgot_for.append(ov); xgot_for_obs+=1; bucket["for_xgot"]+=ov
            else: xgot_against.append(ov); xgot_against_obs+=1; bucket["against_xgot"]+=ov

    event_specs={"passes":("pass","passes","successfulPasses","accuratePasses"),"recoveries":("recovery","recoveries","ballRecoveries"),"losses":("loss","losses","turnovers","possessionLost"),"tackles":("tackle","tackles"),"interceptions":("interception","interceptions"),"duels":("duel","duels"),"final_third_entries":("finalThirdEntries","final_third_entries","entriesFinalThird"),"possession":("possession","possessionPercent","possessionPercentage"),"corners":("corners","corner"),"free_kicks":("freeKicks","free_kicks")}
    event_counts={}
    events=data.get("events", [])
    for name,keys in event_specs.items():
        vals=[]
        for e in events:
            if belongs_to_team(e,cfg): vals.extend(deep_values(e,keys))
        event_counts[name]=vals

    n=len(matches)
    def total_metric(values, unit): return metric(round(sum(values),2) if values else None, len(values), n, unit, "observed" if values else None)
    metrics={
      "form":metric("".join(form[:5]) or None,min(5,len(form)),min(5,n),"result-code"),
      "goals_for":metric(sum(gf) if gf else None,len(gf),n,"goals"),"goals_against":metric(sum(ga) if ga else None,len(ga),n,"goals"),
      "goals_for_per_match":metric(round(sum(gf)/len(gf),2) if gf else None,len(gf),n,"goals/match","derived" if gf else None),"goals_against_per_match":metric(round(sum(ga)/len(ga),2) if ga else None,len(ga),n,"goals/match","derived" if ga else None),
      "xg":metric(round(sum(xgf),2) if xgf else None,xg_for_obs,len(shots),"goals"),"xga":metric(round(sum(xga),2) if xga else None,xg_against_obs,len(shots),"goals"),
      "xgot":metric(round(sum(xgot_for),2) if xgot_for else None,xgot_for_obs,len(shots),"goals"),"xgot_against":metric(round(sum(xgot_against),2) if xgot_against else None,xgot_against_obs,len(shots),"goals"),
      "xg_per_match":metric(round(sum(xgf)/n,2) if xgf and n else None,xg_for_obs,n,"goals/match","derived" if xgf else None),"xga_per_match":metric(round(sum(xga)/n,2) if xga and n else None,xg_against_obs,n,"goals/match","derived" if xga else None),
      "shots_count":metric(len(shots) or None,len(shots),len(shots),"shots"),"shots_with_xg":metric(xg_for_obs+xg_against_obs if xg_for_obs+xg_against_obs else None,xg_for_obs+xg_against_obs,len(shots),"shots"),
      "shots_for":metric(sum(v["for"] for v in shot_counts.values()) or None,sum(v["for"]>0 for v in shot_counts.values()),n,"shots"),"shots_against":metric(sum(v["against"] for v in shot_counts.values()) or None,sum(v["against"]>0 for v in shot_counts.values()),n,"shots"),
      "matches_sample":metric(n,n,n,"matches"),"players_count":metric(len(data.get("players",[])) or None,len(data.get("players",[])),len(data.get("players",[])),"players"),"events_count":metric(len(events) or None,len(events),len(events),"events"),"spatial_actions_count":metric(len(data.get("spatial_actions",[])) or None,len(data.get("spatial_actions",[])),len(data.get("spatial_actions",[])),"actions")}
    for name,vals in event_counts.items(): metrics[name]=metric(round(sum(vals),2) if vals else None,len(vals),len(events),"provider-unit","observed" if vals else None)
    for mid,row in xg_by_match.items():
        if mid in match_metrics: match_metrics[mid].update({"xg":round(row["for"],3),"xga":round(row["against"],3),"xgot":round(row["for_xgot"],3),"xgot_against":round(row["against_xgot"],3),"shots_for":row["for_shots"],"shots_against":row["against_shots"]})
    out={"schema_version":"1.3","model":"FOSI metrics","generated_at":datetime.now(timezone.utc).isoformat(),"scope":{"country":cfg["country"],"competition":cfg["competition"],"team":team,"team_id":cfg["team_id"]},"method":"deterministic-from-normalized","source_normalized":str(src).replace("\\","/"),"metrics":metrics,"xg_by_match":dict(xg_by_match),"match_metrics":list(match_metrics.values()),"shot_zones_for":dict(shot_zones),"recent_matches":matches[:20],"coverage":{"normalized_records":sum(len(data.get(k,[])) for k in ("matches","players","events","shots","spatial_actions")),"attributed_shots":attributed}}
    (root/"normalized"/"metrics.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps({k:v["value"] for k,v in metrics.items()},ensure_ascii=False))

if __name__ == "__main__": main()
