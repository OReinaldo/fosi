"""Build dashboard payload from the active scouting cache, without fabricating fields."""
import json
from datetime import datetime, timezone
from pathlib import Path
from intelligence import build_insights

CFG=Path("config/selected-scout.json"); OUT=Path("dashboard/data.json")

def num(v):
    try:return float(v)
    except (TypeError,ValueError):return None

def name(x): return (x or {}).get("name") or (x or {}).get("longName") or "—"

def extract_xg(detail):
    stats=detail.get("content",{}).get("stats",{}).get("Periods",{}).get("All",{}).get("stats",[])
    for block in stats if isinstance(stats,list) else []:
        for item in block.get("stats",[]) if isinstance(block,dict) else []:
            if item.get("key") in {"expected_goals","xg"}:
                v=item.get("stats")
                if isinstance(v,list) and len(v)>=2:return num(v[0]),num(v[1])
    return None,None

def extract_match(detail,team):
    g=detail.get("general",{}); h=g.get("homeTeam",{}) or {}; a=g.get("awayTeam",{}) or {}; facts=detail.get("content",{}).get("matchFacts",{}) or {}; s=facts.get("score",{}) or {}
    hg,ag=s.get("homeScore"),s.get("awayScore")
    if hg is None or ag is None:
        try:hg,ag=[int(x.strip()) for x in str(s.get("scoreStr","")).split("-")[:2]]
        except (ValueError,TypeError):hg=ag=None
    hn,an=name(h),name(a); xh,xa=extract_xg(detail)
    return {"id":detail.get("id") or facts.get("matchId"),"date":g.get("matchTimeUTC") or g.get("utcTime"),"home":hn,"away":an,"finished":bool(g.get("finished")),"score":s.get("scoreStr"),"goals_for":hg if hn==team else ag if an==team else None,"goals_against":ag if hn==team else hg if an==team else None,"xg_for":xh if hn==team else xa if an==team else None,"xg_against":xa if hn==team else xh if an==team else None}

def main():
    cfg=json.loads(CFG.read_text(encoding="utf-8")); root=Path("data/scouting")/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"]
    status=json.loads((root/"status.json").read_text(encoding="utf-8")) if (root/"status.json").exists() else {}
    matches=[]
    for p in (root/"matches").glob("*.json"):
        try:
            m=extract_match(json.loads(p.read_text(encoding="utf-8")),cfg["team"])
            if m["finished"] and m["id"] is not None:matches.append(m)
        except Exception:continue
    matches.sort(key=lambda x:x.get("date") or "",reverse=True); recent=matches[:20]; sample=recent[:10]
    gf=sum(x["goals_for"] for x in sample if isinstance(x.get("goals_for"),(int,float))); ga=sum(x["goals_against"] for x in sample if isinstance(x.get("goals_against"),(int,float)))
    xgf=[x["xg_for"] for x in sample if isinstance(x.get("xg_for"),(int,float))]; xga=[x["xg_against"] for x in sample if isinstance(x.get("xg_against"),(int,float))]
    form=''.join('W' if x.get("goals_for")>x.get("goals_against") else 'D' if x.get("goals_for")==x.get("goals_against") else 'L' for x in sample[:5] if x.get("goals_for") is not None and x.get("goals_against") is not None) or None
    metrics={"form":form,"goals_for":gf if sample else None,"goals_against":ga if sample else None,"xg":round(sum(xgf)/len(xgf),2) if xgf else None,"xga":round(sum(xga)/len(xga),2) if xga else None,"matches_sample":len(sample)}
    insights=build_insights({"xg_for":metrics["xg"],"xg_against":metrics["xga"]})
    payload={"schema_version":"0.7","generated_at":datetime.now(timezone.utc).isoformat(),"status":status.get("status","awaiting_verified_ingestion"),"team":{"id":cfg["team_id"],"name":cfg["team"],"competition":cfg["competition"],"country":cfg["country"]},"metrics":metrics,"matches":recent,"players":[],"threat_score":round(max(0,min(100,50+(metrics["xg"]-metrics["xga"])*12))) if xgf and xga else None,"insights":insights,"data_quality":{"score":status.get("data_score",0),"layers":status.get("layers",{}),"sample_matches":len(sample)},"sources":[{"provider":x,"status":"configured"} for x in ["FotMob","FBref","Sofascore","Transfermarkt","Understat","Official club"]]}
    OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
if __name__=="__main__":main()
