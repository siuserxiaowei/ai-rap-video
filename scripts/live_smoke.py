#!/usr/bin/env python3
"""Exercise the running local workbench without a browser or supplier calls."""
import argparse,csv,io,json,subprocess,uuid
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--base-url',default='http://127.0.0.1:8788');a=p.parse_args()
assert a.base_url.startswith('http://127.0.0.1:'),'This check only targets the local test service'
def call(path,payload=None,headers=None):
    request=Request(a.base_url+path,data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
    try:response=urlopen(request,timeout=15)
    except HTTPError as error:response=error
    with response:return response.status,dict(response.headers),response.read()
checks=[]
for path in ('/','/create.html','/app.js','/create.js','/styles.css','/create.css'):
    status,_,body=call(path);assert status==200 and body,path;checks.append({'path':path,'status':status,'bytes':len(body)})
status,_,body=call('/api/stats');stats=json.loads(body);assert status==200 and stats['total']==46 and stats['full_page']>=30
brief={'topic':'[验收样例] 团队上线庆祝','mode':'duo','stage':'studio','duration_seconds':12,'aspect_ratio':'9:16','quality':'720p','lyrics':'','language':'zh'}
status,_,body=call('/api/briefs',brief);created=json.loads(body)['brief'];assert status==201
status,_,body=call('/api/briefs/'+created['id']);assert status==200 and json.loads(body)['brief']==created
key='smoke-'+str(uuid.uuid4());payload={'mode':'brief_preview','brief':brief}
status,_,body=call('/api/jobs',payload,{'Idempotency-Key':key});job=json.loads(body)['job'];assert status==201 and job['result']['is_generated_video'] is False
status,_,body=call('/api/jobs',payload,{'Idempotency-Key':key});assert status==200 and json.loads(body)['job']['id']==job['id']
status,_,_=call('/api/jobs',{'mode':'brief_preview','brief':dict(brief,topic='different')},{'Idempotency-Key':key});assert status==409
status,_,_=call('/api/jobs',{'mode':'provider_render','brief':brief});assert status==503
status,_,body=call('/api/quote',{'duration_seconds':12,'quality':'720p','aspect_ratio':'9:16'});quote=json.loads(body)['quote'];assert status==200 and quote['estimate']==3.99 and quote['is_vendor_quote'] is False
status,_,body=call('/api/quote',{'duration_seconds':10,'quality':'720p','aspect_ratio':'9:16'});assert status==200 and json.loads(body)['quote']['estimate'] is None
exports={}
dest=ROOT/'artifacts';dest.mkdir(exist_ok=True)
for fmt,suffix in [('json','json'),('csv','csv'),('markdown','md')]:
    status,headers,body=call('/api/report?format='+fmt);assert status==200 and 'attachment' in headers.get('Content-Disposition','')
    text=body.decode('utf-8-sig')
    if fmt=='json':assert len(json.loads(text)['sites'])==46
    elif fmt=='csv':assert len(list(csv.DictReader(io.StringIO(text))))==46
    else:assert 'https://rapvideogenerator.com/' in text and 'D50' in text
    path=dest/('research-catalog.'+suffix);path.write_bytes(body);exports[fmt]={'bytes':len(body),'path':str(path.relative_to(ROOT))}
js={}
for filename in ('app.js','create.js'):
    result=subprocess.run(['node','--check',str(ROOT/'web'/filename)],capture_output=True,text=True);assert result.returncode==0,result.stderr;js[filename]='passed'
result={'status':'passed','checked_at':datetime.now(timezone.utc).isoformat(),'base_url':a.base_url,'stats':stats,'static_http':checks,'brief_roundtrip':'passed','job_idempotency_and_conflict':'passed','unconfigured_provider_503':'passed','historical_quote_and_no_match':'passed','exports':exports,'javascript_syntax':js,'browser':{'status':'blocked_by_access_policy','desktop':'not_verified','mobile_390':'not_verified','keyboard':'not_verified','reason':'Computer Use session was terminated by the current-page access policy. No alternate browser or tool was used to bypass it.'},'sample_brief_id':created['id']}
(dest/'tests'/'live-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
