# C48 复用：程序化预览流水线复核

2026-10-24。已读取本轮 PLAN 与仓库根 COORDINATION.md。本次只修改 `airap/pipeline.py`、`tests/engine/test_pipeline_contract.py`、本文；不修改原 C48 验收台账、研究、工作台、HTTP 路由或 provider 门禁。

## 输入与写入边界

`RapVideoGenerationRequest`、`RapVideoGenerationResult`、`RapPipelineOrchestrator` 和顶层结果字段保持兼容。请求必须是正确的请求类；歌词为非空、有效 UTF-8、最多 64 KiB 的字符串，按字节计算而非字符数；BPM 必须为有限的 int/float（拒绝 bool），范围含 40 和 300；比例只接受 9:16 或 16:9；输出必须为至多 255 UTF-8 字节的 .mp4 文件 basename，拒绝目录、穿越、Windows 分隔符/驱动器前缀和控制字符。主题仅作有界有效 UTF-8 文本记录，不假定某主题已经应用。

发现并修复默认 BarScheduler 的 16 小节静默截断：明确使用 target_bars=None 保留全部有效歌词。先按小节数和 BPM 计算计划时长，超过 120 秒则在昂贵规划和资产写入前明确拒绝；实际计划时长再次检查有限且不超上限。metadata.lyrics_truncated=false。该资源上限已由 root 协调为本轮合同的一部分。

提供 character_image_path 时明确拒绝，包括空字符串；因为当前没有使用图片的渲染器。只有 audio_path=None 才选择合成纯节拍；空字符串、缺失文件、目录、非路径类型与不可读文件明确报错，绝不替换为节拍。音频必须是可读本地普通文件，输出不能与该音频路径、符号链接解析目标或硬链接指向同一文件。这里只验证本地可读性，媒体可解码性与最终流验证由 C50 合成器负责，不能据文件存在宣称音轨有效。

初始化不再创建输出目录。前置校验失败时不生成资产；只有标题、没有有效歌词小节的输入也不再回退到任意 8 秒内容。每次有效运行在输出目录内创建独立 `preview-assets-*` 子目录存放 beat/ASS，避免固定名文件覆盖用户音频，也避免不同运行覆盖彼此的资产。结果中仍保留可定位的实际音频和字幕路径；不清理仍被结果引用的资产，不提交生成媒体。

## 能力与结果语义

metadata 明确携带：render_kind=procedural_preview、is_generated_ai_video=false、visual_source=procedural_placeholder、audio_source=provided_audio 或 synthetic_beat、vocals_generated=false、lipsync_rendered=false、character_image_used=false。

subtitles_burned、duration_verified、requested_duration 透传合成器 RenderResult。duration_seconds 使用合成器的 duration，而不是用歌词计划时长代替实测时长。为与旧 RenderResult 对象兼容，缺少新属性时仅回退为字幕/时长未验证（false），requested_duration 回退为计划值，不把旧结果升级成已验证结果。字幕文件存在不参与字幕烧录成功判断。

兼容说明：metadata 的 theme 仍保留键但值为 None，补充 requested_theme 与 theme_applied=false，表示实际视觉未使用主题；不再把请求主题写入 style 配置。avatar_frames=0，补充 planned_avatar_states 与 avatar_states_are_planning_data=true。MockLipSyncRenderer 生成的状态仅为规划数据，不传给视频合成器，不能视为渲染了人物或验证了口型。

保持合成器原有 success=false；metadata.error 传递其 error_message 便于 CLI 说明失败。合成器抛出的异常继续向调用方传播，不转成成功，不生成伪造视频路径或虚构实测结果。

## 定向验证

使用指定环境与本 worktree 工作目录：

`/Users/xiaowei/work/ai-rap-video-20261023/.venv/bin/python -m pytest tests/engine/test_pipeline_contract.py -q`

42 项通过。测试使用真实歌词/对齐/规划/ASS 路径，合成器结果受控，合成节拍写入仅为本机虚构 fixture；未将 fixture 当作真实 MP4 验证。

覆盖 17 小节完整保留、120 秒上限的前置拒绝、UTF-8 字节边界、空白/标题歌词、无效 BPM 与比例、输出穿越、图片拒绝、缺失/不可读音频不回退、两种比例、合成/提供音频区分、字幕烧录与实测时长元数据透传、未应用主题/未渲染人物、失败/异常传播、独立资产目录，以及原音频/硬链接输出保护。

没有网络、供应商、付费、浏览器、截图操作；本轮定向测试没有运行 FFmpeg。继承基线、合并回归和实际 CLI/FFprobe/完整解码验证由 root 负责。此处仅验证流水线合同与诚实能力说明，不构成人声、人物动画、口型质量或真实供应商验收。
