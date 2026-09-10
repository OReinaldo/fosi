"""Dedicated SofaScore web-app capture fallback with optional authorized egress."""
import json,re,unicodedata,os
from datetime import datetime,timezone
from pathlib import Path

CONFIG=Path("config/selected-scout.json");ROOT=Path("data/scouting")
DETAILS={"event","statistics","incidents","lineups","graph","shotmap","media"}
API_BASES=("https://api.sofascore.com/api/v1","https://www.sofascore.com/api/v1","https://www.sofascore.app/api/v1")


def save(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    if isinstance(payload,(bytes,bytearray)): path.write_bytes(payload)
    else: path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

def slugify(value):
    s=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+","-",s).strip("-")

def extract_match_urls(text):
    if not text:return []
    text=text.replace('\\\\/','/')
    patterns=[r"https?://www\.sofascore\.com/(?:[a-z]{2}/)?football/match/[^\"'<>\s\\]+",r"/(?:[a-z]{2}/)?football/match/[^\"'<>\s\\]+"]
    found=[]
    for pattern in patterns:found.extend(re.findall(pattern,text,flags=re.I))
    normalized=[]
    for value in found:
        if value.startswith('/'):value='https://www.sofascore.com'+value
        value=value.rstrip('.,);]')
        if '/football/match/' in value:normalized.append(value)
    return list(dict.fromkeys(normalized))

def make_session():
    from curl_cffi import requests
    s=requests.Session(impersonate="chrome");proxy=os.getenv("SOFASCORE_PROXY","").strip()
    if proxy:s.proxies={"http":proxy,"https":proxy}
    s.headers.update({"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36","X-Requested-With":"XMLHttpRequest"})
    return s

def common_headers(referer="https://www.sofascore.com/"):
    return {"Accept":"text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8","Accept-Language":"en-US,en;q=0.9","Cache-Control":"no-cache","Pragma":"no-cache","Referer":referer,"X-Requested-With":"XMLHttpRequest"}

def probe_official_hosts(team_id):
    result={"hosts":[],"event_pages":[],"usable_api_base":None,"proxy_configured":bool(os.getenv("SOFASCORE_PROXY","" ).strip())}
    try:
        session=make_session()
        for url in ("https://www.sofascore.com/","https://www.sofascore.com/en"):
            try:
                r=session.get(url,headers=common_headers(),timeout=20);result["hosts"].append({"url":url,"status_code":r.status_code,"bytes":len(r.content),"proxy_configured":result["proxy_configured"]})
            except Exception as exc:result["hosts"].append({"url":url,"error":str(exc)})
        for base in API_BASES:
            url=f"{base}/team/{team_id}/events/last/0"
            try:
                r=session.get(url,headers={**common_headers(),"Accept":"application/json,text/plain,*/*"},timeout=25);item={"url":url,"status_code":r.status_code,"bytes":len(r.content)}
                if r.status_code==200:
                    try:
                        payload=r.json();events=payload.get("events") or [];item["events"]=len(events);result["event_pages"].append({"base":base,"page":0,"payload":payload})
                        if events and result["usable_api_base"] is None:result["usable_api_base"]=base
                    except Exception as exc:item["json_error"]=str(exc)
                result["hosts"].append(item)
            except Exception as exc:result["hosts"].append({"url":url,"error":str(exc)})
    except Exception as exc:result["error"]=str(exc)
    return result

def fetch_direct_api_events(team_id,raw,probe):
    base=probe.get("usable_api_base");
    if not base:return []
    events=[]
    for item in probe.get("event_pages",[]):
        for event in (item.get("payload") or {}).get("events") or []:
            eid=str(event.get("id") or "")
            if eid:events.append(eid)
    ids=list(dict.fromkeys(events))
    all_events=[e for item in probe.get("event_pages",[]) for e in (item.get("payload") or {}).get("events") or []]
    for eid in ids:save(raw/"matches"/eid/"event.json",{"_discovery":True,"event":next((e for e in all_events if str(e.get("id"))==eid),{})})
    return ids

def discover_ssr(team_url):
    try:
        session=make_session();response=session.get(team_url,headers=common_headers("https://www.google.com/"),timeout=30);meta={"status_code":response.status_code,"bytes":len(response.content)}
        if response.status_code>=400:return [],meta
        return extract_match_urls(response.text),meta
    except Exception as exc:return [],{"error":str(exc)}

def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"));country=cfg["country"].lower().replace(" ","-");competition=cfg["competition"].lower().replace(" ","-");team_id=cfg["team_id"];root=ROOT/country/competition/team_id;raw=root/"raw"/"sofascore";status={"source":"sofascore-spa","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"records":{},"errors":[],"proxy_configured":bool(os.getenv("SOFASCORE_PROXY","" ).strip())}
    tid=str((cfg.get("provider_ids") or {}).get("sofascore") or "")
    if not tid:status["status"]="error";status["errors"].append({"error":"missing SofaScore team id"});save(root/"source-status-sofascore-spa.json",status);return
    probe=probe_official_hosts(tid);status["official_host_probe"]={k:v for k,v in probe.items() if k!="event_pages"};direct_ids=fetch_direct_api_events(tid,raw,probe);status["direct_api_discovery"]={"unique_matches":len(direct_ids),"usable_api_base":probe.get("usable_api_base")}
    team_url=f"https://www.sofascore.com/football/team/{slugify(cfg.get('team'))}/{tid}";ssr_candidates,ssr_meta=discover_ssr(team_url);status["ssr_discovery"]={"team_url":team_url,"candidate_pages":len(ssr_candidates),**ssr_meta}
    try:from playwright.sync_api import sync_playwright
    except Exception as exc:status["status"]="error";status["errors"].append({"error":f"Playwright unavailable: {exc}"});save(root/"source-status-sofascore-spa.json",status);return
    captured={};visited=0
    with sync_playwright() as p:
        try:browser=p.chromium.launch(channel="chrome",headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
        except Exception:browser=p.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
        context=browser.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36",locale="en-US",viewport={"width":1440,"height":1200},extra_http_headers={"X-Requested-With":"XMLHttpRequest","Accept-Language":"en-US,en;q=0.9"});page=context.new_page();page.set_default_timeout(7000)
        def on_response(resp):
            if "api.sofascore.com/api/v1/" not in resp.url or resp.request.resource_type not in {"xhr","fetch"}:return
            try:
                parts=resp.url.split("/api/v1/",1)[1].split("?",1)[0].strip("/").split("/")
                if len(parts)<2 or parts[0]!="event":return
                eid=parts[1];asset="event" if len(parts)==2 else ("player/"+parts[3]+("/"+parts[4] if len(parts)>4 else "") if len(parts)>=4 and parts[2]=="player" else parts[2])
                if asset in DETAILS or asset.startswith("player/"):captured[(eid,asset)]=resp.json()
            except Exception:pass
        page.on("response",on_response)
        try:
            candidates=list(ssr_candidates)
            if not candidates:
                try:
                    page.goto("https://www.sofascore.com/",wait_until="domcontentloaded",timeout=60000);page.wait_for_timeout(3000);page.goto(team_url,wait_until="domcontentloaded",timeout=60000);page.wait_for_timeout(7000)
                    for _ in range(16):page.evaluate("window.scrollBy(0, Math.max(900, window.innerHeight))");page.wait_for_timeout(450)
                    candidates=list(dict.fromkeys(page.locator('a[href*="/football/match/"]').evaluate_all("els => els.map(e => e.href)")+extract_match_urls(page.content())))
                except Exception as exc:status["errors"].append({"layer":"spa_discovery","error":str(exc)})
            status["discovery"]={"team_url":team_url,"candidate_pages":len(candidates),"source":"ssr" if ssr_candidates else "spa"}
            for href in candidates:
                try:
                    page.goto(href,wait_until="domcontentloaded",timeout=50000);page.wait_for_timeout(3000)
                    for labels in (("Statistics","Estadísticas","Stats"),("Lineups","Alineaciones"),("Media","Videos","Vídeos")):
                        for label in labels:
                            try:
                                loc=page.get_by_text(label,exact=True)
                                if loc.count():loc.first.click(timeout=2500);page.wait_for_timeout(1200);break
                            except Exception:pass
                    for _ in range(8):page.evaluate("window.scrollBy(0, Math.max(700, window.innerHeight*.85))");page.wait_for_timeout(350)
                    visited+=1
                except Exception as exc:status["errors"].append({"url":href,"error":str(exc)})
            for (eid,asset),payload in captured.items():
                if asset.startswith("player/"):
                    parts=asset.split("/");save(raw/"matches"/eid/"players"/parts[1]/((parts[2] if len(parts)>2 else "data")+".json"),payload)
                else:save(raw/"matches"/eid/(asset+".json"),payload)
        finally:browser.close()
    status["browser_capture"]={"pages_visited":visited,"captured_layers":len(captured),"unique_matches":len({k[0] for k in captured})};status["records"]={k:sum(1 for eid in {x[0] for x in captured} if (raw/"matches"/eid/(k+".json")).exists()) for k in DETAILS}
    all403=all(x.get("status_code") in (403,429) for x in probe.get("hosts",[]) if "status_code" in x and "/api/v1/" in x.get("url", ""))
    if all403:status["waf_blocked"]=True;status["blocked_by_egress"]=not status["proxy_configured"]
    status["status"]="success" if captured or direct_ids else "partial";save(root/"source-status-sofascore-spa.json",status)
if __name__=="__main__":main()
