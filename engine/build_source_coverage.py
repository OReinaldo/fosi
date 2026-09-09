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
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def has_files(path, pattern):
    return any(path.glob(pattern))


def main():
    cfg = load(CONFIG)
    root = ROOT / cfg.get("country", "").lower().replace(" ", "-") / cfg.get("competition", "").lower().replace(" ", "-") / cfg.get("team_id", "")
    statuses = {}
    for path in root.glob("source-status-*.json"):
        data = load(path)
        statuses[data.get("source", path.stem.replace("source-status-", ""))] = data

    matrix = {}
    for source, st in sorted(statuses.items()):
        layers = st.get("layers", {})
        rec = st.get("records", {})
        # SofaScore SPA may publish its status under a different source label than
        # its raw directory. Prefer the explicit raw directory when present.
        raw_source = "sofascore" if source.startswith("sofascore") and (root / "raw" / "sofascore").exists() else source
        raw = root / "raw" / raw_source
        available = set()

        if layers.get("team") == "available" or rec.get("team") or (raw / "team.json").exists():
            available.add("team_identity")
        if layers.get("competition") == "available" or rec.get("competition") or (raw / "league.json").exists():
            available.add("competition")
        if layers.get("standings") == "available" or rec.get("standings") or (raw / "standings.json").exists():
            available.add("standings")
        if layers.get("matches") == "available" or rec.get("matches") or rec.get("schedule_events") or has_files(raw, "matches.json") or has_files(raw, "events.json") or has_files(raw, "schedule.json"):
            available.add("fixtures_results")
        if layers.get("players") == "available" or rec.get("players") or rec.get("player_profiles") or (raw / "squad.json").exists():
            available.add("squad")
        if rec.get("player_profiles") or has_files(raw / "players", "*.json"):
            available.add("player_profiles")
        if rec.get("player_matches") or has_files(raw / "player-matches", "*.json"):
            available.add("player_match_history")
        if rec.get("match_summaries") or rec.get("match_details") or rec.get("match_details_skipped_existing") or has_files(raw / "matches", "*/summary.json") or has_files(raw / "matches", "*/event.json"):
            available.add("match_summary")
        if layers.get("events") == "available" or rec.get("plays") or rec.get("incidents") or has_files(raw / "matches", "*/incidents.json") or has_files(raw / "matches", "*/plays.json"):
            available.add("events")
        if layers.get("stats") == "available" or rec.get("statistics") or rec.get("competitor_stats") or has_files(raw / "matches", "*/statistics.json") or has_files(raw / "matches", "*/competitor-stats-*.json"):
            available.update({"shots_xg", "xgot", "passes_possession", "recoveries_losses", "duels_tackles_interceptions", "final_third"})
        if rec.get("shotmap") or has_files(raw / "matches", "*/shotmap.json") or has_files(raw / "matches", "*/shots.json"):
            available.add("shots_xg")
        if layers.get("spatial") == "available" or rec.get("heatmaps") or has_files(raw / "matches", "*/heatmap*.json") or has_files(raw / "matches", "*/graph.json"):
            available.add("spatial_heatmaps")
        if rec.get("transfers") or (raw / "transfers.json").exists() or (raw / "transactions.json").exists():
            available.add("transfers")
        if layers.get("news") == "available" or rec.get("news_items") or (raw / "news.json").exists() or has_files(root / "raw" / "sites", "site-*.html"):
            # Official club/competition news is valid context even when the collector
            # exposes it as a page layer rather than a normalized news_items counter.
            available.add("news_context")
        if layers.get("injuries") == "available" or rec.get("injuries") or (raw / "injuries.json").exists():
            available.add("injuries")
        if rec.get("lineups") or has_files(raw / "matches", "*/lineups.json"):
            available.add("lineups")
        if rec.get("cards") or rec.get("incidents") or rec.get("plays") or has_files(raw / "matches", "*/incidents.json") or has_files(raw / "matches", "*/plays.json"):
            available.add("cards_suspensions")
        if layers.get("video") == "available" or rec.get("videos") or has_files(raw / "videos", "*.json") or has_files(raw / "matches", "*/media.json"):
            available.add("video_evidence")

        matrix[source] = {field: ("available" if field in available else "missing") for field in FIELDS}

    payload = {
        "schema": "1.1",
        "generated_from": "source-status + RAW inventory",
        "target": {"country": cfg.get("country"), "competition": cfg.get("competition"), "team": cfg.get("team"), "season": cfg.get("season")},
        "fields": FIELDS,
        "sources": matrix,
        "notes": {
            "available": "Available means verified acquisition evidence exists in status or preserved RAW. It does not claim that every provider exposes every subfield for every match.",
            "missing": "No usable evidence was observed for this field from that source.",
            "source_aliases": "SofaScore browser/SPA status is mapped to its preserved SofaScore RAW directory when present.",
            "compliance_gated": "Sources such as FBref/Transfermarkt remain excluded from automated acquisition unless an explicit compliant access path is established."
        }
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Source coverage: {len(matrix)} sources x {len(FIELDS)} fields -> {OUT}")


if __name__ == "__main__":
    main()
