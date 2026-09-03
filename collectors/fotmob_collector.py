"""FOSI FotMob collector with dynamic team resolution and raw preservation."""
import json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
BASE="https://www.fotmob.com/api/data";CONFIG=Path("config/selected-scout.json");ROOT_BASE=Path("data/scouting")
def get_json(path):
    req=urllib.request.Request(BASE+path,headers={"User-Agent":"Mozilla/5.0 FOSI/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=45) as r:return json.load(r)
def save(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
def resolve_team(name):
    data=get_json("/search/suggest?term="+urllib.parse.quote(name)+"&hits=50&lang=en");exact=None;fallback=None
    for item in data.get("suggestions",data.get("results",[])):
        typ=item.get("type") or item.get("entityType");ent=item.get("entity") or item
        if typ in {"team","teams"}:
            n=ent.get("name") or ent.get("title") or "";tid=ent.get("id")
            if n.lower()==name.lower():exact=str(tid);break
            if name.lower() in n.lower():fallback=str(tid)
    return exact or fallback,data
def walk_matches(node):
    out=[]
    if isinstance(node,dict):
        if {"id","home","away"}.issubset(node) and isinstance(node["home"],dict) and isinstance(node["away"],dict):out.append(node)
        for v in node.values():out+=walk_matches(v)
    elif isinstance(node,list):
        for v in node:out+=walk_matches(v)
    return out
def finished(m):
    s=m.get("status") or {};return bool(s.get("finished") or (s.get("reason") or {}).get("short") in {"FT","AET","PEN"})
def team_match(m,name):
    ns=[(m.get("home") or {}).get("name"),(m.get("home") or {}).get("longName"),(m.get("away") or {}).get("name"),(m.get("away") or {}).get("longName")];return any(name.lower() in str(x).lower() for x in ns if x)
def find_first(node,keys):
    wanted={k.lower() for k in keys}
    if isinstance(node,dict):
        for k,v in node.items():
            if k.lower() in wanted and isinstance(v,str) and v.strip(): return v
            found=find_first(v,keys)
            if found:return found
    elif isinstance(node,list):
        for v in node:
            found=find_first(v,keys)
            if found:return found
    return None
def collect_team_player_ids(node,team_id,out=None):
    out=out if out is not None else set()
    if isinstance(node,dict):
        tid=node.get("teamId",node.get("team_id")); pid=node.get("playerId",node.get("player_id"))
        if pid is None and "id" in node and any(k in node for k in ("name","fullName","playerName")): pid=node.get("id")
        if pid is not None and tid is not None and str(tid)==str(team_id): out.add(str(pid))
        for v in node.values(): collect_team_player_ids(v,team_id,out)
    elif isinstance(node,list):
        for v in node: collect_team_player_ids(v,team_id,out)
    return out
def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"));st={"source":"fotmob","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"layers":{},"records":{},"errors":[]}
    if not cfg.get("enabled") or not cfg.get("team"):return
    root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];raw=root/"raw"/"fotmob";raw.mkdir(parents=True,exist_ok=True)
    try:
        tid=str((cfg.get("provider_ids") or {}).get("fotmob") or "")
        if not tid:
            tid,search=resolve_team(cfg["team"]);save(raw/"search.json",search)
        if not tid:raise RuntimeError("FotMob team id could not be resolved")
        team=get_json(f"/teams?id={tid}&ccode3=POL");save(raw/"team.json",team);st["layers"].update({"team":"available","players":"available"});st["records"]["team"]=1;st["team_id"]=tid
        player_ids=sorted(collect_team_player_ids(team,tid))
        profile_count=0
        for pid in player_ids[:40]:
            try: save(raw/"players"/(pid+".json"),get_json(f"/playerData?id={pid}&includeMarketValues=true")); profile_count+=1
            except Exception as pe: st["errors"].append({"player_id":pid,"player_error":str(pe)})
        st["records"]["player_profiles"]=profile_count
        try:
            save(raw/"transfers.json",get_json(f"/transfers?teamId={tid}"));st["records"]["transfers"]=1
        except Exception as te:
            st["errors"].append({"transfers_error":str(te)})
        matches={str(m["id"]):m for m in walk_matches(team) if team_match(m,cfg["team"]) and finished(m)};matches=sorted(matches.values(),key=lambda m:str((m.get("status") or {}).get("utcTime") or m.get("timeTS") or ""),reverse=True)
        st["layers"]["matches"]="available" if matches else "pending";st["records"]["matches"]=len(matches);detail=0;heatmaps=0;errors=[]
        for m in matches:
            mid=str(m["id"])
            try:
                detail_payload=get_json(f"/matchDetails?matchId={mid}");save(raw/"matches"/(mid+".json"),detail_payload);detail+=1
                heatmap_url=find_first(detail_payload,("heatmapUrl","heatmapURL"))
                if heatmap_url:
                    q=urllib.parse.urlencode({"heatmapUrl":heatmap_url})
                    try:
                        save(raw/"heatmaps"/(mid+".json"),get_json(f"/heatmap/match/{mid}/heatmaps?{q}"));heatmaps+=1
                    except Exception as he: errors.append({"match_id":mid,"heatmap_error":str(he)})
            except Exception as e:errors.append({"match_id":mid,"error":str(e)})
        st["records"]["match_details"]=detail;st["records"]["heatmaps"]=heatmaps;st["layers"].update({"stats":"available" if detail else "pending","events":"available" if detail else "pending","spatial":"available" if heatmaps else ("available" if detail else "pending")});st["errors"].extend(errors);st["status"]="success" if not st["errors"] else "partial"
    except Exception as e:st["status"]="error";st["errors"].append({"fatal":str(e)})
    save(root/"source-status-fotmob.json",st);save(root/"status-fotmob.json",st)
if __name__=="__main__":main()