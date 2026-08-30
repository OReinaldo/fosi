"""Deterministic FOSI intelligence layer based only on verified metrics."""
from dataclasses import dataclass, asdict

@dataclass
class Insight:
    kind: str
    title: str
    evidence: str
    confidence: int

    def to_dict(self):
        return asdict(self)

def build_insights(metrics):
    insights = []
    xgf, xga = metrics.get("xg_for"), metrics.get("xg_against")
    if isinstance(xgf, (int, float)) and isinstance(xga, (int, float)):
        if xgf > xga:
            insights.append(Insight("strength", "Positive chance balance", f"xG {xgf:.2f} > xGA {xga:.2f}", 80))
        else:
            insights.append(Insight("weakness", "Negative chance balance", f"xGA {xga:.2f} > xG {xgf:.2f}", 80))
    return [i.to_dict() for i in insights]
