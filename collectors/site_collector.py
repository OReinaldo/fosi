"""Acquire official competition/club pages and preserve structured public data.

HTML remains the evidence source. In addition to embedded JSON, the collector now
extracts ordinary HTML tables (standings/statistics/schedules) into a small,
lossless-ish row representation so the official Ekstraklasa pages are useful even
when the application does not expose hydration JSON.
"""
import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

CONFIG = Path("config/selected-scout.json")
ROOT_BASE = Path("data/scouting")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 FOSI/2.2", "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en,pl;q=0.9"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def layer_for(url):
    u = url.lower()
    if any(x in u for x in ("tabela", "standings")): return "standings"
    if any(x in u for x in ("statystyki", "statistics", "?ranking=")): return "stats"
    if any(x in u for x in ("schedule", "terminarz", "kolejka", "round")): return "fixtures"
    if "clubs/" in u and "player/" not in u: return "club"
    if "news" in u or "aktualnosci" in u: return "news"
    return "context"


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def embedded_json(body):
    text = body.decode("utf-8", "ignore")
    out = []
    patterns = [r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>']
    for pattern in patterns:
        for raw in re.findall(pattern, text, re.I | re.S):
            raw = html.unescape(raw).strip()
            try: out.append(json.loads(raw))
            except Exception: pass
    return out


def extract_tables(body):
    """Extract visible HTML tables without inventing field names."""
    text = body.decode("utf-8", "ignore")
    tables = []
    for table_html in re.findall(r"<table\b[^>]*>(.*?)</table>", text, re.I | re.S):
        rows = []
        for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table_html, re.I | re.S):
            cells = re.findall(r"<(?:th|td)\b[^>]*>(.*?)</(?:th|td)>", tr, re.I | re.S)
            values = [clean_text(c) for c in cells]
            if values: rows.append(values)
        if rows: tables.append({"rows": rows, "row_count": len(rows), "column_count": max(map(len, rows))})
    return tables


def extract_links(body, base_url):
    text = body.decode("utf-8", "ignore")
    links = []
    for href in re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', text, re.I):
        if href.startswith("/"): href = urljoin(base_url, href)
        if href.startswith("http") and href not in links: links.append(href)
    return links[:5000]


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    root = ROOT_BASE / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    raw = root / "raw" / "sites"; raw.mkdir(parents=True, exist_ok=True)
    urls = cfg.get("public_site_urls", [])
    st = {"source":"official-sites","status":"collecting","retrieved_at":datetime.now(timezone.utc).isoformat(),"layers":{},"records":{},"errors":[],"structured_records":0,"structured_tables":0,"structured_rows":0,"links":0}
    for i, url in enumerate(urls):
        layer = layer_for(url)
        try:
            body = fetch(url); (raw / f"site-{i}.html").write_bytes(body)
            emb = embedded_json(body); tables = extract_tables(body); links = extract_links(body, url)
            if emb: (raw / f"site-{i}.embedded.json").write_text(json.dumps({"source_url":url,"layer":layer,"records":emb},ensure_ascii=False,indent=2),encoding="utf-8")
            if tables: (raw / f"site-{i}.tables.json").write_text(json.dumps({"source_url":url,"layer":layer,"tables":tables},ensure_ascii=False,indent=2),encoding="utf-8")
            if links: (raw / f"site-{i}.links.json").write_text(json.dumps({"source_url":url,"links":links},ensure_ascii=False,indent=2),encoding="utf-8")
            row_count = sum(t["row_count"] for t in tables)
            st["records"][url] = {"bytes":len(body),"layer":layer,"embedded_json_records":len(emb),"html_tables":len(tables),"html_table_rows":row_count,"links":len(links)}
            st["structured_records"] += len(emb); st["structured_tables"] += len(tables); st["structured_rows"] += row_count; st["links"] += len(links); st["layers"][layer] = "available"
        except Exception as e: st["errors"].append({"url":url,"layer":layer,"error":str(e)})
    st["status"] = "success" if urls and not st["errors"] else "partial" if st["records"] else "error" if urls else "not_configured"
    (root / "source-status-official-sites.json").write_text(json.dumps(st,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":st["status"],"pages":len(st["records"]),"embedded_records":st["structured_records"],"html_tables":st["structured_tables"],"html_rows":st["structured_rows"]},ensure_ascii=False))


if __name__ == "__main__": main()
