# Iteration 3: verify and correct the existing local composition engine

Planned before implementation, 2026-10-24. The preceding provider-contract iteration is accepted and published in the existing Feishu document, revision11. Original browser gates remain open; no browser or alternative screenshot tool may be used to bypass the access policy. This iteration addresses concrete defects found in existing `airap` code, not a new claim of AI generation.

## Observed defects and intended behavior

`airap/pipeline.py` renders procedural placeholder shots and a synthetic beat by default, computes mock avatar states without rendering them, and silently substitutes a synthetic beat when a supplied audio path is missing. It accepts a character image that it never uses. `airap/cli.py` calls this an AI Rap video success and ignores a false result.success. `VideoBuilder` declares success after checking only a nonempty output, reports requested rather than measured duration, and can silently substitute missing supplied media. These paths were inherited from external engine commits and have not been accepted by the workbench test suite.

The existing local composition flow must describe its actual output, reject unsupported or invalid supplied inputs, and prove that its final file contains the requested playable video/audio streams before reporting success. A local MP4 is a procedural preview, not AI vocals, image animation or measured lip-sync quality. Preserve the source-backed research, workbench routes, provider gates and original task registry.

## Parallel ownership

Reuse the original C48/C49/C50 agents in isolated worktrees; this does not add distinct agents or change their original acceptance records. Keep new tests under tests/engine/ per COORDINATION.md.

| Worker | Worktree | Owned files |
|---|---|---|
| C48 follow-up | engine_preview_pipeline | airap/pipeline.py; tests/engine/test_pipeline_contract.py; docs/iterations/engine-preview-20261024/pipeline-review.md |
| C49 follow-up | engine_preview_cli | airap/cli.py; tests/engine/test_cli_contract.py; docs/iterations/engine-preview-20261024/cli-review.md |
| C50 follow-up | engine_preview_media | airap/compositor/video_builder.py; tests/engine/test_media_acceptance.py; docs/iterations/engine-preview-20261024/media-review.md |
| Root | integration | baseline and combined verification, real CLI/FFprobe smoke, docs and same-document Feishu update |

## Agreed interfaces and limits

Pipeline: retain public request/result class names and return shape. Validate nonempty bounded lyrics (64 KiB UTF-8), finite numeric BPM in40–300, supported aspect9:16/16:9, and a basename .mp4 output filename before writing generated assets. A supplied audio path must be a readable local file; absent audio means synthetic beat. Reject a supplied character image explicitly because no image renderer exists. Metadata must include `render_kind='procedural_preview'`, `is_generated_ai_video=false`, `visual_source='procedural_placeholder'`, `audio_source='provided_audio'|'synthetic_beat'`, `vocals_generated=false`, `lipsync_rendered=false`, `character_image_used=false`, `subtitles_burned` from RenderResult, and `duration_verified` from RenderResult. Any mock avatar states are planning data, never rendered frames. A requested theme may be recorded but must not be claimed as applied when the compositor does not use it.

Media: retain existing RenderResult required fields, add defaults for `requested_duration`, `duration_verified`, `subtitles_burned`. Successful duration must come from probed video duration. Require actual video+audio streams, finite positive duration, configured dimensions/FPS, and video duration within max(0.1 seconds,2/fps) of requested duration. Use the existing local FFprobe wrapper. Explicit missing media is an error; only absent media permits procedural fallback. Explicit subtitle burn without support is an error; auto omission is reported accurately. Render to scratch and atomically replace the target only after verification; a failure must preserve an existing output. Never overwrite an input file. No network or provider calls.

CLI: keep legacy `generate` accepted, describe it as a procedural local preview and provide `preview` as the preferred command. Clarify source audio, synthetic beats, missing AI vocals/lip-sync, and subtitle burn status using returned metadata. Check result.success and exit nonzero on failure; catch input/read/initialization failures without an unhandled traceback. Support explicit `--lyrics-file` alongside existing `--lyrics`, bounded reads, output basename plus `--output-dir`, and optional machine-readable `--json` for the real CLI smoke. Never print a successful AI-generation message for this local engine. No new HTTP route or provider submit command.

## Acceptance and finish

Run the inherited engine tests in the existing Python3.15 .venv, then targeted meaningful tests for each defect and combined engine/workbench regression. Root must run real local CLI previews using only synthetic lyrics/audio, inspect final files with FFprobe and full FFmpeg decode, and compare measured streams, durations and explicit capability flags. This verifies composition correctness, not human audiovisual quality or real provider behavior. Retain logs and manifests; do not commit generated media. Accept then immediately reclaim each clean follow-up worktree. Update current docs and append one truthful progress section to the same Feishu document, preserving its prior content. Real provider generation, billing, authorized-person quality and original browser acceptance remain open.
