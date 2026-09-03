"""Deterministic, evidence-based FOSI intelligence layer."""
from dataclasses import dataclass, asdict

@dataclass
class Insight:
    kind: str
    title: str
    evidence: str
    confidence: int
    status: str = "pattern"
    def to_dict(self): return asdict(self)

def _coverage(meta, key):
    try: return max(0.0, min(1.0, float((meta.get(key) or {}).get("coverage", 0))))
    except (TypeError, ValueError): return 0.0

def _confidence(sample, coverage, base=50):
    try: s=max(0.0,min(1.0,float(sample)/10))
    except (TypeError, ValueError): s=0.0
    return max(35,min(95,round(base+20*s+15*coverage)))

def build_insights(metrics, metric_meta=None, bundle=None):
    meta=metric_meta or {}; sample=metrics.get("matches_sample") or 0; out=[]
    xgf,xga=metrics.get("xg"),metrics.get("xga")
    if isinstance(xgf,(int,float)) and isinstance(xga,(int,float)):
        cov=min(_coverage(meta,"xg"),_coverage(meta,"xga"))
        if xgf>xga: out.append(Insight("strength","Positive chance balance",f"xG {xgf:.2f} > xGA {xga:.2f}; coverage {cov:.0%}",_confidence(sample,cov,55)))
        elif xga>xgf: out.append(Insight("weakness","Negative chance balance",f"xGA {xga:.2f} > xG {xgf:.2f}; coverage {cov:.0%}",_confidence(sample,cov,55)))
    sf,sa=metrics.get("shots_for"),metrics.get("shots_against")
    if isinstance(sf,(int,float)) and isinstance(sa,(int,float)):
        cov=min(_coverage(meta,"shots_for"),_coverage(meta,"shots_against"))
        if sa>sf*1.35: out.append(Insight("weakness","Opponent shot-volume exposure",f"{sa:.0f} shots against vs {sf:.0f} for; coverage {cov:.0%}",_confidence(sample,cov,50)))
        elif sf>sa*1.35: out.append(Insight("strength","Positive shot-volume balance",f"{sf:.0f} shots for vs {sa:.0f} against; coverage {cov:.0%}",_confidence(sample,cov,50)))
    form=metrics.get("form")
    if isinstance(form,str) and len(form)>=5:
        w,l=form[:5].count("W"),form[:5].count("L")
        if w>=3: out.append(Insight("strength","Recent positive results",f"{w} wins in last 5 recorded matches",_confidence(sample,1,50)))
        elif l>=3: out.append(Insight("weakness","Recent negative results",f"{l} losses in last 5 recorded matches",_confidence(sample,1,50)))
    return [x.to_dict() for x in out]
