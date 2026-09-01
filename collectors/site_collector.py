"""Generic public-site collector for official club/competition pages.
It preserves HTML as raw evidence and does not infer structured fields from markup.
"""
import json, urllib.request
from datetime import datetime, timezone
from pathlib import Path
CONFIG=Path("config/selected-scout.json");ROOT_BASE=Path("data/scouting")
def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 FOSI/1.0","Accept":"text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req,timeout=45) as r:return r.read()
def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"));root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];raw=root/"raw"/"sites";raw.mkdir(parents=True,exist_ok=True)
    urls=cfg.get("public_site_urls",[]);st={"source":"official-sites","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"layers":{},"records":{},"errors":[]}
    for i,url in enumerate(urls):
        try:
            body=fetch(url);(raw/f"site-{i}.html").write_bytes(body);st["records"][url] = len(body);st["layers"]["news"]="available"
        except Exception as e:st["errors"].append({"url":url,"error":str(e)})
    st["status"]="success" if urls and not st["errors"] else "partial" if st["records"] else "error" if urls else "not_configured"
    (root/"source-status-official-sites.json").write_text(json.dumps(st,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":main()
