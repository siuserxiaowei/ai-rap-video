# Iteration 4: verify real ASS subtitle burn-in

Planned before implementation, 2026-10-24. Previous engine iteration is accepted at bebaf44,387 tests and actual local media checks, and the same Feishu report is verified at revision12. It explicitly left burn-in unverified because the installed FFmpeg8.1.1 has no ass/subtitles filters. Prior browser access policy remains binding; no browser, UI screenshot or alternative UI tool may be used to bypass it. Inspecting frames from synthetic video tests verifies media captions only and cannot close C44/C45.

## Concrete result

Provide explicit local FFmpeg/FFprobe selection and subtitle auto/required/off modes through the existing CLI and pipeline. Support a requested subtitle font family. Required mode must fail clearly if the selected binary cannot burn ASS; off must leave the video untouched by captions. Verify real text appearing/disappearing in actual output frames, not just an ASS file or success flag. Preserve all honest procedural-preview and no-real-AI boundaries.

Local discovery: all existing ffmpeg aliases resolve to /opt/homebrew/Cellar/ffmpeg/8.1.1/bin/ffmpeg, with neither ass nor subtitles. System Arial Unicode MS font is installed. Official Homebrew ffmpeg-full is keg-only9.0.2 but a dry-run requests42 new and22 upgraded dependencies. Root will instead build libass0.17.5 and FFmpeg8.1.1 in the project's ignored .workbench/toolchains directory, using existing libraries plus only needed build prerequisites after inspecting their dry-run. No force-link, global FFmpeg switch, third-party tap trust or provider credentials are needed. Verify upstream archive SHA-256 from official release/formula metadata before extraction/build. Source URLs, hashes, exact build steps and runtime capability evidence must be retained; binaries/fonts/media are not committed.

## Parallel ownership

Reuse the original C48/C49/C50 handles in isolated worktrees; no additional distinct agents and no original acceptance-record changes.

| Worker | Worktree | Owned files |
|---|---|---|
| C48 | subtitle_pipeline | airap/config.py; airap/pipeline.py; tests/engine/test_subtitle_pipeline.py; existing tests/engine/test_pipeline_contract.py only if fixture compatibility requires it; docs/iterations/subtitle-burnin-20261024/pipeline-review.md |
| C49 | subtitle_cli | airap/cli.py; tests/engine/test_subtitle_cli.py; docs/iterations/subtitle-burnin-20261024/cli-review.md |
| C50 | subtitle_media | airap/compositor/ffmpeg_pipeline.py; airap/compositor/video_builder.py; tests/engine/test_subtitle_media.py; docs/iterations/subtitle-burnin-20261024/media-review.md |
| Root | integration | source/toolchain build and receipt; real caption pixel/CLI/decode verification script; docs and same-document Feishu publication |

## Shared contract

ProjectConfig appends `ffmpeg_path: Optional[str]=None`, `ffprobe_path: Optional[str]=None`, `subtitle_mode: str='auto'`. Existing VideoConfig and StyleConfig defaults remain compatible. `--ffmpeg` and `--ffprobe` select these paths explicitly; app code must not download/install tools or silently replace an explicitly invalid binary with PATH. The default remains existing discovery. VideoBuilder adds optional `ffprobe_bin=None` after existing args and passes it to FFmpegPipeline; pipeline supplies configured paths without changing default legacy call behavior.

CLI adds `--subtitle-mode auto|required|off` (default auto), `--subtitle-font FONT` (optional, applied to config.style.font_name), `--ffmpeg FILE` and `--ffprobe FILE`. Mode maps to build_video burn_subtitles None/True/False. Required mode preflights ass support on the selected binary before generated assets; actual `subtitles_burned` still comes from RenderResult, never preflight alone. Validate requested mode, nonempty bounded valid UTF-8 executable references (None means default; empty explicit paths are invalid), and font family (nonempty bounded UTF-8; no comma/control characters that would corrupt ASS styles). Metadata includes `subtitle_mode` and `subtitle_font_requested`; it must not claim the requested font was actually resolved merely from the name. Keep main(argv)->int and single --json result semantics.

FFmpeg filter discovery must recognize actual three-column capability flags, respect a nonzero -filters exit and avoid false positives from headers. Resolve/escape ASS paths according to the two parsing layers in FFmpeg's official filtergraph docs; subprocess argv has no shell parsing layer. Preserve literal POSIX backslashes and correctly handle apostrophes, spaces, colons, commas/brackets and Chinese characters. Add real burn-in cases with those path characters, not command-string tests alone. Existing explicit-missing-media, atomic output replacement, per-cut trimming and accurate duration/FPS behavior must remain intact.

## Acceptance

Targeted tests cover configuration forwarding, modes, explicit invalid tools, CLI flags/errors and font validation, filter capability parsing, and real ASS rendering/path handling. Root supplies test-only AIRAP_TEST_FFMPEG/AIRAP_TEST_FFPROBE paths to the built toolchain for optional actual ASS tests; final combined regression must execute them without skips. No live provider, paid generation, real-person assets or browser operations.

Root must render identical synthetic source clips with subtitle off/required, compare decoded frame pixels before/during/after a timed Chinese caption, inspect the actual Chinese caption media frame, and fully decode outputs. Root also exercises both full-HD aspect ratios through actual CLI with explicit toolchain/font and required mode; verifies measured streams/durations and actual subtitles_burned=true. A controlled unsupported-tool case must fail without changing an existing output. Retain local synthetic media/frame artifacts for review outside Git if useful, with hashes and exact commands recorded. Numeric caption differences and image inspection establish only these sample captions, not general typography, Chinese vocals, lip-sync, or browser UI quality.

After review and appropriate tests, accept and immediately reclaim each clean follow-up worktree. Reconcile current docs, append one truthful update to the existing Feishu document, and read back to prove prior46 site headings,50 decision rows and source links are preserved. Original C44/C45 and real-provider quality/cost gates remain open; overall completion remains unproven.

## Execution result

Scope accepted, 2026-10-24. Upstream SHA-verified FFmpeg8.1.1/libass0.17.5 were built locally; two small prerequisites were installed without upgrading existing libraries, and the default FFmpeg path/hash stayed unchanged. All three follow-ups were reviewed, merged, independently retested and their worktrees reclaimed. Final529 tests passed with393 subtests and zero skips, including all seven real ASS path cases. Four actual full-HD CLI outputs covered required/auto/off, with full audio/video decode; unsupported required preflight preserved old output and created no assets.

Controlled caption frame differences were0/2996/0 pixels at0.1/0.5/0.9 seconds for a0.25–0.75s event. Root visually inspected three decoded frames and could read all six Chinese characters. This establishes only these caption samples, not font-face identification, general typography, real vocals/lip-sync or browser UI. The same Feishu document reached revision14 after one section append and its image upload; full text exactly matched the candidate, prior46 site headings/50 decision rows/161 links were preserved, and the native image fetched back with its original SHA-256. The remaining external gates and blocked audit are recorded separately; overall goal is not complete.
