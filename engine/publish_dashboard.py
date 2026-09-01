"""Build dashboard payload from verified raw acquisition without fabricating fields."""
import json
from datetime import datetime,timezone
from pathlib import Path
from intelligence import build_insights
CFG=Path("config/selected-scout.json");OUT=Path("dashboard/data.json")
def num(v):
    try:return float(v)
    except (TypeError,ValueError):return None
def name(x):return (x or {}).get("name") or (x or {}).get("longName") or "—"
def extract_fotmob_xg(detail):
    stats=detail.get("content",{}).get("stats",{}).get("Periods",{}).get("All",{}).get("stats",[])
    for block in stats if isinstance(stats,list) else []:
        for item in block.get("stats",[]) if isinstance(block,dict) else []:
            if item.get("key") in {"expected_goals","xg"}:
                v=item.get("stats")
                if isinstance(v,list) and len(v)>=2:return num(v[0]),num(v[1])
    return None,None
def extract_fotmob_match(detail,team):
    g=detail.get("general",{}) or {};h=g.get("homeTeam",{}) or {};a=g.get("awayTeam",{}) or {};header=detail.get("header",{}) or {};teams=header.get("teams") or [];s=header.get("status",{}) or {};hn,an=name(h),name(a);hg=ag=None
    if len(teams)>=2: hg=teams[0].get("score");ag=teams[1].get("score")
    if hg is None or ag is None:
        try:hg,ag=[int(x.strip()) for x in str(s.get("scoreStr","")).split("-")[:2]]
        except Exception:hg=ag=None
    xh,xa=extract_fotmob_xg(detail)
    return {"id":g.get("matchId") or detail.get("id"),"date":g.get("matchTimeUTC") or g.get("utcTime"),"home":hn,"away":an,"finished":bool(g.get("finished")),"score":s.get("scoreStr"),"goals_for":hg if hn==team else ag if an==team else None,"goals_against":ag if hn==team else hg if an==team else None,"xg_for":xh if hn==team else xa if an==team else None,"xg_against":xa if hn==team else xh if an==team else None,"source":"FotMob"}
def main():
    cfg=json.loads(CFG.read_text(encoding="utf-8"));root=Path("data/scouting")/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];status=json.loads((root/"master-status.json").read_text(encoding="utf-8")) if (root/"master-status.json").exists() else {}
    matches=[];raw=root/"raw"/"fotmob"/"matches"
    for p in raw.glob("*.json") if raw.exists() else []:
        try:
            m=extract_fotmob_match(json.loads(p.read_text(encoding="utf-8")),cfg["team"])
            if m["finished"] and m["id"] is not None:matches.append(m)
        except Exception:pass
    matches.sort(key=lambda x:x.get("date") or "",reverse=True);recent=matches[:20];sample=[m for m in recent[:10] if m.get("goals_for") is not None and m.get("goals_against") is not None]
    gf=sum(m["goals_for"] for m in sample);ga=sum(m["goals_against"] for m in sample);xgf=[m["xg_for"] for m in recent[:10] if isinstance(m.get("xg_for"),(int,float))];xga=[m["xg_against"] for m in recent[:10] if isinstance(m.get("xg_against"),(int,float))]
    form=''.join('W' if m["goals_for"]>m["goals_against"] else 'D' if m["goals_for"]==m["goals_against"] else 'L' for m in sample[:5]) or None
    metrics={"form":form,"goals_for":gf if sample else None,"goals_against":ga if sample else None,"xg":round(sum(xgf)/len(xgf),2) if xgf else None,"xga":round(sum(xga)/len(xga),2) if xga else None,"matches_sample":len(sample)}
    status_name="verified_partial" if status.get("data_score",0)>0 else status.get("status","awaiting_verified_ingestion")
    payload={"schema_version":"0.9","generated_at":datetime.now(timezone.utc).isoformat(),"status":status_name,"team":{"id":cfg["team_id"],"name":cfg["team"],"competition":cfg["competition"],"country":cfg["country"]},"metrics":metrics,"matches":recent,"players":[],"threat_score":None,"insights":build_insights({"xg_for":metrics["xg"],"xg_against":metrics["xga"]}),"data_quality":{"score":status.get("data_score",0),"layers":status.get("layers",{}),"sources":status.get("sources",[]),"sample_matches":len(sample)},"sources":status.get("sources",[])}
    OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
if __name__=="__main__":main()
