"""Truthful FOSI acquisition-quality scoring.

The old score treated the best state seen for each layer as sufficient, so a
single healthy source could mask a blocked or empty source.  This scorer keeps
layer coverage and source health separate and combines both into a bounded
score.  `not_applicable` is excluded from the denominator; it is not a failure.
"""

LAYER_WEIGHTS = {
    "team": 8,
    "competition": 5,
    "matches": 18,
    "players": 12,
    "stats": 18,
    "events": 12,
    "spatial": 10,
    "lineups": 7,
    "video": 5,
    "injuries": 3,
    "standings": 2,
}

STATE_VALUE = {"available": 1.0, "ready": 1.0, "partial": 0.5,
               "pending": 0.25, "not_available": 0.0, "error": 0.0,
               "unavailable": 0.0}

EXPECTED_SOURCES = {"fotmob", "sofascore", "sofascore-spa", "espn", "official-sites"}


def _layer_score(layers):
    earned = total = 0.0
    for name, weight in LAYER_WEIGHTS.items():
        state = layers.get(name)
        if state == "not_applicable":
            continue
        total += weight
        earned += weight * STATE_VALUE.get(state, 0.0)
    return (earned / total if total else 0.0), earned, total


def _record_count(source):
    records = source.get("records") or {}
    total = 0
    for value in records.values():
        if isinstance(value, (int, float)):
            total += max(0, int(value))
    return total


def _source_health(source):
    status = source.get("status")
    if status == "not_applicable":
        return None
    records = _record_count(source)
    if status in {"error", "failed", "not_available"}:
        return 0.0
    if status == "success":
        # A nominally successful collector with almost no records is not full
        # source coverage. This matters for ESPN in lower-coverage competitions.
        if records == 0:
            return 0.25
        if records < 3:
            return 0.60
        return 1.0
    if status == "partial":
        return 0.20 if records == 0 else (0.55 if records < 3 else 0.75)
    return 0.25 if records else 0.0


def breakdown(layers, sources=None):
    layer_ratio, earned, total = _layer_score(layers or {})
    source_values = []
    seen = set()
    for source in sources or []:
        name = str(source.get("source") or "").strip().lower()
        if name:
            seen.add(name)
        value = _source_health(source)
        if value is not None:
            source_values.append(value)
    # Missing expected sources are explicit acquisition gaps, even when another
    # source supplies the same layer. SofaScore and its SPA fallback are treated
    # as one expected provider family to avoid double-penalising it.
    missing = {s for s in EXPECTED_SOURCES if s not in seen}
    if "sofascore" not in seen and "sofascore-spa" not in seen:
        missing.add("sofascore")
        missing.discard("sofascore-spa")
    expected = len(EXPECTED_SOURCES) - 1  # SofaScore + SPA = one provider family.
    healthy = sum(source_values)
    # One value is reserved for the SofaScore family.
    sofa_values = [_source_health(s) for s in sources or [] if str(s.get("source","")).lower() in {"sofascore","sofascore-spa"}]
    if sofa_values:
        healthy = healthy - sum(v for v in sofa_values if v is not None) + max(sofa_values)
    source_ratio = healthy / expected if expected else 0.0
    source_ratio = max(0.0, min(1.0, source_ratio))
    score = round(100 * (0.70 * layer_ratio + 0.30 * source_ratio))
    return {
        "score": score,
        "layer_coverage": round(layer_ratio, 3),
        "source_health": round(source_ratio, 3),
        "missing_expected_sources": sorted(missing),
        "layer_points": round(earned, 2),
        "layer_points_possible": round(total, 2),
    }


def score(layers, sources=None):
    return breakdown(layers, sources).get("score", 0)
