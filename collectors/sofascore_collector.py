"""FOSI SofaScore acquisition: direct API + protected authorized egress + browser SPA capture.

Direct public endpoints are attempted first. When the GitHub Actions egress is blocked,
FOSI can use either an operator-provided HTTP proxy (SOFASCORE_PROXY) or a protected
reverse gateway (SOFASCORE_GATEWAY_URL + SOFASCORE_GATEWAY_TOKEN). Nothing is fabricated.
"""
import json,re,time,os
from datetime import datetime,timezone
from pathlib import Path

CONFIG=Path("config/selected-scout.json");ROOT_BASE=Path("data/scouting")
BASES=["https://api.sofascore.com/api/v1","https://api.sofascore.app/api/v1","https://www.sofascore.com/api/v1"]
DETAILS=("event","statistics","incidents","lineups","graph","shotmap","media")


def save(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")


def get_json(path):
    """Fetch SofaScore JSON using direct access, an HTTP proxy, or the protected gateway."""
    last=None;telemetry=[]
    proxy=os.getenv("SOFASCORE_PROXY","").strip() or None
    gateway=os.getenv("SOFASCORE_GATEWAY_URL","").strip().rstrip("/") or None
    gateway_token=os.getenv("SOFASCORE_GATEWAY_TOKEN","").strip() or None
    if gateway and gateway_token:
        url=f"{gateway}/api/v1{path}"
        try:
            from curl_cffi import requests
            s=requests.Session(impersonate="chrome")
            s.headers.update({"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36","Accept":"application/json, text/plain, */*","Accept-Language":"en-US,en;q=0.9","Authorization":f"Bearer {gateway_token}"})
            for attempt in range(3):
                try:
                    r=s.get(url,timeout=35,allow_redirects=True)
                    telemetry.append({"base":"gateway","status":r.status_code,"attempt":attempt+1,"transport":"curl_cffi_gateway","proxy_configured":False})
                    if r.status_code in (403,429): last=RuntimeError(f"HTTP {r.status_code} from SofaScore gateway");time.sleep(1.5*(attempt+1));continue
                    r.raise_for_status();return r.json(),gateway,telemetry
                except Exception as e:last=e;time.sleep(.8*(attempt+1))
        except Exception as e:last=e
    try:
        from curl_cffi import requests
        session=requests.Session(impersonate="chrome")
        if proxy: session.proxies={"http":proxy,"https":proxy}
        session.headers.update({"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36","Accept":"application/json, text/plain, */*","Accept-Language":"en-US,en;q=0.9","Referer":"https://www.sofascore.com/","Origin":"https://www.sofascore.com","X-Requested-With":"XMLHttpRequest","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-site"})
        for base in BASES:
            url=base+path
            for attempt in range(3):
                try:
                    r=session.get(url,timeout=35,allow_redirects=True)
                    telemetry.append({"base":base,"status":r.status_code,"attempt":attempt+1,"transport":"curl_cffi","proxy_configured":bool(proxy)})
                    if r.status_code in (403,429): last=RuntimeError(f"HTTP {r.status_code} from {base}");time.sleep(1.5*(attempt+1));continue
                    r.raise_for_status();return r.json(),base,telemetry
                except Exception as e:last=e;time.sleep(.8*(attempt+1))
    except Exception as e:last=e
    for base in BASES:
        try:
            import urllib.request
            req=urllib.request.Request(base+path,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json, text/plain, */*","Referer":"https://www.sofascore.com/","Origin":"https://www.sofascore.com","X-Requested-With":"XMLHttpRequest"})
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({"http":proxy,"https":proxy}) if proxy else urllib.request.ProxyHandler({}))
            with opener.open(req,timeout=35) as r:
                telemetry.append({"base":base,"status":getattr(r,"status",200),"transport":"urllib","proxy_configured":bool(proxy)})
                return json.load(r),base,telemetry
        except Exception as e:last=e
    raise last


def slugify(value):
    value=str(value or "").lower().replace("&","and");value=re.sub(r"[^a-z0-9]+","-",value).strip("-");return value


def event_page_url(event):
    custom=str(event.get("customId") or "");slug=str(event.get("slug") or "")
    if slug and custom:return f"https://www.sofascore.com/football/match/{slug}/{custom}"
    home=(event.get("homeTeam") or {}).get("slug") or (event.get("homeTeam") or {}).get("name");away=(event.get("awayTeam") or {}).get("slug") or (event.get("awayTeam") or {}).get("name")
    if home and away and custom:return f"https://www.sofascore.com/football/match/{slugify(home)}-{slugify(away)}/{custom}"
    return f"https://www.sofascore.com/football/match/{custom or event.get('id')}/{custom or event.get('id')}"


def browser_capture(tid,team_name,events,raw,st):
    try:from playwright.sync_api import sync_playwright
    except Exception as e:st["errors"].append({"layer":"browser","error":f"Playwright unavailable: {e}"});return {}
    captured={};visited=0;team_slug=slugify(team_name) or "pogon-szczecin";team_url=f"https://www.sofascore.com/football/team/{team_slug}/{tid}";wanted=set(DETAILS)
    ua="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    with sync_playwright() as p:
        try:browser=p.chromium.launch(channel="chrome",headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
        except Exception:browser=p.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
        context=browser.new_context(user_agent=ua,locale="en-US",viewport={"width":1440,"height":1200},extra_http_headers={"Accept-Language":"en-US,en;q=0.9","X-Requested-With":"XMLHttpRequest"})
        page=context.new_page();page.set_default_timeout(5000)
        def on_response(resp):
            url=resp.url
            if "api.sofascore.com/api/v1/" not in url or resp.request.resource_type not in {"xhr","fetch"}:return
            try:
                key=url.split("/api/v1/",1)[-1].split("?",1)[0].strip("/");parts=key.split("/")
                if len(parts)<2 or parts[0]!="event":return
                eid=parts[1]
                if len(parts)==2:rest="event"
                elif len(parts)>=4 and parts[2]=="player":rest="player/"+parts[3]+("/"+parts[4] if len(parts)>4 else "")
                else:rest=parts[2]
                if rest not in wanted and not rest.startswith("player/"):return
                captured[(eid,rest)]=resp.json()
            except BaseException:pass
        page.on("response",on_response)
        def click_text(patterns):
            for label in patterns:
                try:
                    loc=page.get_by_role("link",name=re.compile(rf"^{re.escape(label)}$",re.I))
                    if loc.count():loc.first.click(timeout=3000);page.wait_for_timeout(1800);return True
                except BaseException:pass
                try:
                    loc=page.get_by_text(label,exact=True)
                    if loc.count():loc.first.click(timeout=3000);page.wait_for_timeout(1800);return True
                except BaseException:pass
            return False
        def prime_team_page():
            try:
                page.goto(team_url,wait_until="domcontentloaded",timeout=60000);page.wait_for_timeout(7000);click_text(("Matches","Partidos","Resultados"))
                for _ in range(14):page.evaluate("window.scrollBy(0, Math.max(800, window.innerHeight*0.95))");page.wait_for_timeout(500)
            except BaseException as e:st["errors"].append({"layer":"browser_team_page","error":str(e)})
        prime_team_page();hrefs=[]
        try:hrefs=page.locator('a[href*="/football/match/"]').evaluate_all("els => els.map(e => e.href)")
        except BaseException:pass
        candidates=list(dict.fromkeys(hrefs+[event_page_url(e) for e in events]));st["browser_discovery"]={"team_url":team_url,"dom_match_links":len(hrefs),"candidate_pages":len(candidates)}
        for href in candidates:
            try:
                page.goto(href,wait_until="domcontentloaded",timeout=50000);page.wait_for_timeout(2800)
                for labels in (("Statistics","Estadísticas","Stats"),("Lineups","Alineaciones"),("Media","Videos","Vídeos")):click_text(labels)
                for _ in range(10):page.evaluate("window.scrollBy(0, Math.max(700, window.innerHeight*0.85))");page.wait_for_timeout(450)
                visited+=1
            except BaseException as e:st.setdefault("browser_errors",[]).append({"url":href,"error":str(e)})
        browser.close()
    for (eid,kind),payload in captured.items():
        if kind.startswith("player/"):
            parts=kind.split("/");save(raw/"matches"/eid/"players"/parts[1]/((parts[2] if len(parts)>2 else "data")+".json"),payload)
        else:save(raw/"matches"/eid/(kind+".json"),payload)
    st["browser_capture"]={"captured_match_layers":len(captured),"unique_matches":len({k[0] for k in captured}),"pages_visited":visited,"candidate_pages":len(candidates)};return captured


def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"));root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];raw=root/"raw"/"sofascore";proxy=bool(os.getenv("SOFASCORE_PROXY","").strip());gateway=bool(os.getenv("SOFASCORE_GATEWAY_URL","").strip() and os.getenv("SOFASCORE_GATEWAY_TOKEN","").strip());st={"source":"sofascore","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"layers":{},"records":{},"errors":[],"attempted_bases":BASES,"proxy_configured":proxy,"gateway_configured":gateway}
    try:
        tid=str((cfg.get("provider_ids") or {}).get("sofascore") or "");team_name=cfg.get("team") or "";events=[]
        if not tid:raise RuntimeError("SofaScore team id not configured")
        try:
            data,base,telemetry=get_json(f"/team/{tid}");save(raw/"team.json",data);st["base_used"]=base;st["transport_telemetry"]=telemetry;st["layers"]["team"]="available";st["records"]["team"]=1;squad,_,_=get_json(f"/team/{tid}/players");save(raw/"squad.json",squad);st["layers"]["players"]="available";st["records"]["players"]=len(squad.get("players",[]))
        except Exception as e:st["errors"].append({"layer":"direct_team_api","error":str(e)})
        try:
            for page_no in range(40):
                p,_,_=get_json(f"/team/{tid}/events/last/{page_no}");save(raw/"events"/f"last-{page_no}.json",p);batch=p.get("events",[]);events.extend(batch)
                if not p.get("hasNextPage") or not batch:break
            events=list({str(e.get("id")):e for e in events if e.get("id")}.values());save(raw/"events.json",{"events":events});st["records"]["matches"]=len(events)
        except Exception as e:st["errors"].append({"layer":"matches","error":str(e)})
        counts={k:0 for k in DETAILS}
        for e in events:
            eid=str(e["id"])
            for kind in DETAILS:
                dest=raw/"matches"/eid/(kind+".json")
                if dest.exists():counts[kind]+=1;continue
                try:payload,_,_=get_json(f"/event/{eid}" if kind=="event" else f"/event/{eid}/{kind}");save(dest,payload);counts[kind]+=1
                except Exception:pass
                time.sleep(.12)
        missing=not events or any(counts[k]<len(events) for k in ("event","statistics","incidents","lineups","shotmap","media"))
        if missing and not (st["errors"] and not events):browser_capture(tid,team_name,events,raw,st)
        for k in counts:counts[k]=sum(1 for e in events if (raw/"matches"/str(e["id"])/(k+".json")).exists())
        st["records"].update(counts);st["layers"]["matches"]="available" if events else "partial";st["layers"]["stats"]="available" if counts["statistics"] else "partial";st["layers"]["events"]="available" if counts["incidents"] else "partial";st["layers"]["spatial"]="available" if counts["shotmap"] else "partial";st["layers"]["lineups"]="available" if counts["lineups"] else "partial";st["layers"]["video"]="available" if counts["media"] else "unavailable"
        all403=bool(st.get("transport_telemetry")) and all(x.get("status") in (403,429) for x in st["transport_telemetry"] if x.get("transport") in {"curl_cffi","curl_cffi_gateway"})
        if all403:st["waf_blocked"]=True;st["blocked_by_egress"]=not (proxy or gateway)
        st["status"]="success" if not st["errors"] else "partial"
    except Exception as exc:st["status"]="error";st["errors"].append({"fatal":str(exc)})
    save(root/"source-status-sofascore.json",st)
if __name__=="__main__":main()
