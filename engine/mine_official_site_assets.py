"""Mine machine-readable/runtime assets from already acquired official HTML.

This is acquisition-only: HTML remains the source of truth. The script extracts
script sources, API-like URLs, framework markers and JSON-looking script blocks
without requesting guessed endpoints or inventing business data.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

CONFIG = Path("config/selected-scout.json")
ROOT = Path("data/scouting")


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    root = ROOT / cfg["country"].lower().replace(" ", "-") / cfg["competition"].lower().replace(" ", "-") / cfg["team_id"]
    raw = root / "raw" / "sites"
    assets = []
    seen = set()
    files = 0
    for html_path in sorted(raw.glob("site-*.html")) if raw.exists() else []:
        files += 1
        text = html_path.read_text(encoding="utf-8", errors="ignore")
        meta = None
        links_path = raw / (html_path.stem + ".links.json")
        if links_path.exists():
            try:
                meta = json.loads(links_path.read_text(encoding="utf-8"))
            except Exception:
                meta = None
        base = (meta or {}).get("source_url", "")
        found = set()
        for src in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', text, re.I):
            found.add(urljoin(base, src) if base else src)
        for href in re.findall(r'(?:https?:)?//[^"\'<>\\ ]+', text, re.I):
            found.add(href.replace('\\/', '/'))
        for token in re.findall(r'["\']([^"\']*(?:/api/|/graphql|/ajax/|/rest/|api\.|graphql\.)[^"\']*)["\']', text, re.I):
            found.add(urljoin(base, token) if base else token)
        for token in re.findall(r'(?i)(?:fetch|axios\.(?:get|post)|XMLHttpRequest)[^\n]{0,500}', text):
            for u in re.findall(r'["\']([^"\']+)["\']', token):
                if any(k in u.lower() for k in ("api", "graphql", "ajax", "rest")):
                    found.add(urljoin(base, u) if base else u)
        markers = []
        for marker in ("__NEXT_DATA__", "__NUXT__", "__APOLLO_STATE__", "__INITIAL_STATE__", "application/ld+json", "application/json"):
            if marker.lower() in text.lower():
                markers.append(marker)
        for value in sorted(found):
            if not value or value in seen:
                continue
            seen.add(value)
            assets.append({"source_file": html_path.name, "source_url": base, "asset": value, "kind": "runtime-or-api-reference"})
        if markers:
            assets.append({"source_file": html_path.name, "source_url": base, "kind": "framework-markers", "markers": markers})
    out = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"country": cfg["country"], "competition": cfg["competition"], "team": cfg["team"], "team_id": cfg["team_id"]},
        "method": "observed-from-acquired-html",
        "html_files_scanned": files,
        "assets": assets,
        "asset_count": sum(1 for x in assets if x.get("kind") == "runtime-or-api-reference"),
        "framework_marker_records": sum(1 for x in assets if x.get("kind") == "framework-markers"),
    }
    (raw / "runtime-assets.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "success", "html_files_scanned": files, "asset_count": out["asset_count"], "framework_marker_records": out["framework_marker_records"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
