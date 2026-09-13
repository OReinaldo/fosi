"""Authorized SofaScore fallback through Crawlora's documented public-data API.

This collector is intentionally opt-in: it only runs when CRAWLORA_API_KEY is set.
It writes the same RAW SofaScore shapes used by the native collector, so the rest
of FOSI does not need to know which acquisition transport supplied the data.
"""
import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CONFIG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")
BASE = "https://api.crawlora.net/api/v1"


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def call(endpoint, params):
    key = os.getenv("CRAWLORA_API_KEY", "").strip()
    if not key:
        raise RuntimeError("CRAWLORA_API_KEY is not configured")
    url = f"{BASE}/{endpoint}?{urlencode(params)}"
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "FOSI/1.0", "x-api-key": key})
    with urlopen(req, timeout=60) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Crawlora HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def data_of(payload):
    return payload.get("data", payload) if isinstance(payload, dict) else payload


def main():
    key = os.getenv("CRAWLORA_API_KEY", "").strip()
    if not key:
        print("Crawlora SofaScore fallback: skipped (CRAWLORA_API_KEY not configured)")
        return

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    country = cfg["country"].lower().replace(" ", "-")
    competition = cfg["competition"].lower().replace(" ", "-")
    team_slug = cfg["team_id"]
    team_id = str((cfg.get("provider_ids") or {}).get("sofascore") or "")
    raw = ROOT / country / competition / team_slug / "raw" / "sofascore"
    status = {
        "source": "sofascore-crawlora",
        "transport": "crawlora",
        "status": "collecting",
        "team_id": team_id,
        "records": {},
        "errors": [],
    }
    if not team_id:
        status["status"] = "unavailable"
        status["errors"].append("SofaScore team id not configured")
        save(raw.parent / "source-status-sofascore-crawlora.json", status)
        return

    try:
        team = data_of(call("sofascore/team", {"id": team_id}))
        save(raw / "team.json", {"team": team.get("team", team)})
        status["records"]["team"] = 1
    except Exception as exc:
        status["errors"].append({"layer": "team", "error": str(exc)})

    try:
        players = data_of(call("sofascore/team-players", {"id": team_id}))
        save(raw / "squad.json", {"players": players.get("players", [])})
        status["records"]["players"] = len(players.get("players", []))
    except Exception as exc:
        status["errors"].append({"layer": "players", "error": str(exc)})

    events = {}
    for direction in ("last", "next"):
        for page in range(12):
            try:
                payload = data_of(call("sofascore/team-events", {"id": team_id, "direction": direction, "page": page}))
                batch = payload.get("events", [])
                for event in batch:
                    if event.get("id") is not None:
                        events[str(event["id"])] = event
                if not payload.get("has_next_page") or not batch:
                    break
            except Exception as exc:
                status["errors"].append({"layer": f"team-events-{direction}-{page}", "error": str(exc)})
                break

    event_list = list(events.values())
    save(raw / "events.json", {"events": event_list})
    status["records"]["matches"] = len(event_list)

    counts = {"event": 0, "statistics": 0, "incidents": 0, "lineups": 0}
    endpoints = {
        "event": "sofascore/event",
        "statistics": "sofascore/event-statistics",
        "incidents": "sofascore/event-incidents",
        "lineups": "sofascore/event-lineups",
    }
    # Prefer finished/recent matches for the scouting dataset and keep requests bounded.
    selected = [e for e in event_list if (e.get("status") or {}).get("type") == "finished"][-12:]
    if not selected:
        selected = event_list[-12:]
    for event in selected:
        eid = str(event["id"])
        for kind, endpoint in endpoints.items():
            dest = raw / "matches" / eid / f"{kind}.json"
            try:
                payload = data_of(call(endpoint, {"id": eid}))
                if kind == "event":
                    payload = {"event": payload.get("event", payload)}
                elif kind == "statistics":
                    payload = {"statistics": payload}
                elif kind == "incidents":
                    payload = {"incidents": payload.get("incidents", payload)}
                elif kind == "lineups":
                    payload = {"home": payload.get("home", {}), "away": payload.get("away", {})}
                save(dest, payload)
                counts[kind] += 1
            except Exception as exc:
                status["errors"].append({"layer": kind, "event": eid, "error": str(exc)})
            time.sleep(0.25)

    status["records"].update(counts)
    status["status"] = "available" if counts["event"] or counts["statistics"] or counts["lineups"] else "partial"
    status["events_selected"] = len(selected)
    save(raw.parent / "source-status-sofascore-crawlora.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
