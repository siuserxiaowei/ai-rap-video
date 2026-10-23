# Procedural preview CLI review — iteration 20261024

本次复用原 C49，只改本轮拥有的 `airap/cli.py`、`tests/engine/test_cli_contract.py` 与本文。完整阅读本轮 PLAN.md 及仓库根 COORDINATION.md。基线 `7c16fe3`；使用指定解释器 `/Users/xiaowei/work/ai-rap-video-20261023/.venv/bin/python`（Python 3.15.0），工作目录为独立 worktree。

## 行为与接口

首选 `python -m airap.cli preview`，保留 `generate` 为兼容别名。帮助与成功文案都称本地程序化预览，不声称生成 AI 人声、人物动画或真实口型。`main(argv=None)` 返回退出码，模块入口 `raise SystemExit(main())`：成功 0，输入/读取/参数错误 2，失败渲染或非法结果 1。false result.success 不再打印完成消息；初始化、文件读取与运行异常会转为简明错误，避免未处理 traceback。

`--lyrics-file FILE` 明确读取本地普通 UTF-8 文件；与 `--lyrics` 互斥。`--lyrics` 继续接受文字及既有文件路径以兼容旧调用；不存在的路径形状字符串仍按旧语义作为文字。两条路径都限制 64 KiB UTF-8，文件最多读取 65537 字节，不接受目录/设备文件或坏 UTF-8；长文字不会因文件名过长而失效。非空歌词和有限 40–300 BPM 在初始化前验证。显式提供却不存在的 audio 在 CLI 边界直接失败，不可静默替换为合成节拍。

`--output` 仅接受 .mp4 basename；目录由 `--output-dir` 设置并传入 ProjectConfig。拒绝绝对路径、斜杠/反斜杠、错误扩展名与控制字符；输出不能解析为所提供的歌词或音频输入文件。默认目录仍为 ./output，默认 basename 仍为 output_rap.mp4。

`--json` 可放主命令前或 preview/generate 后。正常结果与错误输出为 stdout 上单个 JSON 对象；成功保留 success、output_video_path、duration_seconds、total_bars、bpm、metadata，失败含 success=false 和 error.code/message，渲染明确失败时还保留合法 metadata。help 仍使用 argparse 标准帮助。非法非有限结果或不可序列化 metadata 会失败，避免破损 JSON。

人类输出依据 metadata 的 visual_source/audio_source、vocals_generated、lipsync_rendered、character_image_used、subtitles_burned、duration_verified，缺失字段写 unknown，不从输入参数推断字幕已烧录或已有真实人声。provided_audio 只称来源音频，内容未独立验证；synthetic_beat 明确为无人声的合成器乐。主题显示 requested_theme 与 theme_applied，不能把请求主题称为实际应用。JSON 完整保留约定的 theme=None、requested_theme、theme_applied=false、avatar_frames=0 和 planned_avatar_states 等元数据。若元数据声称不支持的 AI 生成、人声、口型、人物图像或主题应用能力，CLI 拒绝成功。

## 验证

新增 55 个参数化契约用例，使用本地 fake orchestrator / result 验证：preview 与 generate 的请求和配置；元数据驱动来源与字幕事实；缺失标记 unknown；false result 与异常非零；明确和兼容文件读取、精确 UTF-8 字节上限与 bounded read；缺失/目录/坏 UTF-8/空白文件；非有限 BPM；basename/路径与覆盖保护；无声替换禁止；能力矛盾及非法结果；参数错误；实际模块进程 version 与缺文件退出码。

```text
$ /Users/xiaowei/work/ai-rap-video-20261023/.venv/bin/python -m pytest tests/engine/test_cli_contract.py -q
.......................................................                  [100%]
55 passed in 0.15s

$ /Users/xiaowei/work/ai-rap-video-20261023/.venv/bin/python -m pytest tests/test_audio.py tests/test_avatar.py tests/test_compositor.py tests/test_lyrics.py tests/test_pipeline.py tests/test_subtitles.py -q
154 passed in 2.77s
```

下方为完整组合回归的真实原始输出（其中包含既有 workbench 本机 HTTP 契约测试；无外部联网）：

```text
$ /Users/xiaowei/work/ai-rap-video-20261023/.venv/bin/python -m pytest -q
........................................................................ [ 24%]
........................................................................ [ 48%]
.........................................................................................................................................................                               [100%]
297 passed, 393 subtests passed in 11.76s

exit_code=0
```

`git diff --check` 无输出。测试未使用 provider、真实 key、计费、真人素材、浏览器或截图，没有变更原 C49 registry。CLI 专项证明输出/输入/退出契约；本 worktree 的 C48/C50 新实现尚待 root 合并，因此 root 仍须执行组合真实 CLI 预览、最终 FFprobe 与全文件 FFmpeg 解码。本次通过不构成新流水线合成质量、AI 人声、真实口型或浏览器验收。
