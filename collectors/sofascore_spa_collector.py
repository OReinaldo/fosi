"""Dedicated SofaScore web-app capture fallback.

Used when the public API returns 403. It first discovers match URLs from the
public server-rendered team page using curl_cffi, then uses real Chrome to
visit those match pages and capture the site's own JSON. RAW payloads are
preserved; no values are invented.
"""
import json,re,unicodedata,time
from datetime import datetime,timezone
from pathlib import Path

CONFIG=Path("config/selected-scout.json")
ROOT=Path("data/scouting")
DETAILS={"event","statistics","incidents","lineups","graph","shotmap","media"}


def save(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    if isinstance(payload,(bytes,bytearray)):
        path.write_bytes(payload)
    else:
        path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")


def slugify(value):
    s=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode().lower()
    s=s.replace("&","and")
    return re.sub(r"[^a-z0-9]+","-",s).strip("-")


def extract_match_urls(text):
    """Extract absolute/relative SofaScore football match URLs from SSR HTML/JSON."""
    if not text:
        return []
    patterns=(
        r'https?://www\\.sofascore\\.com/(?:[a-z]{2}/)?football/match/[^"\\'<>\\s\\\\]+' ,
        r'/(?:[a-z]{2}/)?football/match/[^"\\'<>\\s\\\\]+'
    )
    found=[]
    for pattern in patterns:
        found.extend(re.findall(pattern,text,flags=re.I))
    # HTML/JSON may contain escaped slashes or unicode escapes.
    normalized=[]
    for value in found:
        value=value.replace('\\\\/','/')
        if value.startswith('/'):
            value='https://www.sofascore.com'+value
        value=value.rstrip('\\.,);]')
        if '/football/match/' in value:
            normalized.append(value)
    return list(dict.fromkeys(normalized))


def discover_ssr(team_url):
    """Use a browser-like HTTP client before Playwright; the team page is SSR accessible."""
    try:
        from curl_cffi import requests
        session=requests.Session(impersonate="chrome")
        response=session.get(
            team_url,
            headers={
                "Accept":"text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language":"en-US,en;q=0.9",
                "Referer":"https://www.google.com/"
            },
            timeout=30,
        )
        if response.status_code >= 400:
            return [], {"status_code":response.status_code,"bytes":len(response.content)}
        return extract_match_urls(response.text), {"status_code":response.status_code,"bytes":len(response.content)}
    except Exception as exc:
        return [], {"error":str(exc)}


def main():
    cfg=json.loads(CONFIG.read_text(encoding="utf-8"))
    country=cfg["country"].lower().replace(" ","-")
    competition=cfg["competition"].lower().replace(" ","-")
    team_id=cfg["team_id"]
    root=ROOT/country/competition/team_id
    raw=root/"raw"/"sofascore"
    status={"source":"sofascore-spa","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"records":{},"errors":[]}
    tid=str((cfg.get("provider_ids") or {}).get("sofascore") or "")
    if not tid:
        status["status"]="error";status["errors"].append({"error":"missing SofaScore team id"});save(root/"source-status-sofascore-spa.json",status);return
    team_url=f"https://www.sofascore.com/football/team/{slugify(cfg.get('team'))}/{tid}"

    # First route: public SSR HTML. This avoids relying on the SPA DOM, which
    # can be empty in GitHub-hosted Chromium even though the public page is
    # available to normal HTTP clients and search crawlers.
    ssr_candidates,ssr_meta=discover_ssr(team_url)
    status["ssr_discovery"]={"team_url":team_url,"candidate_pages":len(ssr_candidates),**ssr_meta}

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        status["status"]="error";status["errors"].append({"error":f"Playwright unavailable: {exc}"});save(root/"source-status-sofascore-spa.json",status);return

    captured={};visited=0
    with sync_playwright() as p:
        try:
            browser=p.chromium.launch(channel="chrome",headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
        except Exception:
            browser=p.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
        context=browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36",
            locale="en-US",viewport={"width":1440,"height":1200}
        )
        page=context.new_page();page.set_default_timeout(7000)

        def on_response(resp):
            if "api.sofascore.com/api/v1/" not in resp.url or resp.request.resource_type not in {"xhr","fetch"}:
                return
            try:
                key=resp.url.split("/api/v1/",1)[1].split("?",1)[0].strip("/")
                parts=key.split("/")
                if len(parts)<2 or parts[0]!="event": return
                eid=parts[1]
                if len(parts)==2: asset="event"
                elif len(parts)>=4 and parts[2]=="player": asset="player/"+parts[3]+("/"+parts[4] if len(parts)>4 else "")
                else: asset=parts[2]
                if asset not in DETAILS and not asset.startswith("player/"): return
                captured[(eid,asset)]=resp.json()
            except Exception:
                pass
        page.on("response",on_response)

        try:
            # Only use SPA discovery as a secondary route. The SSR route above
            # is authoritative for candidate URL discovery when available.
            candidates=list(ssr_candidates)
            if not candidates:
                try:
                    page.goto(team_url,wait_until="domcontentloaded",timeout=60000)
                    page.wait_for_timeout(7000)
                    for label in ("Matches","Partidos","Resultados"):
                        try:
                            loc=page.get_by_text(label,exact=True)
                            if loc.count():
                                loc.first.click(timeout=3000);page.wait_for_timeout(1500);break
                        except Exception:
                            pass
                    for _ in range(16):
                        page.evaluate("window.scrollBy(0, Math.max(900, window.innerHeight))")
                        page.wait_for_timeout(450)
                    hrefs=[]
                    try:
                        hrefs=page.locator('a[href*="/football/match/"]').evaluate_all("els => els.map(e => e.href)")
                    except Exception:
                        pass
                    try:
                        hrefs += extract_match_urls(page.content())
                    except Exception:
                        pass
                    candidates=list(dict.fromkeys(hrefs))
                except Exception as exc:
                    status["errors"].append({"layer":"spa_discovery","error":str(exc)})

            status["discovery"]={"team_url":team_url,"candidate_pages":len(candidates),"source":"ssr" if ssr_candidates else "spa"}
            for href in candidates:
                try:
                    page.goto(href,wait_until="domcontentloaded",timeout=50000)
                    page.wait_for_timeout(2600)
                    for labels in (("Statistics","Estadísticas","Stats"),("Lineups","Alineaciones"),("Media","Videos","Vídeos")):
                        for label in labels:
                            try:
                                loc=page.get_by_text(label,exact=True)
                                if loc.count():
                                    loc.first.click(timeout=2500);page.wait_for_timeout(1200);break
                            except Exception:
                                pass
                    for _ in range(8):
                        page.evaluate("window.scrollBy(0, Math.max(700, window.innerHeight*.85))")
                        page.wait_for_timeout(350)
                    visited+=1
                except Exception as exc:
                    status["errors"].append({"url":href,"error":str(exc)})

            for (eid,asset),payload in captured.items():
                if asset.startswith("player/"):
                    parts=asset.split("/")
                    save(raw/"matches"/eid/"players"/parts[1]/((parts[2] if len(parts)>2 else "data")+".json"),payload)
                else:
                    save(raw/"matches"/eid/(asset+".json"),payload)
        finally:
            browser.close()

    status["browser_capture"]={"pages_visited":visited,"captured_layers":len(captured),"unique_matches":len({k[0] for k in captured})}
    status["records"]={k:sum(1 for eid in {x[0] for x in captured} if (raw/"matches"/eid/(k+".json")).exists()) for k in DETAILS}
    status["status"]="success" if captured else "partial"
    save(root/"source-status-sofascore-spa.json",status)


if __name__=="__main__": main()
