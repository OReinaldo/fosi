"""Build a run manifest for every configured source without coupling analytics to acquisition."""
import json
from datetime import datetime, timezone
from pathlib import Path

REGISTRY=Path('config/data-sources.json')
OUT=Path('data/acquisition-manifest.json')

def main():
    cfg=json.loads(REGISTRY.read_text(encoding='utf-8'))
    now=datetime.now(timezone.utc).isoformat()
    sources=[]
    for s in cfg.get('sources',[]):
        sources.append({'source':s['id'],'enabled':bool(s.get('enabled')),'priority':s.get('priority',999),'requested_layers':s.get('layers',[]),'attempted_at':now if s.get('enabled') else None,'status':'pending_adapter' if s.get('enabled') else 'disabled','records':0,'raw_files':0,'errors':[]})
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({'schema_version':'1.0','generated_at':now,'sources':sources},ensure_ascii=False,indent=2),encoding='utf-8')
    print('FOSI acquisition manifest written:',len(sources),'sources')
if __name__=='__main__': main()
