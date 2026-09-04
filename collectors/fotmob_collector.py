"""FOSI FotMob collector with all-competition match backfill and raw preservation."""
import json
import urllib.parse
import urllib.request
import time
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

BASE = "https://www.fotmob.com/api/data"
CONFIG = Path("config/selected-scout.json")
ROOT_BASE = Path("data/scouting")

def get_json(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0 FOSI/1.1", "Accept": "application/json", "Referer": "https://www.fotmob.com/"})
    with urllib.request.urlopen(req, timeout=45) as response: return json.load(response)

def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def resolve_team(name):
    data = get_json("/search/suggest?term=" + urllib.parse.quote(name) + "&hits=50&lang=en"); exact = fallback = None
    for item in data.get("suggestions", data.get("results", [])):
        typ = item.get("type") or item.get("entityType"); ent = item.get("entity") or item
        if typ in {"team", "teams"}:
            n = ent.get("name") or ent.get("title") or ""; tid = ent.get("id")
            if n.lower() == name.lower(): exact = str(tid); break
            if name.lower() in n.lower(): fallback = str(tid)
    return exact or fallback, data

def walk_matches(node):
    out = []
    if isinstance(node, dict):
        if {"id", "home", "away"}.issubset(node) and isinstance(node["home"], dict) and isinstance(node["away"], dict): out.append(node)
        for value in node.values(): out.extend(walk_matches(value))
    elif isinstance(node, list):
        for value in node: out.extend(walk_matches(value))
    return out

def finished(match):
    status = match.get("status") or {}; return bool(status.get("finished") or (status.get("reason") or {}).get("short") in {"FT", "AET", "PEN"})

def team_match(match, name, team_id):
    home = match.get("home") or {}; away = match.get("away") or {}
    if str(home.get("id")) == str(team_id) or str(away.get("id")) == str(team_id): return True
    return any(name.lower() in str(x).lower() for x in (home.get("name"), home.get("longName"), away.get("name"), away.get("longName")) if x)

def find_first(node, keys):
    wanted = {k.lower() for k in keys}
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in wanted and isinstance(value, str) and value.strip(): return value
            found = find_first(value, keys)
            if found: return found
    elif isinstance(node, list):
        for value in node:
            found = find_first(value, keys)
            if found: return found
    return None

def collect_team_player_ids(node, team_id, out=None):
    out = out if out is not None else set()
    if isinstance(node, dict):
        tid = node.get("teamId", node.get("team_id")); pid = node.get("playerId", node.get("player_id"))
        if pid is None and "id" in node and any(k in node for k in ("name", "fullName", "playerName")): pid = node.get("id")
        if pid is not None and tid is not None and str(tid) == str(team_id): out.add(str(pid))
        for value in node.values(): collect_team_player_ids(value, team_id, out)
    elif isinstance(node, list):
        for value in node: collect_team_player_ids(value, team_id, out)
    return out

def try_player_matches(pid, league_id):
    attempts = [f"/playerMatches?playerId={urllib.parse.quote(str(pid))}"]
    if league_id: attempts.append(f"/playerMatches?playerId={urllib.parse.quote(str(pid))}&parentLeagueId={urllib.parse.quote(str(league_id))}")
    last = None
    for path in attempts:
        try: return get_json(path), path
        except Exception as exc: last = exc
    raise last

def date_scan_matches(team_name, team_id, start_day, end_day):
    found = {}; day = start_day
    while day <= end_day:
        try:
            payload = get_json(f"/matches?date={day.strftime('%Y%m%d')}&ccode3=POL")
            for match in walk_matches(payload):
                if team_match(match, team_name, team_id): found[str(match["id"])] = match
        except Exception:
            pass
        day += timedelta(days=1); time.sleep(.05)
    return found

def extract_video_assets(payload, match_id):
    """Return source-provided video/highlight links without inventing timestamps."""
    found = []
    seen = set()
    def walk(node, path=""):
        if isinstance(node, dict):
            url = node.get("url") or node.get("videoUrl") or node.get("videoURL") or node.get("embedUrl") or node.get("embedURL")
            source = node.get("source") or node.get("provider") or node.get("site")
            image = node.get("image") or node.get("thumbnail") or node.get("thumbnailUrl")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                low = (url + " " + str(source or "") + " " + path).lower()
                if any(x in low for x in ("youtube", "youtu.be", "vimeo", "video", "highlight", "stream")):
                    key = url
                    if key not in seen:
                        seen.add(key); found.append({"match_id": str(match_id), "url": url, "source": source, "thumbnail": image, "asset_type": "highlight" if "highlight" in low else "video", "raw_path": path})
            for k, v in node.items(): walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node): walk(v, f"{path}[{i}]")
    walk(payload)
    return found

def event_video_refs(events, videos):
    """Link match-level video assets to known event times when no provider timestamp exists.

    We deliberately keep the relation as match_highlight rather than pretending the video
    starts at a particular event. Future provider-specific timestamp metadata can refine it.
    """
    refs=[]
    for video in videos:
        for event in events:
            eid = event.get("id") or event.get("eventId")
            if eid is not None:
                refs.append({"event_id": str(eid), "match_id": str(event.get("matchId") or video.get("match_id")), "video_url": video["url"], "relation": "match_highlight", "source": video.get("source")})
    return refs

def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")); status = {"source": "fotmob", "status": "collecting", "retrieved_at": datetime.now(timezone.utc).isoformat(), "layers": {}, "records": {}, "errors": []}
    if not cfg.get("enabled") or not cfg.get("team"): return
    root = ROOT_BASE / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]; raw = root / "raw" / "fotmob"; raw.mkdir(parents=True, exist_ok=True)
    try:
        tid = str((cfg.get("provider_ids") or {}).get("fotmob") or "")
        if not tid: tid, search = resolve_team(cfg["team"]); save(raw / "search.json", search)
        if not tid: raise RuntimeError("FotMob team id could not be resolved")
        team = get_json(f"/teams?id={tid}&ccode3=POL"); save(raw / "team.json", team); status["layers"].update({"team": "available", "players": "available"}); status["records"]["team"] = 1; status["team_id"] = tid
        league_id = str((cfg.get("provider_competition_ids") or {}).get("fotmob") or ("196" if cfg.get("competition") == "Ekstraklasa" else "")); season = str(cfg.get("season") or "2026/2027")
        if league_id:
            try: league = get_json(f"/leagues?id={league_id}&season={urllib.parse.quote(season)}&ccode3=POL"); save(raw / "league.json", league); status["layers"]["competition"] = "available"; status["records"]["league"] = 1
            except Exception as exc: status["errors"].append({"league_error": str(exc)})
        player_ids = sorted(collect_team_player_ids(team, tid)); profile_count = history_count = history_existing = 0
        for pid in player_ids[:40]:
            try:
                pp = raw / "players" / (pid + ".json")
                if not pp.exists(): save(pp, get_json(f"/playerData?id={pid}&includeMarketValues=true"))
                profile_count += 1
            except Exception as exc: status["errors"].append({"player_id": pid, "player_error": str(exc)})
            try:
                ph = raw / "player-matches" / (pid + ".json")
                if ph.exists(): history_existing += 1
                else: data, _ = try_player_matches(pid, league_id); save(ph, data); history_count += 1
            except Exception as exc: status["errors"].append({"player_id": pid, "player_matches_error": str(exc)})
        status["records"].update({"player_profiles": profile_count, "player_matches": history_count, "player_matches_skipped_existing": history_existing})
        try: save(raw / "transfers.json", get_json(f"/transfers?teamId={tid}")); status["records"]["transfers"] = 1
        except Exception as exc: status["errors"].append({"transfers_error": str(exc)})
        matches = {str(m["id"]): m for m in walk_matches(team) if team_match(m, cfg["team"], tid)}
        calendar_file = raw / "all-competition-calendar.json"
        try:
            season_start = date(int(season[:4]), 7, 1); today = datetime.now(timezone.utc).date(); initial = not calendar_file.exists(); scan_start = season_start if initial else today - timedelta(days=7); scan_end = today + timedelta(days=30)
            scanned = date_scan_matches(cfg["team"], tid, scan_start, scan_end); matches.update(scanned)
            save(calendar_file, {"team_id": tid, "from": scan_start.isoformat(), "to": scan_end.isoformat(), "matches": sorted(matches.values(), key=lambda x: str((x.get("status") or {}).get("utcTime") or ""))})
            status["records"].update({"date_scanned_matches": len(scanned), "date_scan_from": scan_start.isoformat(), "date_scan_to": scan_end.isoformat()})
        except Exception as exc: status["errors"].append({"calendar_scan_error": str(exc)})
        matches = sorted(matches.values(), key=lambda m: str((m.get("status") or {}).get("utcTime") or m.get("timeTS") or ""), reverse=True); status["layers"]["matches"] = "available" if matches else "pending"; status["records"]["matches"] = len(matches)
        detail = skipped = heatmaps = tickers = videos_count = event_video_refs_count = 0; errors = []
        for match in matches:
            mid = str(match["id"]); detail_path = raw / "matches" / (mid + ".json")
            try:
                if detail_path.exists(): detail_payload = json.loads(detail_path.read_text(encoding="utf-8")); skipped += 1
                else: detail_payload = get_json(f"/matchDetails?matchId={mid}"); save(detail_path, detail_payload); detail += 1
                videos = extract_video_assets(detail_payload, mid)
                vp = raw / "videos" / (mid + ".json")
                if videos and not vp.exists(): save(vp, {"match_id": mid, "videos": videos}); videos_count += len(videos)
                elif vp.exists():
                    try: videos_count += len((json.loads(vp.read_text(encoding="utf-8")) or {}).get("videos", []))
                    except Exception: pass
                if videos:
                    events = ((detail_payload.get("content") or {}).get("matchFacts") or {}).get("events") or []
                    refs = event_video_refs(events if isinstance(events, list) else [], videos)
                    if refs: save(raw / "videos" / (mid + "-event-refs.json"), {"match_id": mid, "refs": refs}); event_video_refs_count += len(refs)
                heatmap_url = find_first(detail_payload, ("heatmapUrl", "heatmapURL"))
                if heatmap_url:
                    hp = raw / "heatmaps" / (mid + ".json")
                    if not hp.exists(): save(hp, get_json(f"/heatmap/match/{mid}/heatmaps?" + urllib.parse.urlencode({"heatmapUrl": heatmap_url}))); heatmaps += 1
                ltc_url = find_first(detail_payload, ("ltcUrl", "ltcURL", "liveTickerUrl", "liveTickerURL")) or f"https://data.fotmob.com/webcl/ltc/gsm/{mid}_en.json.gz"; tp = raw / "liveticker" / (mid + ".json"); teams = [(match.get("home") or {}).get("name"), (match.get("away") or {}).get("name")]
                if not tp.exists() and all(teams):
                    q = urllib.parse.urlencode({"ltcUrl": ltc_url, "teams": json.dumps(teams, separators=(",", ":"))}); save(tp, get_json(f"/ltc?{q}")); tickers += 1
            except Exception as exc: errors.append({"match_id": mid, "error": str(exc)})
        status["records"].update({"match_details": detail, "match_details_skipped_existing": skipped, "heatmaps": heatmaps, "livetickers": tickers, "videos": videos_count, "event_video_refs": event_video_refs_count}); status["layers"].update({"stats": "available" if detail or skipped else "pending", "events": "available" if detail or skipped else "pending", "spatial": "available" if heatmaps else ("available" if detail or skipped else "pending"), "video": "available" if videos_count else "unavailable"}); status["errors"].extend(errors); status["status"] = "success" if not status["errors"] else "partial"
    except Exception as exc: status["status"] = "error"; status["errors"].append({"fatal": str(exc)})
    save(root / "source-status-fotmob.json", status); save(root / "status-fotmob.json", status)

if __name__ == "__main__": main()
