#!/usr/bin/env python3
"""Integrate one reviewed research branch, validate records, reclaim clean worktree."""
import argparse, datetime, json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REQUIRED={'id','name','url','category','checked_at','summary','inputs','outputs','features','pricing','api','limitations','best_for','evidence_status','sources','observations'}
def git(*args):
    return subprocess.run(['git',*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
def validate(path):
    record=json.loads(path.read_text())
    missing=REQUIRED-record.keys()
    if missing:raise ValueError(f'{path.name} missing {missing}')
    assert record['evidence_status'] in ('full_page','partial','inaccessible')
    assert record['api']['status'] in ('documented','not_found','unknown')
    assert record['category'] in ('rap','music_video','lip_sync','music','video','editor')
    official=[]
    for source in record['sources']:
        assert source['url'].startswith('https://'),source['url']
        if source.get('local_path'):
            evidence=Path(source['local_path'])
            if not evidence.is_absolute():evidence=ROOT/evidence
            assert evidence.exists(),evidence
            if source['kind'] in ('official','documentation','pricing') and evidence.stat().st_size>700:official.append(evidence)
    if record['evidence_status']=='full_page':assert official,'No substantive primary evidence file'
    return record
def main():
    p=argparse.ArgumentParser();p.add_argument('id');p.add_argument('commit');p.add_argument('agent');a=p.parse_args()
    sid=f'{int(a.id):02}'
    current=ROOT/'research/sites'/f'{sid}.json'
    if not current.exists():print(git('cherry-pick',a.commit))
    raw=json.loads(current.read_text())
    normalized=False
    for source in raw.get('sources',[]):
        if isinstance(source.get('supports'),str):
            source['supports']=[source['supports']]
            normalized=True
    if normalized:current.write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
    record=validate(current)
    try:
        from rap_workbench.catalog import validate_site
    except ModuleNotFoundError:
        validate_site=None
    if validate_site:validate_site(record,ROOT)
    dest=ROOT/'research/codex'/f'C{sid}.json';dest.parent.mkdir(parents=True,exist_ok=True)
    worktree=ROOT.parent/'ai-rap-worktrees'/f'site{sid}'
    removed=not worktree.exists()
    if worktree.exists():
        dirty=subprocess.run(['git','status','--porcelain'],cwd=worktree,check=True,capture_output=True,text=True).stdout
        if not dirty:git('worktree','remove',str(worktree));removed=True
    data={'id':f'C{sid}','agent_task':a.agent,'site_id':sid,'name':record['name'],'original_commit':a.commit,'accepted_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'evidence_status':record['evidence_status'],'record_validated':True,'worktree_reclaimed':removed}
    dest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(data,ensure_ascii=False))
if __name__=='__main__':main()
