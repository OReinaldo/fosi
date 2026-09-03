"""Evidence-first player and match intelligence for FOSI.

Outputs measurable rankings/patterns only. No tactical role is inferred from
statistics alone, and every item keeps its evidence basis and confidence.
"""
from collections import defaultdict


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(',', '.').replace('%', '').strip())
    except (TypeError, ValueError):
        return None


def _score_confidence(sample, coverage=1.0):
    s = max(0.0, min(1.0, float(sample or 0) / 10.0))
    c = max(0.0, min(1.0, float(coverage or 0)))
    return max(35, min(95, round(40 + 20 * s + 25 * c)))


def _value(stats, key):
    return _num((stats or {}).get(key))


def build_player_intelligence(player_metrics, min_minutes=180):
    """Rank players by measurable contribution families, not inferred roles."""
    rows = []
    for p in player_metrics or []:
        stats = p.get('stats') or {}
        mins = _value(stats, 'minutes')
        if mins is None or mins < min_minutes:
            continue
        per90 = p.get('per90') or {}
        families = {
            'production': sum(max(0, _value(stats, k) or 0) * w for k, w in [('goals', 4), ('assists', 3), ('xg', 1)]),
            'creation': sum(max(0, _value(per90, k) or 0) * w for k, w in [('key_passes', 2), ('assists', 2), ('final_third_entries', 0.5)]),
            'defensive': sum(max(0, _value(per90, k) or 0) * w for k, w in [('tackles', 1), ('interceptions', 1), ('recoveries', 0.5), ('duels', 0.25)]),
            'involvement': sum(max(0, _value(per90, k) or 0) * w for k, w in [('passes', 0.25), ('touches', 0.1), ('touches_opp_box', 0.75)]),
        }
        top_family = max(families, key=families.get)
        evidence = {}
        for key in ('minutes', 'goals', 'assists', 'xg', 'xgot', 'shots', 'shots_on_target', 'key_passes', 'passes', 'accurate_passes', 'tackles', 'interceptions', 'duels', 'recoveries', 'turnovers', 'touches_opp_box', 'final_third_entries'):
            value = _value(stats, key)
            if value is not None:
                evidence[key] = value
        rows.append({
            'player_id': p.get('player_id') or p.get('fosi_id'),
            'name': p.get('name') or 'Jugador sin nombre',
            'position': p.get('position'),
            'minutes': mins,
            'per90': per90,
            'family_scores': {k: round(v, 2) for k, v in families.items()},
            'leading_statistical_family': top_family,
            'evidence': evidence,
            'confidence': _score_confidence(mins / 90),
            'status': 'observed+derived',
        })
    rows.sort(key=lambda x: (x['family_scores'].get('production', 0), x['family_scores'].get('creation', 0)), reverse=True)
    for i, row in enumerate(rows, 1):
        row['rank'] = i
    return rows


def build_match_intelligence(matches, match_metrics):
    """Create match-level evidence records and conservative patterns."""
    by_id = {str(x.get('match_id')): x for x in (match_metrics or [])}
    out = []
    for m in matches or []:
        mid = str(m.get('provider_id') or m.get('fosi_id'))
        mm = by_id.get(mid, {})
        gf, ga = _num(mm.get('goals_for')), _num(mm.get('goals_against'))
        xgf, xga = _num(mm.get('xg')), _num(mm.get('xga'))
        sf, sa = _num(mm.get('shots_for')), _num(mm.get('shots_against'))
        patterns = []
        if xgf is not None and xga is not None:
            patterns.append('balance_xg_positive' if xgf > xga else 'balance_xg_negative' if xga > xgf else 'balance_xg_even')
        if sf is not None and sa is not None:
            patterns.append('shot_volume_positive' if sf > sa else 'shot_volume_negative' if sa > sf else 'shot_volume_even')
        if gf is not None and ga is not None and xgf is not None and xga is not None:
            goal_balance = gf - ga
            xg_balance = xgf - xga
            if goal_balance * xg_balance < 0:
                patterns.append('result_xg_divergence')
        evidence = {k: v for k, v in {'goals_for': gf, 'goals_against': ga, 'xg': xgf, 'xga': xga, 'shots_for': sf, 'shots_against': sa}.items() if v is not None}
        out.append({
            'match_id': mid,
            'date': m.get('date'),
            'home_team': m.get('home_team'),
            'away_team': m.get('away_team'),
            'score': m.get('score'),
            'result': mm.get('result'),
            'patterns': patterns,
            'evidence': evidence,
            'confidence': _score_confidence(1, 1 if evidence else 0),
            'status': 'pattern',
        })
    return out


def build_threat_weakness_center(metrics, player_intelligence, match_intelligence):
    """Build evidence-backed threat/weakness candidates.

    'Threat' and 'weakness' mean statistical scouting signals. They are not
    tactical instructions and are never emitted without measurable evidence.
    """
    threats, weaknesses = [], []
    def add(target, kind, title, evidence, confidence=60):
        target.append({'kind': kind, 'title': title, 'evidence': evidence, 'confidence': max(35, min(95, int(confidence))), 'status': 'pattern'})

    xg, xga = _num(metrics.get('xg')), _num(metrics.get('xga'))
    shots_for, shots_against = _num(metrics.get('shots_for')), _num(metrics.get('shots_against'))
    if xg is not None and xga is not None:
        if xg > xga:
            add(threats, 'team', 'Producción de ocasiones superior a la recibida', f'xG {xg:.2f} frente a xGA {xga:.2f}.', 68)
        elif xga > xg:
            add(weaknesses, 'team', 'Balance de ocasiones desfavorable', f'xGA {xga:.2f} frente a xG {xg:.2f}.', 68)
    if shots_for is not None and shots_against is not None:
        if shots_for > shots_against * 1.25:
            add(threats, 'team', 'Volumen de tiro superior', f'{shots_for:.0f} tiros propios frente a {shots_against:.0f} recibidos.', 62)
        elif shots_against > shots_for * 1.25:
            add(weaknesses, 'team', 'Volumen de tiro rival superior', f'{shots_against:.0f} tiros recibidos frente a {shots_for:.0f} propios.', 62)

    for p in player_intelligence[:5]:
        scores = p.get('family_scores') or {}
        if scores.get('production', 0) > 0 or scores.get('creation', 0) > 0:
            add(threats, 'player', f"Contribución estadística destacada: {p['name']}",
                f"Familia dominante: {p['leading_statistical_family']}; minutos {p['minutes']:.0f}.", p.get('confidence', 50))
    return {'threats': threats, 'weaknesses': weaknesses, 'match_signals': match_intelligence}
