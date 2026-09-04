"""Generic public-site collector for official club/competition pages.

HTML is preserved verbatim. In addition, machine-readable JSON embedded by the
public site (JSON-LD, Next.js hydration and generic application/json scripts) is
extracted without inventing or transforming business fields.
"""
import json,re,urllib.request,html
from datetime import datetime,timezone
from pathlib import Path
CONFIG=Path("config/selected-scout.json");ROOT_BASE=Path("data/scouting")

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 FOSI/2.0","Accept":"text/html,application/xhtml+xml","Accept-Language":"en,pl;q=0.8"})
    with urllib.request.urlopen(req,timeout=45) as r:return r.read()

def layer_for(url):
    u=url.lower()
    if "tabela" in u:return "standings"
    if "statystyki" in u:return "stats"
    if "schedule" in u or "terminarz" in u:return "fixtures"
    if "news" in u:return "news"
    return "context"

def embedded_json(body):
    text=body.decode("utf-8","ignore")
    out=[]
    # JSON-LD and framework hydration payloads are often the richest structured
    # layer on official pages and can be consumed later by the normalizer.
    patterns=[r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>']
    for pattern in patterns:
        for raw in re.findall(pattern,text,re.I|re.S):
            raw=html.unescape(raw).strip()
            try:out.append(json.loads(raw))
            except Exception:pass
    return out

def extract_links(body,base_url):
    text=body.decode("utf-8","ignore")
    links=[]
    for href in re.findall(r'<a[^>]+href=["\']([^"\']+)["\']',text,re.I):
        if href.startswith("/"):
            from urllib.parse import urljoin
            href=urljoin(base_url,href)
        if href.startswith("http") and href not in links:links.append(href)
    return links[:5000]

def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"));root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];raw=root/"raw"/"sites";raw.mkdir(parents=True,exist_ok=True)
    urls=cfg.get("public_site_urls",[]);st={"source":"official-sites","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"layers":{},"records":{},"errors":[],"structured_records":0,"links":0}
    for i,url in enumerate(urls):
        layer=layer_for(url)
        try:
            body=fetch(url);(raw/f"site-{i}.html").write_bytes(body)
            emb=embedded_json(body);links=extract_links(body,url)
            if emb:(raw/f"site-{i}.embedded.json").write_text(json.dumps({"source_url":url,"layer":layer,"records":emb},ensure_ascii=False,indent=2),encoding="utf-8")
            if links:(raw/f"site-{i}.links.json").write_text(json.dumps({"source_url":url,"links":links},ensure_ascii=False,indent=2),encoding="utf-8")
            st["records"][url]={"bytes":len(body),"layer":layer,"embedded_json_records":len(emb),"links":len(links)};st["structured_records"]+=len(emb);st["links"]+=len(links);st["layers"][layer]="available"
        except Exception as e:st["errors"].append({"url":url,"layer":layer,"error":str(e)})
    st["status"]="success" if urls and not st["errors"] else "partial" if st["records"] else "error" if urls else "not_configured"
    (root/"source-status-official-sites.json").write_text(json.dumps(st,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":main()
