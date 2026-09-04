"""Publish the complete normalized FOSI evidence model to the dashboard."""
import json
from datetime import datetime, timezone
from pathlib import Path
from intelligence import build_insights
from scouting_intelligence import build_player_intelligence, build_match_intelligence, build_threat_weakness_center

CFG = Path("config/selected-scout.json")
OUT = Path("dashboard/data.json")


def display_name(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return value.get("fullName") or " ".join(str(value.get(k, "")).strip() for k in ("firstName", "lastName") if value.get(k)).strip() or None
    return None


def clean_players(rows):
    out = []
    for p in rows or []:
        if isinstance(p, dict):
            q = dict(p)
            q["name"] = display_name(p.get("name")) or display_name(p.get("player_name")) or "Unnamed player"
            out.append(q)
    return out


def match_status(match, now):
    status = str(match.get("status", "")).lower()
    if status in {"finished", "completed", "played"} or match.get("played") is True:
        return "finished"
    if status in {"scheduled", "upcoming", "future"} or match.get("played") is False:
        return "scheduled"
    score = match.get("score")
    try:
        dt = datetime.fromisoformat(str(match.get("date", "")).replace("Z", "+00:00"))
        if dt <= now and isinstance(score, dict) and score.get("home") is not None and score.get("away") is not None:
            return "finished"
    except Exception:
        pass
    return "unresolved"


def load_video_evidence(root):
    """Load source-preserved match video links only; event links require explicit provider evidence."""
    videos = []
    raw = root / "raw"
    for path in sorted(raw.glob("**/fotmob/videos/*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for item in payload.get("videos", []):
                if isinstance(item, dict) and item.get("url"):
                    row = dict(item)
                    row["raw_path"] = str(path).replace("\\", "/")
                    videos.append(row)
        except Exception:
            pass
    return videos, []


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    root = Path("data/scouting") / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    normalized_path = root / "normalized" / "fosi.json"
    metrics_path = root / "normalized" / "metrics.json"
    status_path = root / "master-status.json"
    if not normalized_path.exists():
        raise SystemExit("Normalized FOSI data not found")
    normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
    metrics_bundle = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {"metrics": {}}
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    raw_metrics = metrics_bundle.get("metrics", {})
    metrics = {k: v.get("value") if isinstance(v, dict) else v for k, v in raw_metrics.items()}
    now = datetime.now(timezone.utc)
    matches = normalized.get("matches", [])
    for match in matches:
        if isinstance(match, dict):
            s = match_status(match, now)
            match["status"] = s
            match["played"] = s == "finished"
            if s != "finished":
                match["score"] = None
                match["result_for_home"] = None
    played_matches = [m for m in matches if isinstance(m, dict) and m.get("status") == "finished"]
    scheduled_matches = [m for m in matches if isinstance(m, dict) and m.get("status") == "scheduled"]
    unresolved_matches = [m for m in matches if isinstance(m, dict) and m.get("status") == "unresolved"]
    played_matches.sort(key=lambda m: str(m.get("date", "")), reverse=True)
    scheduled_matches.sort(key=lambda m: str(m.get("date", "")))
    players = clean_players(normalized.get("players", []))
    events = normalized.get("events", [])
    shots = normalized.get("shots", [])
    spatial = normalized.get("spatial_actions", [])
    player_metrics = metrics_bundle.get("player_metrics", [])
    player_intelligence = build_player_intelligence(player_metrics)
    match_metrics = metrics_bundle.get("match_metrics", [])
    played_ids = {str(m.get("provider_id")) for m in played_matches}
    played_match_metrics = [m for m in match_metrics if str(m.get("match_id", m.get("provider_id", ""))) in played_ids] if played_ids else match_metrics
    match_intelligence = build_match_intelligence(played_matches, played_match_metrics)
    threat_center = build_threat_weakness_center(metrics, player_intelligence, match_intelligence)
    videos, video_event_refs = load_video_evidence(root)
    payload = {
        "schema_version": "1.7",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "verified_partial" if status.get("data_score", 0) > 0 else status.get("status", "awaiting_verified_ingestion"),
        "team": {"id": cfg["team_id"], "name": cfg["team"], "competition": cfg["competition"], "country": cfg["country"]},
        "metrics": metrics,
        "metric_meta": raw_metrics,
        "matches": matches,
        "recent_matches": played_matches[:20],
        "played_matches": played_matches,
        "scheduled_matches": scheduled_matches,
        "unresolved_matches": unresolved_matches,
        "match_metrics": match_metrics,
        "match_intelligence": match_intelligence,
        "xg_by_match": metrics_bundle.get("xg_by_match", {}),
        "shot_zones_for": metrics_bundle.get("shot_zones_for", {}),
        "players": players,
        "player_metrics": player_metrics,
        "player_intelligence": player_intelligence,
        "events": events,
        "shots": shots,
        "spatial_actions": spatial,
        "videos": videos,
        "video_event_refs": video_event_refs,
        "counts": {
            "matches": len(matches),
            "played_matches": len(played_matches),
            "scheduled_matches": len(scheduled_matches),
            "unresolved_matches": len(unresolved_matches),
            "players": len(players),
            "events": len(events),
            "shots": len(shots),
            "spatial_actions": len(spatial),
            "lineups": len(normalized.get("lineups", [])),
            "player_matches": len(normalized.get("player_matches", [])),
            "videos": len(videos),
            "video_event_refs": len(video_event_refs),
        },
        "threat_score": None,
        "insights": build_insights(metrics, metric_meta=raw_metrics, bundle=metrics_bundle),
        "threat_center": threat_center.get("threats", []),
        "weakness_center": threat_center.get("weaknesses", []),
        "data_quality": {
            "score": status.get("data_score", 0),
            "layers": status.get("layers", {}),
            "sources": status.get("sources", []),
            "sample_matches": metrics.get("matches_sample"),
        },
        "sources": status.get("sources", []),
        "provenance": {
            "metrics": str(metrics_path).replace("\\", "/"),
            "normalized": str(normalized_path).replace("\\", "/"),
            "raw_root": str(root / "raw").replace("\\", "/"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Dashboard payload published: {len(played_matches)} played, {len(scheduled_matches)} scheduled, {len(unresolved_matches)} unresolved, {len(players)} players, {len(events)} events, {len(shots)} shots, {len(spatial)} spatial actions, {len(videos)} videos")


if __name__ == "__main__":
    main()
