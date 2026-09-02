"""Publish dashboard payload from normalized evidence and deterministic metrics."""
import json
from datetime import datetime, timezone
from pathlib import Path
from intelligence import build_insights

CFG = Path("config/selected-scout.json")
OUT = Path("dashboard/data.json")


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    root = Path("data/scouting") / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    normalized_path = root / "normalized" / "fosi.json"
    metrics_path = root / "normalized" / "metrics.json"
    status_path = root / "master-status.json"
    if not normalized_path.exists(): raise SystemExit("Normalized FOSI data not found")
    normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
    metrics_bundle = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {"metrics": {}}
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    raw_metrics = metrics_bundle.get("metrics", {})
    metrics = {k: v.get("value") if isinstance(v, dict) else v for k, v in raw_metrics.items()}
    xgf, xga = metrics.get("xg"), metrics.get("xga")
    insights = build_insights({"xg_for": xgf, "xg_against": xga})
    data_score = status.get("data_score", 0)
    payload = {
        "schema_version": "1.1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "verified_partial" if data_score > 0 else status.get("status", "awaiting_verified_ingestion"),
        "team": {"id": cfg["team_id"], "name": cfg["team"], "competition": cfg["competition"], "country": cfg["country"]},
        "metrics": metrics, "metric_meta": raw_metrics,
        "matches": (metrics_bundle.get("recent_matches") or normalized.get("matches", []))[:20],
        "players": normalized.get("players", []), "events": normalized.get("events", []),
        "shots": normalized.get("shots", []), "spatial_actions": normalized.get("spatial_actions", []),
        "threat_score": None, "insights": insights,
        "data_quality": {"score": data_score, "layers": status.get("layers", {}), "sources": status.get("sources", []), "sample_matches": metrics.get("matches_sample")},
        "sources": status.get("sources", []),
        "provenance": {"metrics": str(metrics_path).replace("\\", "/"), "normalized": str(normalized_path).replace("\\", "/")}
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Dashboard payload published from normalized FOSI metrics")

if __name__ == "__main__": main()
