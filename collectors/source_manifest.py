"""Source acquisition manifest and provenance writer for FOSI."""
import json
from datetime import datetime, timezone
from pathlib import Path

REGISTRY = Path("config/data-sources.json")
OUT = Path("data/source-manifest.json")

def main():
    cfg=json.loads(REGISTRY.read_text(encoding="utf-8"))
    now=datetime.now(timezone.utc).isoformat()
    manifest={"generated_at":now,"strategy":cfg.get("strategy"),"sources":[]}
    for source in cfg.get("sources",[]):
        manifest["sources"].append({"id":source["id"],"priority":source.get("priority"),"enabled":source.get("enabled",False),"layers":source.get("layers",[]),"status":"planned" if source.get("enabled") else "disabled","last_attempt":None,"records":0})
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"FOSI source manifest: {len(manifest['sources'])} providers")
if __name__ == "__main__": main()
