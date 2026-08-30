"""Publish a conservative, verified-data dashboard payload."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("data/scouting/poland/ekstraklasa/pogon-szczecin")
OUT = Path("dashboard/data.json")
TEAM = "Pogoń Szczecin"

def team_name(x): return (x or {}).get("name") or (x or {}).get("longName") or "—"

def extract_xg(detail):
    stats = detail.get("content", {}).get("stats", {}).get("Periods", {}).get("All", {}).get("stats", [])
    for block in stats if isinstance(stats, list) else []:
        for item in block.get("stats", []) if isinstance(block, dict) else []:
            if item.get("key") == "expected_goals":
                vals = item.get("stats")
                if isinstance(vals, list) and len(vals) >= 2: return vals[0], vals[1]
    return None, None

def extract_match(detail):
    general = detail.get("general", {}) if isinstance(detail, dict) else {}
    home, away = general.get("homeTeam", {}), general.get("awayTeam", {})
    facts = detail.get("content", {}).get("matchFacts", {})
    score = facts.get("score", {}) if isinstance(facts.get("score"), dict) else {}
    hg, ag = score.get("homeScore"), score.get("awayScore")
    if hg is None or ag is None:
        try: hg, ag = [int(x.strip()) for x in score.get("scoreStr", "").split("-")[:2]]
        except Exception: hg = ag = None
    hn, an = team_name(home), team_name(away)
    xgh, xga = extract_xg(detail)
    return {"id":detail.get("id") or facts.get("matchId"),"date":general.get("matchTimeUTC") or general.get("utcTime"),"home":hn,"away":an,"finished":bool(general.get("finished")),"score":f"{hg} - {ag}" if hg is not None and ag is not None else score.get("scoreStr"),"goals_for":hg if hn==TEAM else ag if an==TEAM else None,"goals_against":ag if hn==TEAM else hg if an==TEAM else None,"xg_for":xgh if hn==TEAM else xga if an==TEAM else None,"xg_against":xga if hn==TEAM else xgh if an==TEAM else None}

def main():
    status=json.loads((ROOT/"status.json").read_text()); raw=json.loads((ROOT/"raw_team.json").read_text()); team=raw.get("team",raw) if isinstance(raw,dict) else {}
    matches=[]
    for path in sorted((ROOT/"matches").glob("*.json")):
        try:
            m=extract_match(json.loads(path.read_text()))
            if m["finished"]: matches.append(m)
        except Exception: pass
    matches.sort(key=lambda m:m.get("date") or "",reverse=True); recent=matches[:10]
    gf=sum(m["goals_for"] for m in recent if isinstance(m.get("goals_for"),int)); ga=sum(m["goals_against"] for m in recent if isinstance(m.get("goals_against"),int))
    xgf=[m["xg_for"] for m in recent if isinstance(m.get("xg_for"),(int,float))]; xga=[m["xg_against"] for m in recent if isinstance(m.get("xg_against"),(int,float))]
    form=''.join('W' if m.get("goals_for",-1)>m.get("goals_against",-1) else 'D' if m.get("goals_for")==m.get("goals_against") else 'L' for m in recent[:5]) or None
    payload={"schema_version":"0.4","generated_at":datetime.now(timezone.utc).isoformat(),"status":"verified_partial" if recent else "awaiting_verified_ingestion","team":{"id":"pogon-szczecin","name":team.get("name") or TEAM,"competition":"Ekstraklasa","country":"Poland"},"metrics":{"form":form,"goals_for":gf if recent else None,"goals_against":ga if recent else None,"xg":round(sum(xgf),2) if xgf else None,"xga":round(sum(xga),2) if xga else None},"matches":recent,"players":[],"threat_score":None,"data_quality":{"score":status.get("data_score",0),"layers":status.get("layers",{})},"insights":[],"sources":[{"provider":"FotMob","type":"team + match details"}]}
    OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False))

if __name__ == "__main__": main()
