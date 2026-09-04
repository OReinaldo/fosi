"""Post-acquisition hardening for FOSI raw evidence.

This layer never replaces RAW. It only retries documented secondary assets,
removes unsupported event->video claims, and records an auditable summary.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path("config/selected-scout.json")
ROOT_BASE = Path("data/scouting")
FOTMOB = "https://www.fotmob.com/api/data"


def get_json(path):
    req = urllib.request.Request(
        FOTMOB + path,
        headers={"User-Agent": "Mozilla/5.0 FOSI/1.2", "Accept": "application/json", "Referer": "https://www.fotmob.com/"},
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def first_value(node, keys):
    wanted = {k.lower() for k in keys}
    for obj in walk(node):
        for k, v in obj.items():
            if k.lower() in wanted and isinstance(v, str) and v.strip():
                return v
    return None


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    root = ROOT_BASE / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    raw = root / "raw" / "fotmob"
    audit = {
        "schema_version": "1.0",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "policy": "retry secondary public assets; preserve RAW; no inferred event-video timestamps",
        "heatmaps": {"attempted": 0, "downloaded": 0, "skipped": 0, "errors": []},
        "livetickers": {"attempted": 0, "downloaded": 0, "skipped": 0, "errors": []},
        "video_event_refs_removed": 0,
    }

    # Existing collector may have produced event-video refs by broad match-level
    # association. Those are not valid event links without provider timestamps/IDs.
    for ref_file in (raw / "videos").glob("*-event-refs.json") if (raw / "videos").exists() else []:
        ref_file.unlink()
        audit["video_event_refs_removed"] += 1

    match_dir = raw / "matches"
    for match_file in sorted(match_dir.glob("*.json")) if match_dir.exists() else []:
        mid = match_file.stem
        try:
            detail = json.loads(match_file.read_text(encoding="utf-8"))
        except Exception as exc:
            audit["heatmaps"]["errors"].append({"match_id": mid, "error": f"invalid match JSON: {exc}"})
            continue

        # Only retry spatial/commentary assets when match detail itself is available.
        heatmap_url = first_value(detail, ("heatmapUrl", "heatmapURL"))
        if heatmap_url:
            audit["heatmaps"]["attempted"] += 1
            hp = raw / "heatmaps" / (mid + ".json")
            if hp.exists():
                audit["heatmaps"]["skipped"] += 1
            else:
                try:
                    query = urllib.parse.urlencode({"heatmapUrl": heatmap_url})
                    save(hp, get_json(f"/heatmap/match/{mid}/heatmaps?{query}"))
                    audit["heatmaps"]["downloaded"] += 1
                except Exception as exc:
                    audit["heatmaps"]["errors"].append({"match_id": mid, "error": str(exc)})

        # FotMob's documented live ticker route can be derived deterministically.
        # Do not mark unavailable matches as failures; preserve the attempt result.
        teams = []
        for obj in walk(detail):
            if "teams" in obj and isinstance(obj["teams"], list):
                vals = [x.get("name") for x in obj["teams"] if isinstance(x, dict) and x.get("name")]
                if len(vals) >= 2:
                    teams = vals[:2]
                    break
        if len(teams) == 2:
            audit["livetickers"]["attempted"] += 1
            tp = raw / "liveticker" / (mid + ".json")
            if tp.exists():
                audit["livetickers"]["skipped"] += 1
            else:
                try:
                    ltc_url = f"https://data.fotmob.com/webcl/ltc/gsm/{mid}_en.json.gz"
                    q = urllib.parse.urlencode({"ltcUrl": ltc_url, "teams": json.dumps(teams, separators=(",", ":"))})
                    save(tp, get_json(f"/ltc?{q}"))
                    audit["livetickers"]["downloaded"] += 1
                except Exception as exc:
                    audit["livetickers"]["errors"].append({"match_id": mid, "error": str(exc)})

    save(root / "acquisition-hardening.json", audit)


if __name__ == "__main__":
    main()
