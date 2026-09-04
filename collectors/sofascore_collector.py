"""FOSI SofaScore acquisition: direct API + resilient real-browser SPA capture, raw-first.

SofaScore may challenge direct API traffic. When that happens FOSI uses the public
SofaScore web application itself and records the JSON responses emitted by the SPA.
Nothing is fabricated and raw payloads remain the source of truth.
"""
import json,re,time,urllib.parse
from datetime import datetime,timezone
from pathlib import Path

CONFIG=Path("config/selected-scout.json");ROOT_BASE=Path("data/scouting")
BASES=["https://api.sofascore.com/api/v1","https://www.sofascore.app/api/v1","https://www.sofascore.com/api/v1"]
DETAILS=("event","statistics","incidents","lineups","graph","shotmap","media")

def save(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

def get_json(path):
    """Try a Chrome-like TLS client first, then standard urllib against public routes."""
    last=None
    try:
        from curl_cffi import requests
        for base in BASES:
            try:
                r=requests.get(base+path,headers={"Accept":"application/json","Referer":"https://www.sofascore.com/","Origin":"https://www.sofascore.com"},timeout=35,impersonate="chrome")
                r.raise_for_status();return r.json(),base
            except Exception as e:last=e
    except Exception as e:last=e
    for base in BASES:
        try:
            import urllib.request
            req=urllib.request.Request(base+path,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json","Referer":"https://www.sofascore.com/"})
            with urllib.request.urlopen(req,timeout=35) as r:return json.load(r),base
        except Exception as e:last=e
    raise last

def slugify(value):
    value=str(value or "").lower().replace("&","and");value=re.sub(r"[^a-z0-9]+","-",value).strip("-");return value

def event_page_url(event):
    eid=str(event.get("id") or "");slug=event.get("slug") or "";custom=event.get("customId") or ""
    if slug and custom:return f"https://www.sofascore.com/football/match/{slug}/{custom}"
    home=(event.get("homeTeam") or {}).get("slug") or (event.get("homeTeam") or {}).get("name");away=(event.get("awayTeam") or {}).get("slug") or (event.get("awayTeam") or {}).get("name")
    if home and away and custom:return f"https://www.sofascore.com/football/match/{slugify(away)}-{slugify(home)}/{custom}"
    return f"https://www.sofascore.com/football/match/{custom or eid}/{custom or eid}"

def browser_capture(tid,team_name,events,raw,st):
    """Drive the public SPA and capture per-match API JSON."""
    try:from playwright.sync_api import sync_playwright
    except Exception as e:st["errors"].append({"layer":"browser","error":f"Playwright unavailable: {e}"});return {}
    captured={};visited=0;team_slug=slugify(team_name) or "pogon-szczecin";team_url=f"https://www.sofascore.com/football/team/{team_slug}/{tid}";wanted=set(DETAILS)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--disable-blink-features=AutomationControlled","--no-sandbox"]);context=browser.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36",locale="en-US",viewport={"width":1440,"height":1100});page=context.new_page();current_event=[None]
        def on_response(resp):
            url=resp.url
            if "api.sofascore.com/api/v1/" not in url or resp.request.resource_type not in {"xhr","fetch"}:return
            try:
                key=url.split("/api/v1/",1)[-1].split("?",1)[0].strip("/");parts=key.split("/")
                if len(parts)<2 or parts[0]!="event":return
                eid=parts[1];rest=parts[2] if len(parts)>=3 else "event"
                if rest not in wanted:return
                captured[(eid,rest)]=resp.json()
            except BaseException:pass
        page.on("response",on_response)
        try:page.goto(team_url,wait_until="domcontentloaded",timeout=60000);page.wait_for_timeout(5000);page.evaluate("window.scrollTo(0, document.body.scrollHeight)");page.wait_for_timeout(2500)
        except BaseException as e:st["errors"].append({"layer":"browser_team_page","error":str(e)})
        hrefs=[]
        try:hrefs=page.locator('a[href*="/football/match/"]').evaluate_all("els => els.map(e => e.href)")
        except BaseException:pass
        candidates=list(dict.fromkeys(list(hrefs)+[event_page_url(e) for e in events if "/football/match/" in event_page_url(e)]));target_ids={str(e.get("id")):e for e in events if e.get("id")}
        for href in candidates:
            try:
                page.goto(href,wait_until="domcontentloaded",timeout=50000);page.wait_for_timeout(1800)
                for label in ("Statistics","Lineups","Stats","Alineaciones","Estadísticas","Media","Videos","Vídeos"):
                    try:
                        loc=page.get_by_text(label,exact=True)
                        if loc.count():loc.first.click(timeout=2500);page.wait_for_timeout(1000)
                    except BaseException:pass
                for _ in range(4):page.evaluate("window.scrollBy(0, Math.max(500, window.innerHeight*0.9))");page.wait_for_timeout(500)
                visited+=1
            except BaseException:continue
            if visited and visited%45==0:
                try:context.close()
                except BaseException:pass
                context=browser.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36",locale="en-US",viewport={"width":1440,"height":1100});page=context.new_page();page.on("response",on_response)
                try:page.goto(team_url,wait_until="domcontentloaded",timeout=50000);page.wait_for_timeout(3000)
                except BaseException:pass
        browser.close()
    for (eid,kind),payload in captured.items():save(raw/"matches"/eid/(kind+".json"),payload)
    st["browser_capture"]={"captured_match_layers":len(captured),"unique_matches":len({k[0] for k in captured}),"pages_visited":visited,"candidate_pages":len(candidates)};return captured

def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"));root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];raw=root/"raw"/"sofascore";st={"source":"sofascore","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"layers":{},"records":{},"errors":[],"attempted_bases":BASES}
    try:
        tid=str((cfg.get("provider_ids") or {}).get("sofascore") or "");team_name=cfg.get("team") or "";events=[]
        if not tid:raise RuntimeError("SofaScore team id not configured")
        try:
            data,base=get_json(f"/team/{tid}");save(raw/"team.json",data);st["base_used"]=base;st["layers"]["team"]="available";st["records"]["team"]=1;squad,_=get_json(f"/team/{tid}/players");save(raw/"squad.json",squad);st["layers"]["players"]="available";st["records"]["players"]=len(squad.get("players",[]))
        except Exception as e:st["errors"].append({"layer":"direct_team_api","error":str(e)})
        try:
            for page_no in range(40):
                p,_=get_json(f"/team/{tid}/events/last/{page_no}");save(raw/"events"/f"last-{page_no}.json",p);batch=p.get("events",[]);events.extend(batch)
                if not p.get("hasNextPage") or not batch:break
            events=list({str(e.get("id")):e for e in events if e.get("id")}.values());save(raw/"events.json",{"events":events});st["records"]["matches"]=len(events)
        except Exception as e:st["errors"].append({"layer":"matches","error":str(e)})
        counts={k:0 for k in DETAILS}
        for e in events:
            eid=str(e["id"])
            for kind in DETAILS:
                dest=raw/"matches"/eid/(kind+".json")
                if dest.exists():counts[kind]+=1;continue
                try:payload,_=get_json(f"/event/{eid}" if kind=="event" else f"/event/{eid}/{kind}");save(dest,payload);counts[kind]+=1
                except Exception:pass
                time.sleep(.04)
        missing=not events or any(counts[k]<len(events) for k in ("event","statistics","incidents","lineups","shotmap","media"))
        if missing:browser_capture(tid,team_name,events,raw,st)
        for k in counts:counts[k]=sum(1 for e in events if (raw/"matches"/str(e["id"])/(k+".json")).exists())
        st["records"].update(counts);st["layers"]["matches"]="available" if events else "partial";st["layers"]["stats"]="available" if counts["statistics"] else "partial";st["layers"]["events"]="available" if counts["incidents"] else "partial";st["layers"]["spatial"]="available" if counts["shotmap"] else "partial";st["layers"]["lineups"]="available" if counts["lineups"] else "partial";st["layers"]["video"]="available" if counts["media"] else "unavailable";st["status"]="success" if not st["errors"] else "partial"
    except Exception as exc:st["status"]="error";st["errors"].append({"fatal":str(exc)})
    save(root/"source-status-sofascore.json",st)
if __name__=="__main__":main()
