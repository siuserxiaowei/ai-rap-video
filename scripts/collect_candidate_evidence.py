#!/usr/bin/env python3
"""Public-site discovery snapshots via the Agent Reach Jina backend."""
import concurrent.futures, datetime, hashlib, json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path.home()/'.agent-reach'/'ai-rap-video-20261023'
OUT.mkdir(parents=True,exist_ok=True)
def collect(s):
    path=OUT/(s['id']+'.txt')
    result=subprocess.run(['curl','-L','--max-time','55','-sS','https://r.jina.ai/'+s['url']],capture_output=True,text=True)
    path.write_text(result.stdout)
    bad=('SecurityCompromiseError','Forbidden','Page not found','404 Not Found','Cloudflare','Please enable JavaScript')
    status='readable' if result.returncode==0 and len(result.stdout)>900 and not any(x in result.stdout[:1200] for x in bad) else 'needs_review'
    meta={**s,'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':status,'returncode':result.returncode,'bytes':len(result.stdout.encode()),'sha256':hashlib.sha256(result.stdout.encode()).hexdigest(),'local_path':str(path),'error':result.stderr[:300]}
    (OUT/(s['id']+'.meta.json')).write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    print(json.dumps({'id':s['id'],'status':status,'bytes':meta['bytes']}),flush=True)
    return meta
if __name__=='__main__':
    sites=json.loads((ROOT/'research/candidates.json').read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(collect,sites))
    (OUT/'index.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
