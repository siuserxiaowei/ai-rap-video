#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit current evidence, actual task records and explicit remaining gates."""
import datetime, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rap_workbench.catalog import load_sites,stats

sites=load_sites(ROOT);state=stats(sites)
records=[json.loads(p.read_text()) for p in sorted((ROOT/'research/codex').glob('C[0-9][0-9].json'))]
assert len(records)==50 and len({x['agent_task'] for x in records})==50
assert {x['id'] for x in records}=={f'C{i:02}' for i in range(1,51)}
original=[json.loads(p.read_text()) for p in sorted((ROOT/'research/gemini').glob('G[0-9][0-9].json'))]
assert len(original)==50 and len({x['result']['conversation_id'] for x in original})==50
assert all(x['accepted'] and x['returncode']==0 and x['result']['status']=='SUCCESS' for x in original)
supp=json.loads((ROOT/'research/gemini/supplemental-G50.json').read_text())
assert supp['accepted'] and supp['same_conversation']
source_paths=sorted({s['local_path'] for x in sites for s in x['sources']})
manifest=[{'path':p,'bytes':(ROOT/p).stat().st_size,'sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest()} for p in source_paths]
(ROOT/'artifacts/evidence-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
tasks=[]
for x in records:
    tasks.append({'id':x['id'],'task_path':'/root/'+x['agent_task'].removeprefix('/root/'),'commit':x['original_commit'],'delivery':'completed','accepted':bool(x.get('accepted',x.get('record_validated',False))),'validation_status':x.get('validation_status','accepted'),'evidence':x.get('test_evidence') or 'research/sites/'+x['site_id']+'.json'})
    result=subprocess.run(['git','cat-file','-e',x['original_commit']+'^{commit}'],cwd=ROOT,capture_output=True)
    assert result.returncode==0,x['id']
invocations={'actual_invoked':50,'unique_task_paths':50,'method':'collaboration.spawn_agent tasks, batched under 4-active-agent concurrency limit','tasks':tasks}
(ROOT/'research/codex/invocations.json').write_text(json.dumps(invocations,ensure_ascii=False,indent=2)+'\n')
log=(ROOT/'artifacts/tests/c49.txt').read_text()
assert 'Ran 54 tests' in log and '\nOK\n' in log
smoke=json.loads((ROOT/'artifacts/tests/live-smoke.json').read_text())
assert smoke['status']=='passed'
assert all(smoke[k]=='passed' for k in ['brief_roundtrip','job_idempotency_and_conflict','unconfigured_provider_503','historical_quote_and_no_match'])
accepted=sum(bool(x.get('accepted',x.get('record_validated',False))) for x in records)
pending=[x['id'] for x in records if x.get('validation_status')=='pending_visual']
assert accepted==48 and pending==['C44','C45']
verification={
    'status':'partial_browser_blocked',
    'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'git_head':subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip(),
    'research':dict(state,source_references=sum(len(x['sources']) for x in sites),unique_source_files=len(source_paths),source_manifest='artifacts/evidence-manifest.json'),
    'agents':{'codex_invoked':50,'codex_deliveries':50,'codex_fully_accepted':accepted,'codex_pending_visual':pending,'gemini_successful':50,'gemini_unique_conversations':50,'supplemental_same_G50':True},
    'automated_checks':{
        'status':'passed',
        'summary':'54 tests passed, 0 failures/errors/skips; running-service HTTP brief/jobs/quote and all3 downloads passed; both JS syntax checks passed. These are not browser UI checks.',
        'unittest_log':'artifacts/tests/c49.txt','live_smoke_log':'artifacts/tests/live-smoke.json'
    },
    'browser':{
        'status':'blocked_by_access_policy',
        'reason':'浏览器自动化会话因当前页面访问策略被终止。未用其他浏览器或工具绕过；桌面、390px布局、真实键盘焦点和浏览器下载交互尚未验证。',
        'desktop':'not_verified','mobile_390':'not_verified','keyboard':'not_verified','browser_download':'not_verified'
    },
    'runtime':{'url':'http://127.0.0.1:8788','live_render_configured':False,'video_generated':False},
    'goal_complete':False,
    'remaining_required':['C44/C45 real browser desktop/mobile/keyboard/download acceptance']
}
(ROOT/'docs/verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
decisions=json.loads((ROOT/'docs/decisions.json').read_text())
front={1,2,3,18,19,23,25,26,27,28};future={12,34,46,48}
for decision in decisions:
    n=int(decision['id'][1:])
    decision['status']='implemented_pending_browser' if n in front else 'planned_next_stage' if n in future else 'publishing' if n==49 else 'verified'
    decision['verification_ref']='docs/verification.json' if n not in future else 'PLAN.md'
    assert all(any(s['id']==sid for s in sites) for sid in decision['evidence_site_ids'])
assert len(decisions)==50 and len({x['id'] for x in decisions})==50
(ROOT/'docs/decisions.json').write_text(json.dumps(decisions,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'sites':len(sites),'full_page':state['full_page'],'codex':50,'fully_accepted':accepted,'pending_visual':pending,'gemini':50,'unique_evidence_files':len(source_paths),'tests':54},ensure_ascii=False))
