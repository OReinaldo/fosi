"""Normalize FOSI RAW provider data into a stable, evidence-first model."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")
PLAYER_FIELDS = {
    "minutes": ("minutes", "minsPlayed", "minutesPlayed", "minutes_played"), "starts": ("starts", "started"),
    "appearances": ("appearances", "apps", "appearancesTotal"), "goals": ("goals", "goalsTotal"),
    "assists": ("assists", "assistsTotal"), "rating": ("rating", "avgRating", "averageRating"),
    "shots": ("shots", "shotsTotal", "totalShots"), "shots_on_target": ("shotsOnTarget", "shotsOnTargetTotal", "shots_on_target"),
    "xg": ("xg", "expectedGoals", "expected_goals"), "xgot": ("xgot", "expectedGoalsOnTarget", "expected_goals_on_target"),
    "key_passes": ("keyPasses", "keyPassesTotal", "key_passes", "chances_created"), "passes": ("passes", "totalPasses", "total_passes"),
    "accurate_passes": ("accuratePasses", "passesAccurate", "accurate_passes"), "tackles": ("tackles", "tacklesTotal"),
    "interceptions": ("interceptions", "interceptionsTotal"), "duels": ("duels", "duelsTotal"),
    "recoveries": ("recoveries", "ballRecoveries"), "turnovers": ("turnovers", "possessionLost", "dispossessed"),
    "fouls": ("fouls", "foulsCommitted"), "yellow_cards": ("yellowCards", "yellowCard"),
    "red_cards": ("redCards", "redCard"), "touches": ("touches",), "touches_opp_box": ("touches_opp_box",),
    "final_third_entries": ("passes_into_final_third", "finalThirdEntries", "final_third_entries"),
    "clearances": ("clearances",), "blocks": ("shot_blocks",), "defensive_actions": ("defensive_actions",),
}
SUM_FIELDS = {k for k in PLAYER_FIELDS if k not in {"rating"}}


def load(path: Path) -> Any: return json.loads(path.read_text(encoding="utf-8"))
def first(d: dict, *keys, default=None):
    if not isinstance(d, dict): return default
    for key in keys:
        if key in d and d[key] is not None: return d[key]
    return default

def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values(): yield from walk(v)
    elif isinstance(node, list):
        for v in node: yield from walk(v)

def deep_first(node, keys):
    wanted = {k.lower() for k in keys}
    for obj in walk(node):
        for k, v in obj.items():
            if k.lower() in wanted and v is not None: return v
    return None

def find_lists(node: Any, wanted: set[str], found=None):
    found = found if found is not None else {}
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() in wanted and isinstance(v, list): found.setdefault(k.lower(), []).extend(v)
            find_lists(v, wanted, found)
    elif isinstance(node, list):
        for v in node: find_lists(v, wanted, found)
    return found

def all_list_items(node):
    if isinstance(node, dict):
        for v in node.values():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict): yield item
                    yield from all_list_items(item)
            else: yield from all_list_items(v)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, dict): yield item
            yield from all_list_items(item)

def source_meta(source, raw_path, provider_id=None):
    return {"source": source, "raw_path": raw_path, "provider_id": str(provider_id) if provider_id is not None else None, "retrieved_at": datetime.now(timezone.utc).isoformat()}

def team_from_payload(payload, side):
    wanted = {f"{side}team", f"{side}_team"}
    for obj in walk(payload):
        for k, v in obj.items():
            if k.lower() in wanted:
                if isinstance(v, dict): return v
                if isinstance(v, list):
                    idx = 0 if side == "home" else 1
                    if len(v) > idx and isinstance(v[idx], dict): return v[idx]
    return {}

def parse_match_name(value):
    if not isinstance(value, str) or "-vs-" not in value: return None, None, None
    pair, *rest = value.split("_", 1); home, away = pair.split("-vs-", 1)
    return home.strip(), away.strip(), rest[0] if rest else None

def score_from_header(payload, side):
    for obj in walk(payload):
        teams = obj.get("teams") if isinstance(obj, dict) else None
        if isinstance(teams, list) and len(teams) >= 2 and all(isinstance(x, dict) for x in teams[:2]):
            idx = 0 if side == "home" else 1; v = first(teams[idx], "score", "goals")
            if isinstance(v, (int, float)) and not isinstance(v, bool): return v
    return None

def numeric_score(payload, side):
    v = score_from_header(payload, side)
    if v is not None: return v
    keys = ("homeScore", "scoreHome", "homeGoals", "home_score", "goalsHome") if side == "home" else ("awayScore", "scoreAway", "awayGoals", "away_score", "goalsAway")
    value = deep_first(payload, keys)
    if isinstance(value, dict): value = first(value, "display", "value", "score", "goals", "current")
    if isinstance(value, str):
        m = re.search(r"-?\d+(?:\.\d+)?", value)
        if m:
            try: return int(float(m.group(0)))
            except ValueError: pass
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

def normalize_match(payload, raw_path, source):
    general = payload.get("general") or {}; mid = first(general, "matchId", "id") or deep_first(payload, ("matchId", "match_id"))
    if mid is None: return None
    home, away = team_from_payload(payload, "home"), team_from_payload(payload, "away")
    match_name = first(general, "matchName", "name") or deep_first(payload, ("matchName",)); parsed_home, parsed_away, parsed_date = parse_match_name(match_name)
    home_name = first(home, "name", "longName", "teamName") or parsed_home; away_name = first(away, "name", "longName", "teamName") or parsed_away
    hs = first(home, "score", "goals"); ass = first(away, "score", "goals"); hs = numeric_score(payload, "home") if hs is None else hs; ass = numeric_score(payload, "away") if ass is None else ass
    result = ("D" if isinstance(hs, (int, float)) and isinstance(ass, (int, float)) and hs == ass else "W" if isinstance(hs, (int, float)) and isinstance(ass, (int, float)) and hs > ass else "L" if isinstance(hs, (int, float)) and isinstance(ass, (int, float)) else None)
    date = first(general, "matchTimeUTCDate", "matchTime", "utcTime", "date", "startTime") or parsed_date; competition = first(general, "leagueName", "competitionName") or deep_first(payload, ("leagueName", "competitionName"))
    return {"fosi_id": f"match:{source}:{mid}", "provider": source, "provider_id": str(mid), "date": date, "competition": competition, "round": first(general, "matchRound", "round", "leagueRoundName"), "home_team": {"id": first(home, "id", "teamId"), "name": home_name}, "away_team": {"id": first(away, "id", "teamId"), "name": away_name}, "score": {"home": hs, "away": ass}, "result_for_home": result, "source_meta": source_meta(source, raw_path, mid)}

def player_stats(p):
    stats = {}
    for canonical, aliases in PLAYER_FIELDS.items():
        v = deep_first(p, aliases)
        if isinstance(v, (int, float)) and not isinstance(v, bool): stats[canonical] = v
        elif isinstance(v, str):
            try: stats[canonical] = float(v.replace(",", ".").replace("%", ""))
            except ValueError: pass
    for obj in walk(p):
        if not isinstance(obj, dict): continue
        for label, entry in obj.items():
            if not isinstance(entry, dict) or not isinstance(entry.get("stat"), dict): continue
            stat = entry["stat"]; value = stat.get("value")
            if not isinstance(value, (int, float)) or isinstance(value, bool): continue
            candidates = {str(entry.get("key") or "").lower(), re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")}
            for canonical, aliases in PLAYER_FIELDS.items():
                if any(c == a.lower() for c in candidates for a in aliases): stats[canonical] = value; break
    return stats

def player_candidate(p, target_team_id, allow_unassigned=False):
    if not isinstance(p, dict): return False
    pid, name = first(p, "id", "playerId", "player_id"), first(p, "name", "playerName", "fullName")
    if pid is None or not name: return False
    if any(k in p for k in ("reactKey", "eventId", "timeStr", "overloadTime", "newScore")): return False
    tid = first(p, "teamId", "team_id")
    if tid is not None and str(tid) != str(target_team_id): return False
    return tid is not None or allow_unassigned

def normalize_players(payload, raw_path, source, target_team_id):
    candidates = []
    if raw_path.endswith("/team.json"):
        # Current squad only; the same payload also contains historical/stat leaderboards.
        squad = ((payload.get("squad") or {}).get("squad") if isinstance(payload.get("squad"), dict) else None)
        if isinstance(squad, list):
            for group in squad:
                if isinstance(group, dict): candidates.extend(group.get("members") or [])
    else:
        candidates.extend(all_list_items(payload))
    rows = {}
    for p in candidates:
        if not player_candidate(p, target_team_id, allow_unassigned=False): continue
        pid = str(first(p, "id", "playerId", "player_id")); stats = player_stats(p)
        row = rows.get(pid)
        if row is None:
            rows[pid] = {"fosi_id": f"player:{source}:{pid}", "provider": source, "provider_id": pid, "name": first(p, "name", "playerName", "fullName"), "position": first(p, "position", "role", "positionName"), "team_id": first(p, "teamId", "team_id"), "stats": stats, "source_meta": source_meta(source, raw_path, pid)}
        else:
            for k, v in stats.items():
                if k in SUM_FIELDS and isinstance(v, (int, float)):
                    row["stats"][k] = row["stats"].get(k, 0) + v
                elif k not in row["stats"]: row["stats"][k] = v
            if row.get("position") is None: row["position"] = first(p, "position", "role", "positionName")
    return list(rows.values())

def normalize_event_like(payload, raw_path, source):
    out = {"shots": [], "events": [], "spatial_actions": []}; lists = find_lists(payload, {"shotmap", "shots", "incidents", "events", "passes"}); mid = deep_first(payload, ("matchId", "match_id"))
    for key, values in lists.items():
        for item in values:
            if not isinstance(item, dict): continue
            iid = first(item, "id", "eventId", "shotId"); target = key if key in out else "events"; index = len(out[target]); record = dict(item); record["fosi_id"] = f"{key}:{source}:{iid}" if iid is not None else f"{key}:{source}:{mid}:{index}"; record["provider"] = source; record["provider_id"] = str(iid) if iid is not None else None; record["match_id"] = str(mid) if mid is not None else None; record["source_meta"] = source_meta(source, raw_path, iid)
            if key in {"shotmap", "shots"}: out["shots"].append(record)
            elif key == "passes": out["spatial_actions"].append(record)
            else: out["events"].append(record)
    return out

def normalize_file(payload, raw_path, source, target_team_id): return normalize_match(payload, raw_path, source), normalize_players(payload, raw_path, source, target_team_id), normalize_event_like(payload, raw_path, source)

def main():
    cfg = load(CONFIG); root = ROOT / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]; raw_root, out_root = root / "raw", root / "normalized"; out_root.mkdir(parents=True, exist_ok=True)
    matches, players, events, shots, spatial = [], [], [], [], []; records = 0
    target_ids = set(str(x) for x in [cfg.get("team_id"), (cfg.get("provider_ids") or {}).get("fotmob"), (cfg.get("provider_ids") or {}).get("sofascore")] if x is not None)
    target_team_id = next(iter(target_ids - {str(cfg.get("team_id"))}), cfg.get("team_id"))
    for path in sorted(raw_root.rglob("*.json")) if raw_root.exists() else []:
        if "source-status" in path.name or path.name.startswith("status-"): continue
        try: payload = load(path)
        except Exception: continue
        source = path.relative_to(raw_root).parts[0]; rel = str(path.relative_to(ROOT)).replace("\\", "/"); match, ps, ev = normalize_file(payload, rel, source, target_team_id)
        if match: matches.append(match)
        players.extend(ps); events.extend(ev["events"]); shots.extend(ev["shots"]); spatial.extend(ev["spatial_actions"]); records += 1
    def dedupe(rows):
        seen, out = set(), []
        for row in rows:
            key = row.get("fosi_id") or json.dumps(row, sort_keys=True, ensure_ascii=False)
            if key not in seen: seen.add(key); out.append(row)
        return out
    bundle = {"schema_version": "1.5", "model": "FOSI normalized", "generated_at": datetime.now(timezone.utc).isoformat(), "scope": {"country": cfg["country"], "competition": cfg["competition"], "team": cfg["team"], "team_id": cfg["team_id"]}, "method": "normalized-from-raw", "counts": {}, "matches": dedupe(matches), "players": dedupe(players), "events": dedupe(events), "shots": dedupe(shots), "spatial_actions": dedupe(spatial)}
    bundle["counts"] = {k: len(bundle[k]) for k in ("matches", "players", "events", "shots", "spatial_actions")}; (out_root / "fosi.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"); print(f"FOSI normalized: {records} RAW files -> {bundle['counts']}")

if __name__ == "__main__": main()
