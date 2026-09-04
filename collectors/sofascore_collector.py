"""FOSI SofaScore acquisition: direct API + browser-network fallback, raw-first."""
import json,time,urllib.parse
from datetime import datetime,timezone
from pathlib import Path

CONFIG=Path("config/selected-scout.json");ROOT_BASE=Path("data/scouting")
BASES=["https://api.sofascore.com/api/v1","https://www.sofascore.app/api/v1","https://www.sofascore.com/api/v1"]

def save(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

def get_json(path):
    last=None
    for base in BASES:
        try:
            import urllib.request
            req=urllib.request.Request(base+path,headers={"User-Agent":"Mozilla/5.0 FOSI/2.0","Accept":"application/json","Referer":"https://www.sofascore.com/"})
            with urllib.request.urlopen(req,timeout=35) as r:return json.load(r),base
        except Exception as e:last=e
    raise last

def browser_capture(tid,raw,st):
    """Use a real Chromium page so SofaScore's own SPA obtains API JSON through its browser session."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        st["errors"].append({"layer":"browser","error":f"Playwright unavailable: {e}"});return []
    captured=[]
    seen=set()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--disable-blink-features=AutomationControlled","--no-sandbox"])
        context=browser.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36",locale="en-US")
        page=context.new_page()
        def on_response(resp):
            url=resp.url
            if "api.sofascore.com/api/v1/" not in url:return
            if resp.request.resource_type not in {"xhr","fetch"}:return
            try:
                ctype=resp.headers.get("content-type","")
                if "json" not in ctype and not url.endswith(".json"):return
                payload=resp.json()
                key=url.split("/api/v1/",1)[-1].split("?",1)[0].strip("/")
                if key in seen:return
                seen.add(key);captured.append((key,payload,url))
            except Exception:pass
        page.on("response",on_response)
        urls=[f"https://www.sofascore.com/football/team/pogon-szczecin/{tid}"]
        # The first page discovers the team's real event links; direct event-page navigation then triggers detail calls.
        try:
            page.goto(urls[0],wait_until="domcontentloaded",timeout=60000);page.wait_for_timeout(7000)
        except Exception as e:st["errors"].append({"layer":"browser_team_page","error":str(e)})
        links=[]
        try:
            links=page.locator('a[href*="/football/match/"]').evaluate_all("els => els.map(e => e.href)")
        except Exception:pass
        # Visit up to 50 unique match pages. Each page causes SofaScore's SPA to request event,
        # statistics, incidents, lineups, graph and shotmap where those layers are public.
        for href in list(dict.fromkeys(links))[:50]:
            try:
                page.goto(href,wait_until="domcontentloaded",timeout=45000);page.wait_for_timeout(1800)
            except Exception:continue
        for key,payload,url in captured:
            safe=key.replace("/","_")
            # Preserve endpoint path and JSON payload exactly enough for later normalization.
            save(raw/"browser"/(safe+".json"),payload)
        browser.close()
    st["browser_capture"]={"captured_endpoints":len(captured),"match_links_visited":min(len(list(dict.fromkeys(links))),50) if 'links' in locals() else 0}
    return captured

def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"));root=ROOT_BASE/cfg["country"].lower().replace(" ","-")/cfg["competition"].lower().replace(" ","-")/cfg["team_id"];raw=root/"raw"/"sofascore"
    st={"source":"sofascore","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"layers":{},"records":{},"errors":[],"attempted_bases":BASES}
    try:
        tid=str((cfg.get("provider_ids") or {}).get("sofascore") or "")
        if not tid:raise RuntimeError("SofaScore team id not configured")
        try:
            data,base=get_json(f"/team/{tid}");save(raw/"team.json",data);st["base_used"]=base;st["layers"]["team"]="available";st["records"]["team"]=1
            squad,_=get_json(f"/team/{tid}/players");save(raw/"squad.json",squad);st["layers"]["players"]="available";st["records"]["players"]=len(squad.get("players",[]))
        except Exception as e:
            st["errors"].append({"layer":"direct_api","error":str(e)})
        events=[]
        try:
            for page_no in range(40):
                p,_=get_json(f"/team/{tid}/events/last/{page_no}");save(raw/"events"/f"last-{page_no}.json",p);batch=p.get("events",[]);events.extend(batch)
                if not p.get("hasNextPage") or not batch:break
            events=list({str(e.get("id")):e for e in events if e.get("id")}.values());save(raw/"events.json",{"events":events});st["records"]["matches"]=len(events)
        except Exception as e:st["errors"].append({"layer":"matches","error":str(e)})
        # Direct detail collection remains preferred when it works.
        counts={"event":0,"statistics":0,"incidents":0,"lineups":0,"graph":0,"shotmap":0}
        for e in events:
            eid=str(e["id"])
            for suffix,key,fn in [("","event","event.json"),("/statistics","statistics","statistics.json"),("/incidents","incidents","incidents.json"),("/lineups","lineups","lineups.json"),("/graph","graph","graph.json"),("/shotmap","shotmap","shotmap.json")]:
                dest=raw/"matches"/eid/fn
                if dest.exists():counts[key]+=1;continue
                try:payload,_=get_json(f"/event/{eid}{suffix}");save(dest,payload);counts[key]+=1
                except Exception:pass
                time.sleep(.04)
        # Protected API fallback: browser capture is attempted whenever useful direct layers are missing.
        missing_detail=not events or counts["statistics"]<len(events) or counts["lineups"]<len(events) or counts["shotmap"]<len(events)
        if missing_detail:
            captured=browser_capture(tid,raw,st)
            for key,payload,url in captured:
                parts=key.split("/")
                if len(parts)>=2 and parts[0]=="event":
                    eid=parts[1];rest="/".join(parts[2:])
                    mapping={"statistics":"statistics.json","incidents":"incidents.json","lineups":"lineups.json","graph":"graph.json","shotmap":"shotmap.json"}
                    if rest in mapping:save(raw/"matches"/eid/mapping[rest],payload);counts[rest]+=1
                    elif rest=="":save(raw/"matches"/eid/"event.json",payload);counts["event"]+=1
        st["records"].update(counts);st["layers"]["matches"]="available" if events else "partial";st["layers"]["stats"]="available" if counts["statistics"] else "partial";st["layers"]["events"]="available" if counts["incidents"] else "partial";st["layers"]["spatial"]="available" if counts["shotmap"] else "partial"
        st["status"]="success" if not st["errors"] else "partial"
    except Exception as exc:st["status"]="error";st["errors"].append({"fatal":str(exc)})
    save(root/"source-status-sofascore.json",st)
if __name__=="__main__":main()
