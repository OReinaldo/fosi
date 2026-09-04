"""Generate a transparent source x data-layer coverage matrix from acquisition status and RAW files."""
import json
from pathlib import Path

CONFIG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")
OUT = Path("data/source-coverage.json")
FIELDS = [
    "team_identity", "competition", "standings", "fixtures_results", "squad", "player_profiles",
    "player_match_history", "match_summary", "lineups", "events", "shots_xg", "xgot", "passes_possession",
    "recoveries_losses", "duels_tackles_interceptions", "final_third", "spatial_heatmaps", "set_pieces",
    "cards_suspensions", "injuries", "transfers", "news_context", "video_evidence"
]


def load(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}


def main():
    cfg = load(CONFIG)
    root = ROOT / cfg.get("country", "").lower().replace(" ", "-") / cfg.get("competition", "").lower().replace(" ", "-") / cfg.get("team_id", "")
    statuses = {}
    for path in root.glob("source-status-*.json"):
        data = load(path); statuses[data.get("source", path.stem.replace("source-status-", ""))] = data
    matrix = {}
    for source, st in sorted(statuses.items()):
        layers = st.get("layers", {})
        rec = st.get("records", {})
        raw = root / "raw" / source
        available = set()
        if layers.get("team") == "available": available.add("team_identity")
        if layers.get("competition") == "available": available.add("competition")
        if layers.get("standings") == "available": available.add("standings")
        if layers.get("matches") == "available" or rec.get("matches") or rec.get("schedule_events"): available.add("fixtures_results")
        if layers.get("players") == "available" or rec.get("players") or rec.get("player_profiles"): available.add("squad")
        if rec.get("player_profiles"): available.add("player_profiles")
        if rec.get("player_matches") or list((raw / "player-matches").glob("*.json")): available.add("player_match_history")
        if rec.get("match_summaries") or rec.get("match_details") or rec.get("match_details_skipped_existing"): available.add("match_summary")
        if layers.get("events") == "available": available.add("events")
        if layers.get("stats") == "available": available.update({"shots_xg", "xgot", "passes_possession", "recoveries_losses", "duels_tackles_interceptions", "final_third"})
        if rec.get("shotmap") or list((raw / "matches").glob("*/shotmap.json")): available.add("shots_xg")
        if layers.get("spatial") == "available": available.add("spatial_heatmaps")
        if rec.get("heatmaps"): available.add("spatial_heatmaps")
        if rec.get("transfers"): available.add("transfers")
        if rec.get("news_items"): available.add("news_context")
        if rec.get("injuries"): available.add("injuries")
        if rec.get("lineups") or list((raw / "matches").glob("*/lineups.json")): available.add("lineups")
        if rec.get("standings"): available.add("standings")
        matrix[source] = {field: ("available" if field in available else "missing") for field in FIELDS}
    payload = {
        "schema": "1.0",
        "generated_from": "source-status + RAW inventory",
        "target": {"country": cfg.get("country"), "competition": cfg.get("competition"), "team": cfg.get("team"), "season": cfg.get("season")},
        "fields": FIELDS,
        "sources": matrix,
        "notes": {
            "available": "The collector reports the layer or RAW evidence as present; it does not guarantee semantic completeness.",
            "missing": "No usable evidence was observed for this field from that source.",
            "compliance_gated": "Sources such as FBref/Transfermarkt remain excluded from automated acquisition unless an explicit compliant access path is established."
        }
    }
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Source coverage: {len(matrix)} sources x {len(FIELDS)} fields -> {OUT}")

if __name__ == "__main__": main()
