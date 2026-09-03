"""Publish the complete normalized FOSI evidence model to the dashboard."""
import json
from datetime import datetime, timezone
from pathlib import Path
from intelligence import build_insights

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
        if not isinstance(p, dict):
            continue
        q = dict(p)
        q["name"] = display_name(p.get("name")) or display_name(p.get("player_name")) or "Unnamed player"
        out.append(q)
    return out


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
    insights = build_insights(metrics, raw_metrics, metrics_bundle)
    data_score = status.get("data_score", 0)
    matches = normalized.get("matches", [])
    players = clean_players(normalized.get("players", []))
    events = normalized.get("events", [])
    shots = normalized.get("shots", [])
    spatial_actions = normalized.get("spatial_actions", [])
    payload = {
        "schema_version": "1.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "verified_partial" if data_score > 0 else status.get("status", "awaiting_verified_ingestion"),
        "team": {"id": cfg["team_id"], "name": cfg["team"], "competition": cfg["competition"], "country": cfg["country"]},
        "metrics": metrics,
        "metric_meta": raw_metrics,
        "matches": matches,
        "recent_matches": matches[:20],
        "match_metrics": metrics_bundle.get("match_metrics", []),
        "xg_by_match": metrics_bundle.get("xg_by_match", {}),
        "shot_zones_for": metrics_bundle.get("shot_zones_for", {}),
        "players": players,
        "events": events,
        "shots": shots,
        "spatial_actions": spatial_actions,
        "counts": {"matches": len(matches), "players": len(players), "events": len(events), "shots": len(shots), "spatial_actions": len(spatial_actions)},
        "threat_score": None,
        "insights": insights,
        "data_quality": {"score": data_score, "layers": status.get("layers", {}), "sources": status.get("sources", []), "sample_matches": metrics.get("matches_sample")},
        "sources": status.get("sources", []),
        "provenance": {"metrics": str(metrics_path).replace("\\", "/"), "normalized": str(normalized_path).replace("\\", "/"), "raw_root": str(root / "raw").replace("\\", "/")},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Dashboard payload published: {len(matches)} matches, {len(players)} players, {len(events)} events, {len(shots)} shots, {len(spatial_actions)} spatial actions")


if __name__ == "__main__":
    main()
