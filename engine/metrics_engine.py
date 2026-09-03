"""Build deterministic FOSI metrics from normalized evidence."""
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CFG=Path("config/selected-scout.json"); ROOT=Path("data/scouting")
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def num(v):
    if isinstance(v,bool): return None
    if isinstance(v,(int,float)): return float(v)
    if isinstance(v,str):
        try: return float(v.replace(",",".").replace("%","").strip())
        except ValueError: return None
    return None
def metric(value,observed,total,unit=None,status=None,source=None):
    return {"value":value,"observed":observed,"total":total,"coverage":round(observed/total,3) if total else 0,"unit":unit,"status":status or ("observed" if observed else "unavailable"),"source":source}
def walk(node):
    if isinstance(node,dict):
        yield node
        for v in node.values(): yield from walk(v)
    elif isinstance(node,list):
        for v in node: yield from walk(v)
def deep_value(item,keys):
    wanted={k.lower() for k in keys}
    for obj in walk(item):
        for k,v in obj.items():
            if k.lower() in wanted and v is not None: return v
    return None
def deep_values(item,keys):
    wanted={k.lower() for k in keys}; out=[]
    for obj in walk(item):
        for k,v in obj.items():
            if k.lower() in wanted and v is not None:
                n=num(v)
                if n is not None: out.append(n)
    return out
def team_ids(cfg):
    ids={str(cfg.get("team_id")),str((cfg.get("provider_ids") or {}).get("fotmob")),str((cfg.get("provider_ids") or {}).get("sofascore"))}
    return {x for x in ids if x and x!="None"}
def belongs_to_team(item,cfg):
    ids=team_ids(cfg); name=str(cfg["team"]).strip().lower()
    for obj in walk(item):
        for k,v in obj.items():
            if k.lower() in {"teamname","team_name","team"}:
                if isinstance(v,dict):
                    if str(v.get("name","")).strip().lower()==name or str(v.get("id")) in ids: return True
                elif str(v).strip().lower()==name or str(v) in ids: return True
            elif k.lower() in {"teamid","team_id"} and str(v) in ids: return True
    return False
def has_other_team(item,cfg):
    ids=team_ids(cfg); name=str(cfg["team"]).strip().lower(); found=False
    for obj in walk(item):
        for k,v in obj.items():
            if k.lower() not in {"teamname","team_name","team","teamid","team_id"}: continue
            if isinstance(v,dict): n=str(v.get("name","")).strip().lower(); i=str(v.get("id"))
            else: n=str(v).strip().lower(); i=str(v)
            if n or i!="None":
                found=True
                if n==name or i in ids: return False
    return found
def match_id(item):
    v=deep_value(item,("matchId","match_id","eventId","event_id","gameId")); return str(v) if v is not None else None
def xg(item): return num(deep_value(item,("xg","expectedGoals","expected_goals","expectedGoal")))
def xgot(item): return num(deep_value(item,("xgot","expectedGoalsOnTarget","expected_goals_on_target","expectedGoalOnTarget")))
def stat_value(item,keys): return num(deep_value(item,keys))
def classify_shot(item):
    x=stat_value(item,("x","xcoord","xCoordinate","shotX")); y=stat_value(item,("y","ycoord","yCoordinate","shotY"))
    if x is None or y is None or not(0<=x<=100 and 0<=y<=100): return None
    central=40<=y<=60
    if x>=83:return "box-central" if central else "box-wide"
    if x>=67:return "final-third-central" if central else "final-third-wide"
    return "middle-third" if central else "wide"
def team_score(m,cfg):
    h,a,s=m.get("home_team") or {},m.get("away_team") or {},m.get("score") or {}; ids=team_ids(cfg); name=str(cfg["team"]).strip().lower()
    def ours(t): return str(t.get("id")) in ids or str(t.get("name","")).strip().lower()==name
    if ours(h): return num(s.get("home")),num(s.get("away"))
    if ours(a): return num(s.get("away")),num(s.get("home"))
    return None,None
def result_for(m,cfg):
    f,a=team_score(m,cfg); return None if f is None or a is None else ("W" if f>a else "D" if f==a else "L")

def main():
    cfg=load(CFG); root=ROOT/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"]; src=root/"normalized"/"fosi.json"
    if not src.exists(): raise SystemExit("Normalized FOSI data not found")
    data=load(src); matches=[m for m in data.get("matches",[]) if isinstance(m.get("score"),dict)]; matches.sort(key=lambda m:m.get("date") or "",reverse=True)
    gf=[];ga=[];form=[];match_metrics={}
    for m in matches:
        mid=str(m.get("provider_id") or m.get("fosi_id")); f,a=team_score(m,cfg); r=result_for(m,cfg)
        if f is not None and a is not None: gf.append(f);ga.append(a);form.append(r)
        match_metrics[mid]={"match_id":mid,"date":m.get("date"),"competition":m.get("competition"),"home_team":m.get("home_team"),"away_team":m.get("away_team"),"score":m.get("score"),"result":r,"goals_for":f,"goals_against":a}
    shots=data.get("shots",[]); xgf=[];xga=[];xgotf=[];xgota=[];zones=defaultdict(int); shot_counts=defaultdict(lambda:{"for":0,"against":0}); xb=defaultdict(lambda:{"for":0.0,"against":0.0,"for_shots":0,"against_shots":0,"for_xgot":0.0,"against_xgot":0.0}); attributed=0
    for shot in shots:
        ours=belongs_to_team(shot,cfg); other=has_other_team(shot,cfg)
        if not ours and not other: continue
        attributed+=1; mid=match_id(shot); b=xb[mid or "unknown"]; side="for" if ours else "against"; shot_counts[mid or "unknown"][side]+=1
        xv=xg(shot)
        if xv is not None:
            if ours:xgf.append(xv);b["for"]+=xv;b["for_shots"]+=1
            else:xga.append(xv);b["against"]+=xv;b["against_shots"]+=1
        ov=xgot(shot)
        if ov is not None:
            if ours:xgotf.append(ov);b["for_xgot"]+=ov
            else:xgota.append(ov);b["against_xgot"]+=ov
        if ours:
            z=classify_shot(shot)
            if z: zones[z]+=1
    events=data.get("events",[]); specs={"passes":("pass","passes","successfulPasses","accuratePasses"),"recoveries":("recovery","recoveries","ballRecoveries"),"losses":("loss","losses","turnovers","possessionLost"),"tackles":("tackle","tackles"),"interceptions":("interception","interceptions"),"duels":("duel","duels"),"final_third_entries":("finalThirdEntries","final_third_entries","entriesFinalThird"),"possession":("possession","possessionPercent","possessionPercentage"),"corners":("corners","corner"),"free_kicks":("freeKicks","free_kicks")}; event_counts={}
    for name,keys in specs.items():
        vals=[]
        for e in events:
            if belongs_to_team(e,cfg): vals.extend(deep_values(e,keys))
        event_counts[name]=vals
    n=len(matches); players=data.get("players",[])
    metrics={"form":metric("".join(form[:5]) or None,min(5,len(form)),min(5,n),"result-code"),"goals_for":metric(sum(gf) if gf else None,len(gf),n,"goals"),"goals_against":metric(sum(ga) if ga else None,len(ga),n,"goals"),"goals_for_per_match":metric(round(sum(gf)/len(gf),2) if gf else None,n,n,"goals/match","derived" if gf else None),"goals_against_per_match":metric(round(sum(ga)/len(ga),2) if ga else None,n,n,"goals/match","derived" if ga else None),"xg":metric(round(sum(xgf),2) if xgf else None,len(xgf),len(shots),"goals"),"xga":metric(round(sum(xga),2) if xga else None,len(xga),len(shots),"goals"),"xgot":metric(round(sum(xgotf),2) if xgotf else None,len(xgotf),len(shots),"goals"),"xgot_against":metric(round(sum(xgota),2) if xgota else None,len(xgota),len(shots),"goals"),"xg_per_match":metric(round(sum(xgf)/n,2) if xgf and n else None,n,n,"goals/match","derived" if xgf else None),"xga_per_match":metric(round(sum(xga)/n,2) if xga and n else None,n,n,"goals/match","derived" if xga else None),"shots_count":metric(len(shots) or None,len(shots),len(shots),"shots"),"shots_with_xg":metric(len(xgf)+len(xga) if xgf or xga else None,len(xgf)+len(xga),len(shots),"shots"),"shots_for":metric(sum(v["for"] for v in shot_counts.values()) or None,sum(v["for"]>0 for v in shot_counts.values()),n,"shots"),"shots_against":metric(sum(v["against"] for v in shot_counts.values()) or None,sum(v["against"]>0 for v in shot_counts.values()),n,"shots"),"matches_sample":metric(n,n,n,"matches"),"players_count":metric(len(players) or None,len(players),len(players),"players"),"events_count":metric(len(events) or None,len(events),len(events),"events"),"spatial_actions_count":metric(len(data.get("spatial_actions",[])) or None,len(data.get("spatial_actions",[])),len(data.get("spatial_actions",[])),"actions")}
    for name,vals in event_counts.items(): metrics[name]=metric(round(sum(vals),2) if vals else None,len(vals),len(events),"provider-unit","observed" if vals else None)
    for mid,row in xb.items():
        if mid in match_metrics: match_metrics[mid].update({"xg":round(row["for"],3),"xga":round(row["against"],3),"xgot":round(row["for_xgot"],3),"xgot_against":round(row["against_xgot"],3),"shots_for":row["for_shots"],"shots_against":row["against_shots"]})
    # Player totals and per-90 are derived only when minutes are explicitly available.
    player_metrics=[]
    for p in players:
        s=p.get("stats") or {}; row={"fosi_id":p.get("fosi_id"),"player_id":p.get("provider_id"),"name":p.get("name"),"position":p.get("position"),"stats":s.copy(),"per90":{}}
        mins=num(s.get("minutes"));
        if mins and mins>0:
            for key in ("goals","assists","shots","shots_on_target","xg","xgot","key_passes","passes","accurate_passes","tackles","interceptions","duels","recoveries","turnovers","fouls","touches","touches_opp_box","final_third_entries"):
                v=num(s.get(key))
                if v is not None: row["per90"][key]=round(v*90/mins,2)
        player_metrics.append(row)
    out={"schema_version":"1.4","model":"FOSI metrics","generated_at":datetime.now(timezone.utc).isoformat(),"scope":{"country":cfg["country"],"competition":cfg["competition"],"team":cfg["team"],"team_id":cfg["team_id"]},"method":"deterministic-from-normalized","source_normalized":str(src).replace("\\","/"),"metrics":metrics,"xg_by_match":dict(xb),"match_metrics":list(match_metrics.values()),"shot_zones_for":dict(zones),"recent_matches":matches[:20],"player_metrics":player_metrics,"coverage":{"normalized_records":sum(len(data.get(k,[])) for k in ("matches","players","events","shots","spatial_actions")),"attributed_shots":attributed}}
    (root/"normalized"/"metrics.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps({k:v["value"] for k,v in metrics.items()},ensure_ascii=False))
if __name__=="__main__": main()
