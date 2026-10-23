#!/usr/bin/env python3
"""Record an already-tested feature commit and reclaim its clean worktree."""
import argparse, datetime, json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('number',type=int);p.add_argument('commit');p.add_argument('agent');p.add_argument('--test-evidence',required=True);p.add_argument('--summary',required=True);p.add_argument('--pending-visual',action='store_true');a=p.parse_args()
assert 41<=a.number<=50
evidence=ROOT/a.test_evidence
assert evidence.exists() and evidence.stat().st_size>0,'Save real verification output before accepting'
assert ROOT in evidence.resolve().parents
def git(*args):return subprocess.run(['git',*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
assert subprocess.run(['git','merge-base','--is-ancestor',a.commit,'HEAD'],cwd=ROOT).returncode==0,'Integrate reviewed commit before accepting'
task=f'feature{a.number}'
worktree=ROOT.parent/'ai-rap-worktrees'/task
removed=not worktree.exists()
if worktree.exists() and not a.pending_visual:
    dirty=subprocess.run(['git','status','--porcelain'],cwd=worktree,check=True,capture_output=True,text=True).stdout
    if not dirty:git('worktree','remove',str(worktree));removed=True
record={'id':f'C{a.number}','agent_task':a.agent,'kind':'research_review_and_feature','original_commit':a.commit,'accepted':not a.pending_visual,'implementation_complete':True,'validation_status':'pending_visual' if a.pending_visual else 'accepted','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'summary':a.summary,'test_evidence':a.test_evidence,'worktree_reclaimed':removed}
dest=ROOT/'research/codex'/f'C{a.number}.json';dest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(record,ensure_ascii=False))
