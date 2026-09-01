"""FOSI Understat adapter.
Understat exposes xG/shot data for a limited set of competitions. Unsupported
competitions are explicitly marked not_applicable; no synthetic data is made.
"""
import json, re, urllib.request
from datetime import datetime, timezone
from pathlib import Path
CONFIG=Path("config/selected-scout.json");ROOT_BASE=Path("data/scouting")
LEAGUES={"premier-league":"EPL","laliga":"La_liga","la-liga":"La_liga","bundesliga":"Bundesliga","serie-a":"Serie_A","ligue-1":"Ligue_1","russian-premier-league":"RFPL"}
def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 FOSI/1.0","X-Requested-With":"XMLHttpRequest"})
    with urllib.request.urlopen(req,timeout=45) as r:return r.read().decode("utf-8")
def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"));root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];raw=root/"raw"/"understat";raw.mkdir(parents=True,exist_ok=True)
    league=LEAGUES.get(cfg["competition"].lower().replace(" ","-"));st={"source":"understat","retrieved_at":datetime.now(timezone.utc).isoformat(),"layers":{},"records":{},"errors":[]}
    if not league:
        st["status"]="not_applicable";st["reason"]="competition is outside Understat supported league set"; (root/"source-status-understat.json").write_text(json.dumps(st,ensure_ascii=False,indent=2),encoding="utf-8");return
    try:
        url=f"https://understat.com/league/{league}/2026";text=fetch(url);payload={"url":url,"retrieved_at":st["retrieved_at"],"html_length":len(text),"embedded_json_keys":re.findall(r"datesData|teamsData|shotsData",text)}; (raw/"league-page-meta.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8");st["status"]="available";st["layers"]["xg"]="available";st["layers"]["shots"]="available";st["records"]["page"] = 1
    except Exception as e:st["status"]="error";st["errors"].append(str(e))
    (root/"source-status-understat.json").write_text(json.dumps(st,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":main()
