# Shared workspace coordination

The Codex root agent is integrating audited website records under `research/`, running 50 independent Gemini sessions via `scripts/run_gemini_research.py`, and preparing the native Feishu report. It owns `research/`, `scripts/`, `web/`, `rap_workbench/`, `docs/`, and Feishu publication.

An external development process added `airap/`, `README.md`, `pyproject.toml`, and `AI_RAP_VIDEO_RESEARCH.md` at commit fccf3d4. These are preserved. Please keep any further engine work under `airap/` and `tests/engine/` in isolated worktrees; do not overwrite research contracts, scripts, data, workbench modules, or Git ignore safety entries. Do not commit all files with `git add .`; stage only your assigned paths. Avoid creating duplicate remote Feishu reports.

`AI_RAP_VIDEO_RESEARCH.md` is an external draft and is not evidence of having researched 42 sites or tested capabilities. Only validated `research/sites/*.json` and their local sources count toward the website gate. Shared snapshots under `~/.agent-reach/ai-rap-video-20261023/` are public source material.

All official website statements remain vendor claims until independently tested. Do not describe the app as industrial or production ready without full-flow evidence. Never commit secrets, `.env*`, generated user media, or private account data.
