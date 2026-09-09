"""Promote verified FotMob team-season deep stats into dashboard metrics.

The main metrics engine is intentionally conservative and derives match-level
values from normalized events. FotMob's league-season tables are an independent
verified aggregate source, so this step fills aggregate team metrics that are
present in RAW but cannot be reconstructed reliably from event records.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

CFG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ".").replace("%", "").strip())
        except ValueError:
            return None
    return None


def metric(value, unit, source):
    return {
        "value": round(value, 3) if isinstance(value, float) else value,
        "observed": 1,
        "total": 1,
        "coverage": 1.0,
        "unit": unit,
        "status": "observed",
        "source": source,
    }


def main():
    cfg = load(CFG)
    root = ROOT / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    normalized = root / "normalized" / "fosi.json"
    metrics_path = root / "normalized" / "metrics.json"
    if not normalized.exists() or not metrics_path.exists():
        print(json.dumps({"status": "skipped", "reason": "normalized files missing"}))
        return

    data = load(normalized)
    metrics = load(metrics_path)
    team = data.get("team_season_stats") or {}
    sources = data.get("team_season_stats_source") or {}
    out = metrics.setdefault("metrics", {})

    # FotMob table names are stable enough to use as canonical source fields.
    aliases = {
        "passes": ("passes", "passes"),
        "recoveries": ("recoveries", "recoveries"),
        "losses": ("possession_lost", "losses"),
        "tackles": ("tackles", "tackles"),
        "interceptions": ("interceptions", "interceptions"),
        "duels": ("duels", "duels"),
        "final_third_entries": ("final_third_entries", "entries"),
        "possession": ("possession", "%"),
        "corners": ("corners", "corners"),
        "free_kicks": ("free_kicks", "free kicks"),
    }
    filled = []
    for metric_name, (stat_name, unit) in aliases.items():
        value = num(team.get(stat_name))
        if value is None:
            continue
        source = sources.get(stat_name) or {"source": "fotmob", "raw_path": "raw/fotmob/deepstats"}
        if out.get(metric_name, {}).get("value") is None:
            out[metric_name] = metric(value, unit, source)
            filled.append(metric_name)

    accurate = num(team.get("accurate_passes"))
    passes = num(team.get("passes"))
    if accurate is not None and passes and passes > 0:
        if out.get("pass_accuracy", {}).get("value") is None:
            out["pass_accuracy"] = metric(round(accurate / passes * 100, 2), "%", {
                "source": "fotmob",
                "raw_paths": [sources.get("passes", {}).get("raw_path"), sources.get("accurate_passes", {}).get("raw_path")],
                "method": "accurate_passes / passes * 100",
            })
            filled.append("pass_accuracy")

    metrics["team_season_stats_evidence"] = {
        "source": "fotmob",
        "season": cfg.get("season"),
        "internal_season_id": cfg.get("fotmob_internal_season_id", "37304"),
        "fields_available": sorted(team),
        "fields_promoted": filled,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "success", "fields_promoted": filled, "team_fields": len(team)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
