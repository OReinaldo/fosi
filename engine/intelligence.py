"""Deterministic, evidence-based FOSI intelligence layer.

This module deliberately produces patterns, not tactical facts. Every pattern is
based on observed/derived metrics and its confidence is bounded by sample size
and data coverage.
"""
from dataclasses import dataclass, asdict


@dataclass
class Insight:
    kind: str
    title: str
    evidence: str
    confidence: int
    status: str = "pattern"

    def to_dict(self):
        return asdict(self)


def _coverage(meta, key):
    try:
        return max(0.0, min(1.0, float((meta.get(key) or {}).get("coverage", 0))))
    except (TypeError, ValueError):
        return 0.0


def _confidence(sample, coverage, base=50):
    try:
        s = max(0.0, min(1.0, float(sample) / 10))
    except (TypeError, ValueError):
        s = 0.0
    return max(35, min(95, round(base + 20 * s + 15 * coverage)))


def _add(out, kind, title, evidence, sample, coverage, base=50):
    out.append(Insight(kind, title, evidence, _confidence(sample, coverage, base)))


def build_insights(metrics, metric_meta=None, bundle=None):
    """Build conservative scouting patterns from verified FOSI metrics."""
    meta = metric_meta or {}
    bundle = bundle or {}
    sample = metrics.get("matches_sample") or 0
    out = []

    # Chance balance.
    xgf, xga = metrics.get("xg"), metrics.get("xga")
    if isinstance(xgf, (int, float)) and isinstance(xga, (int, float)):
        cov = min(_coverage(meta, "xg"), _coverage(meta, "xga"))
        if xgf > xga:
            _add(out, "strength", "Balance positivo de ocasiones",
                 f"xG {xgf:.2f} > xGA {xga:.2f}; cobertura {cov:.0%}", sample, cov, 55)
        elif xga > xgf:
            _add(out, "weakness", "Balance negativo de ocasiones",
                 f"xGA {xga:.2f} > xG {xgf:.2f}; cobertura {cov:.0%}", sample, cov, 55)

    # Shot volume.
    sf, sa = metrics.get("shots_for"), metrics.get("shots_against")
    if isinstance(sf, (int, float)) and isinstance(sa, (int, float)) and sf >= 0 and sa >= 0:
        cov = min(_coverage(meta, "shots_for"), _coverage(meta, "shots_against"))
        if sf and sa > sf * 1.35:
            _add(out, "weakness", "Exposición a volumen de tiros rival",
                 f"{sa:.0f} tiros recibidos frente a {sf:.0f} realizados; cobertura {cov:.0%}", sample, cov, 50)
        elif sa and sf > sa * 1.35:
            _add(out, "strength", "Balance positivo de volumen de tiros",
                 f"{sf:.0f} tiros realizados frente a {sa:.0f} recibidos; cobertura {cov:.0%}", sample, cov, 50)

    # Chance quality / finishing gap. This is a statistical pattern, not a
    # judgement about finishing quality.
    xg_per_match = metrics.get("xg_per_match")
    shots_for = metrics.get("shots_for")
    goals_for = metrics.get("goals_for")
    if isinstance(xg_per_match, (int, float)) and isinstance(shots_for, (int, float)) and shots_for > 0 and sample:
        avg_shots = shots_for / sample
        avg_xg = xg_per_match
        xg_per_shot = avg_xg / avg_shots if avg_shots else None
        if isinstance(xg_per_shot, (int, float)):
            cov = min(_coverage(meta, "xg"), _coverage(meta, "shots_for"))
            if xg_per_shot >= 0.12:
                _add(out, "strength", "Perfil de ocasiones de alta calidad",
                     f"xG/tiro {xg_per_shot:.3f} con {avg_shots:.1f} tiros por partido", sample, cov, 48)
            elif xg_per_shot <= 0.06:
                _add(out, "weakness", "Perfil de ocasiones de baja calidad",
                     f"xG/tiro {xg_per_shot:.3f} con {avg_shots:.1f} tiros por partido", sample, cov, 48)

    # Goals versus expected goals.
    if isinstance(goals_for, (int, float)) and isinstance(xgf, (int, float)):
        cov = min(_coverage(meta, "goals_for"), _coverage(meta, "xg"))
        gap = goals_for - xgf
        if gap >= 1.5:
            _add(out, "pattern", "Producción de gol por encima del xG",
                 f"{goals_for:.0f} goles frente a {xgf:.2f} xG; diferencia {gap:+.2f}", sample, cov, 45)
        elif gap <= -1.5:
            _add(out, "pattern", "Producción de gol por debajo del xG",
                 f"{goals_for:.0f} goles frente a {xgf:.2f} xG; diferencia {gap:+.2f}", sample, cov, 45)

    # Game-state / result pattern.
    form = metrics.get("form")
    if isinstance(form, str) and len(form) >= 5:
        recent = form[:5]
        w, d, l = recent.count("W"), recent.count("D"), recent.count("L")
        if w >= 3:
            _add(out, "strength", "Resultados recientes positivos",
                 f"{w} victorias en los últimos 5 partidos registrados", min(sample, 5), 1.0, 50)
        elif l >= 3:
            _add(out, "weakness", "Resultados recientes negativos",
                 f"{l} derrotas en los últimos 5 partidos registrados", min(sample, 5), 1.0, 50)
        elif d >= 3:
            _add(out, "pattern", "Alta frecuencia de empates recientes",
                 f"{d} empates en los últimos 5 partidos registrados", min(sample, 5), 1.0, 45)

    # Player evidence: surface only measurable contributors, never infer a
    # tactical role from a player's statistics alone.
    player_rows = bundle.get("player_metrics") or []
    candidates = []
    for p in player_rows:
        stats = p.get("stats") or {}
        mins = stats.get("minutes")
        if isinstance(mins, (int, float)) and mins >= 180:
            score = 0.0
            for key, weight in (("goals", 4), ("assists", 3), ("xg", 1), ("key_passes", 0.5)):
                value = stats.get(key)
                if isinstance(value, (int, float)):
                    score += value * weight
            candidates.append((score, p))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        top = candidates[0][1]
        top_name = top.get("name") or "Jugador"
        top_stats = top.get("stats") or {}
        contributions = []
        for key, label in (("goals", "goles"), ("assists", "asistencias"), ("xg", "xG"), ("key_passes", "pases clave")):
            value = top_stats.get(key)
            if isinstance(value, (int, float)) and value:
                contributions.append(f"{label} {value:g}")
        if contributions:
            _add(out, "player", "Mayor contribución estadística registrada",
                 f"{top_name}: " + ", ".join(contributions), sample, 1.0, 40)

    return [x.to_dict() for x in out]
