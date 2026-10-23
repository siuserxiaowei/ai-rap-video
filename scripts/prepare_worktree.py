#!/usr/bin/env python3
"""Create an isolated task worktree from current main. Never reset existing work."""
import argparse, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('task')
a = p.parse_args()
if not a.task.replace('_', '').isalnum():
    raise SystemExit('task must be alphanumeric with underscores')
dest = ROOT.parent / 'ai-rap-worktrees' / a.task
if not dest.exists():
    subprocess.run(['git','worktree','add','-b',f'research/{a.task}',str(dest),'main'],cwd=ROOT,check=True)
print(json.dumps({'task':a.task,'worktree':str(dest)}))
