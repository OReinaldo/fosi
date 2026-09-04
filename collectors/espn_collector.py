"""FOSI ESPN collector: use the current soccer site/core API routes and preserve raw evidence."""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path("config/selected-scout.json")
ROOT_BASE = Path("data/scouting")
SITE_BASES = [
    "https://site.api.espn.com/apis/site/v2/sports/soccer",
    "https://site.web.api.espn.com/apis/site/v2/sports/soccer",
]
V2_BASES = [
    "https://site.api.espn.com/apis/v2/sports/soccer",
    "https://site.web.api.espn.com/apis/v2/sports/soccer",
]
CORE_BASE = "https://sports.core.api.espn.com/v2/sports/soccer"


def get(path, bases=SITE_BASES):
    last = None
    for base in bases:
        try:
            req = urllib.request.Request(
                base + path,
                headers={
                    "User-Agent": "Mozilla/5.0 FOSI/1.1",
                    "Accept": "application/json,text/plain,*/*",
                    "Referer": "https://www.espn.com/",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response), base
        except Exception as exc:
            last = exc
    raise last


def get_core(path):
    return get(path, [CORE_BASE])


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    root = ROOT_BASE / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    raw = root / "raw" / "espn"
    status = {
        "source": "espn",
        "status": "collecting",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "layers": {},
        "records": {},
        "errors": [],
        "routes_attempted": [],
    }
    league = str((cfg.get("provider_competition_ids") or {}).get("espn") or "pol.1")
    team_id = str((cfg.get("provider_ids") or {}).get("espn") or "")

    # ESPN's team schedule route moved to the all-soccer namespace. Keep both routes
    # as fallbacks because some leagues still expose the league-scoped form.
    schedule = None
    for path, bases in [
        (f"/all/teams/{urllib.parse.quote(team_id)}/schedule?fixture=true", SITE_BASES),
        (f"/{league}/teams/{urllib.parse.quote(team_id)}/schedule?fixture=true", SITE_BASES),
    ]:
        if not team_id:
            break
        try:
            schedule, base = get(path, bases)
            status["routes_attempted"].append({"path": path, "status": "success", "base": base})
            save(raw / "schedule.json", schedule)
            status["layers"]["matches"] = "available"
            status["records"]["schedule_events"] = len(schedule.get("events", []))
            status["base_used"] = base
            break
        except Exception as exc:
            status["routes_attempted"].append({"path": path, "status": "error", "error": str(exc)})

    # Team identity, roster and injuries are useful even when ESPN has no league feed.
    if team_id:
        for name, path in [
            ("team.json", f"/all/teams/{urllib.parse.quote(team_id)}"),
            ("roster.json", f"/all/teams/{urllib.parse.quote(team_id)}/roster"),
            ("injuries.json", f"/all/teams/{urllib.parse.quote(team_id)}/injuries"),
            ("record.json", f"/all/teams/{urllib.parse.quote(team_id)}/record"),
        ]:
            try:
                payload, base = get(path)
                save(raw / name, payload)
                key = name[:-5]
                status["layers"]["team" if key == "team" else key] = "available"
                status["records"][key] = 1
                status["base_used"] = base
            except Exception as exc:
                status["errors"].append({"layer": name[:-5], "error": str(exc)})

    # League discovery and standings. The standings endpoint uses /apis/v2/.
    try:
        teams, base = get(f"/{league}/teams")
        save(raw / "teams.json", teams)
        status["layers"]["competition"] = "available"
        status["records"]["teams"] = len(teams.get("sports", teams.get("teams", []))) if isinstance(teams, dict) else 0
        status["base_used"] = base
    except Exception as exc:
        status["errors"].append({"layer": "competition", "error": str(exc)})

    try:
        standings, base = get(f"/{league}/standings", V2_BASES)
        save(raw / "standings.json", standings)
        status["layers"]["standings"] = "available"
        status["records"]["standings"] = 1
        status["base_used"] = base
    except Exception as exc:
        status["errors"].append({"layer": "standings", "error": str(exc)})

    try:
        news, base = get(f"/{league}/news")
        save(raw / "news.json", news)
        status["layers"]["news"] = "available"
        status["records"]["news_items"] = len(news.get("articles", []))
        status["base_used"] = base
    except Exception as exc:
        status["errors"].append({"layer": "news", "error": str(exc)})

    # Match summaries expose richer boxscore/plays/leaders data than the schedule.
    summary_count = 0
    if schedule:
        events = schedule.get("events", [])
        save(raw / "events.json", {"events": events})
        for event in events:
            event_id = str(event.get("id") or "")
            if not event_id:
                continue
            destination = raw / "matches" / event_id / "summary.json"
            if destination.exists():
                summary_count += 1
                continue
            try:
                summary, base = get(f"/{league}/summary?event={urllib.parse.quote(event_id)}")
                save(destination, summary)
                summary_count += 1
                status["base_used"] = base
            except Exception as exc:
                # Fall back to the all-soccer namespace before giving up.
                try:
                    summary, base = get(f"/all/summary?event={urllib.parse.quote(event_id)}")
                    save(destination, summary)
                    summary_count += 1
                    status["base_used"] = base
                except Exception as fallback_exc:
                    status["errors"].append({"match_id": event_id, "layer": "summary", "error": str(fallback_exc)})
    status["records"]["match_summaries"] = summary_count
    status["layers"]["events"] = "available" if summary_count else status["layers"].get("matches", "pending")
    status["layers"]["stats"] = "available" if summary_count else "pending"
    status["status"] = "success" if not status["errors"] else ("partial" if status["records"] else "error")
    save(root / "source-status-espn.json", status)


if __name__ == "__main__":
    main()
