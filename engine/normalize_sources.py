"""Normalize FOSI RAW provider data into a stable, evidence-first model.

The normalizer is intentionally conservative: it maps only fields that are
actually present in RAW, preserves provider identifiers, records provenance,
and uses null for missing values. Provider-native payloads remain untouched.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def first(d: dict, *keys, default=None):
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return default


def as_list(value):
    if isinstance(value, list):
        return value
    return []


def find_lists(node: Any, wanted: set[str], found=None):
    """Find list-valued keys anywhere in a provider response."""
    found = found if found is not None else {}
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() in wanted and isinstance(v, list):
                found.setdefault(k.lower(), v)
            find_lists(v, wanted, found)
    elif isinstance(node, list):
        for v in node[:3]:
            find_lists(v, wanted, found)
    return found


def source_meta(source: str, raw_path: str, provider_id: Any = None):
    return {
        "source": source,
        "raw_path": raw_path,
        "provider_id": str(provider_id) if provider_id is not None else None,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_match(payload: dict, raw_path: str, source: str):
    general = payload.get("general") or {}
    header = payload.get("header") or {}
    home = header.get("teams", {}).get("home") or header.get("homeTeam") or {}
    away = header.get("teams", {}).get("away") or header.get("awayTeam") or {}
    if not home and isinstance(header.get("homeTeam"), dict):
        home = header["homeTeam"]
    if not away and isinstance(header.get("awayTeam"), dict):
        away = header["awayTeam"]

    match_id = first(general, "matchId", "id")
    if match_id is None:
        return None
    home_score = first(home, "score", "goals")
    away_score = first(away, "score", "goals")
    teams = header.get("teams") if isinstance(header.get("teams"), dict) else {}
    if not home and teams:
        home = teams.get("home") or {}
    if not away and teams:
        away = teams.get("away") or {}

    result = None
    if isinstance(home_score, (int, float)) and isinstance(away_score, (int, float)):
        result = "D" if home_score == away_score else "W" if home_score > away_score else "L"

    return {
        "fosi_id": f"match:{source}:{match_id}",
        "provider": source,
        "provider_id": str(match_id),
        "date": first(general, "matchTime", "utcTime", "date", "startTime"),
        "competition": first(general, "leagueName", "competitionName"),
        "round": first(general, "matchRound", "round"),
        "home_team": {"id": first(home, "id", "teamId"), "name": first(home, "name", "longName")},
        "away_team": {"id": first(away, "id", "teamId"), "name": first(away, "name", "longName")},
        "score": {"home": home_score, "away": away_score},
        "result_for_home": result,
        "source_meta": source_meta(source, raw_path, match_id),
    }


def normalize_players(payload: dict, raw_path: str, source: str):
    result = []
    lists = find_lists(payload, {"players", "lineup", "lineups", "playerdata"})
    seen = set()
    for values in lists.values():
        for p in values:
            if not isinstance(p, dict):
                continue
            pid = first(p, "id", "playerId", "player_id")
            name = first(p, "name", "playerName", "fullName")
            if pid is None and name is None:
                continue
            key = str(pid or name)
            if key in seen:
                continue
            seen.add(key)
            result.append({
                "fosi_id": f"player:{source}:{key}",
                "provider": source,
                "provider_id": str(pid) if pid is not None else None,
                "name": name,
                "position": first(p, "position", "role", "positionName"),
                "team_id": first(p, "teamId", "team_id"),
                "source_meta": source_meta(source, raw_path, pid),
            })
    return result


def normalize_event_like(payload: dict, raw_path: str, source: str):
    """Conservative extraction of shots/incidents/events when provider exposes them."""
    out = {"shots": [], "events": [], "spatial_actions": []}
    lists = find_lists(payload, {"shotmap", "shots", "incidents", "events", "passes"})
    for key, values in lists.items():
        for item in values:
            if not isinstance(item, dict):
                continue
            iid = first(item, "id", "eventId", "shotId")
            record = dict(item)
            record["fosi_id"] = f"{key}:{source}:{iid}" if iid is not None else None
            record["provider"] = source
            record["provider_id"] = str(iid) if iid is not None else None
            record["source_meta"] = source_meta(source, raw_path, iid)
            if key in {"shotmap", "shots"}:
                out["shots"].append(record)
            elif key == "passes":
                out["spatial_actions"].append(record)
            else:
                out["events"].append(record)
    return out


def normalize_file(payload: dict, raw_path: str, source: str):
    match = normalize_match(payload, raw_path, source)
    players = normalize_players(payload, raw_path, source)
    event_data = normalize_event_like(payload, raw_path, source)
    return match, players, event_data


def main():
    cfg = load(CONFIG)
    root = ROOT / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    raw_root = root / "raw"
    out_root = root / "normalized"
    out_root.mkdir(parents=True, exist_ok=True)

    matches, players, events, shots, spatial = [], [], [], [], []
    records = 0
    for path in sorted(raw_root.rglob("*.json")) if raw_root.exists() else []:
        if "source-status" in path.name or path.name.startswith("status-"):
            continue
        try:
            payload = load(path)
        except Exception:
            continue
        source = path.relative_to(raw_root).parts[0]
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        match, ps, ev = normalize_file(payload, rel, source)
        if match:
            matches.append(match)
        players.extend(ps)
        events.extend(ev["events"])
        shots.extend(ev["shots"])
        spatial.extend(ev["spatial_actions"])
        records += 1

    # Stable de-duplication across team and match responses.
    def dedupe(rows):
        seen = set(); out = []
        for row in rows:
            key = row.get("fosi_id") or json.dumps(row, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key); out.append(row)
        return out

    bundle = {
        "schema_version": "1.0",
        "model": "FOSI normalized",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"country": cfg["country"], "competition": cfg["competition"], "team": cfg["team"], "team_id": cfg["team_id"]},
        "method": "normalized-from-raw",
        "counts": {},
        "matches": dedupe(matches),
        "players": dedupe(players),
        "events": dedupe(events),
        "shots": dedupe(shots),
        "spatial_actions": dedupe(spatial),
    }
    bundle["counts"] = {k: len(bundle[k]) for k in ("matches", "players", "events", "shots", "spatial_actions")}
    (out_root / "fosi.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FOSI normalized: {records} RAW files -> {bundle['counts']}")


if __name__ == "__main__":
    main()
