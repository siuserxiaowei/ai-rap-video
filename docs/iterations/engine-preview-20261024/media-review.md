# C50 复用迭代：本地合成输出验收与原子替换

日期：2026-10-24；起始基线 `7c16fe3`。已读本轮 `PLAN.md` 与仓库根 `COORDINATION.md`。本轮继续原 C50，不新增任务数、不修改原 C50 metadata。仅修改 `airap/compositor/video_builder.py`、`tests/engine/test_media_acceptance.py` 和本文；其他 pipeline、CLI、工作台、研究及 provider 模块未改。

## 实际行为

成功不再只意味着非空文件。合成器通过现有 `FFmpegPipeline.probe_file` 包装器调用本地FFprobe，要求至少一个非封面视频流和一个音频流、精确配置的整数宽高、有限正FPS且匹配配置、有限正视频时长。FPS优先采用avg_frame_rate，不可用时采用r_frame_rate；不以容器或音频时长证明视频时长。视频duration不可用时，只允许用该视频流的duration_ts×time_base推得时长。NaN/Infinity/零/负值、错误尺寸/FPS、无视频或无音频均拒绝。

视频时长必须处于请求值的 `max(0.1秒, 2/fps)` 容差内；低FPS因此允许两个视频帧的量化误差。显式请求时长为零、负数、布尔值或非有限数时直接失败，不静默套用timeline默认值。成功的 `RenderResult.duration` 是FFprobe测得的视频时长，`requested_duration`保留原请求，`duration_verified=true`只在探测校验通过后返回。

保留原RenderResult所有必填参数与error_message；新增字段均有兼容默认值：`requested_duration=None`、`duration_verified=False`、`subtitles_burned=False`。旧调用构造结果时不会凭空获得已验证或已烧录状态。原有异常传播行为保留，未将失败转换成假success。

显式提供的有效输入路径必须是可读本地普通文件；音频、镜头clip或ASS缺失时明确报错，仅未提供该媒体时才允许原程序化占位镜头/合成beat。直接路径、symlink和hardlink指向输入的输出覆盖都被拒绝。占位镜头的scratch文件名只使用内部序号，shot标签不能成为路径或把scratch写到目录外。

`burn_subtitles=True`要求存在ASS文件且FFmpeg支持ass滤镜，否则明确错误。自动模式缺少该滤镜时允许省略，但成功结果明确 `subtitles_burned=false`；false模式不会烧录。true标志表示实际构建的滤镜图包含ASS且FFmpeg执行成功，不表示人工确认过文字内容、字体或画面质量。

所有生成素材和候选成片写入目标父目录内新建的临时scratch目录。执行结束后先检查候选文件、完整探测并验证，最后 `os.replace` 原子替换目标；同文件系统保证此替换不需要先删除原目标。FFmpeg失败、缺文件、空文件、探测失败、规格/时长不符或替换失败，都保留已有输出字节并清理scratch。返回命令保留实际执行时的scratch路径，验收后这些临时路径会被删除。

## 实跑证据

解释器：`/Users/xiaowei/work/ai-rap-video-20261023/.venv/bin/python`，Python3.15.0；本机FFmpeg/FFprobe位于 `/opt/homebrew/bin/`。所有素材来自测试临时目录和程序化信号，没有真人、供应商、网络、浏览器或截图操作，没有提交生成媒体。

| 检查 | 实际结果 |
| --- | --- |
| 修改前继承引擎基线：`python -m pytest tests/test_audio.py tests/test_avatar.py tests/test_compositor.py tests/test_lyrics.py tests/test_pipeline.py tests/test_subtitles.py -q` | 154 passed in 2.83s |
| 首轮媒体验收与既有合成器：`python -m pytest tests/engine/test_media_acceptance.py tests/test_compositor.py -q` | 66 passed in 0.89s |
| 新增shot标签路径保护后，相同目标集合复测 | **67 passed in 0.98s，exit code 0，无失败或跳过** |
| `python -m pytest --collect-only -q tests/engine/test_media_acceptance.py` | 本轮46个用例；其余21个为既有compositor用例 |
| `git diff --check` | 通过 |

其中两个用例执行真实FFmpeg：160×90、24fps、请求0.7秒的程序化MP4成功，FFprobe同时报告音频和视频、正确尺寸与FPS、时长在容差内，返回duration与视频流实测值一致；随后用 `ffmpeg -v error -i FILE -f null -` 整文件解码成功。另一用例用真实0.25秒源clip请求1秒输出，最终因测得视频时长不足被拒绝，原有目标字节保持。

其余异常用例注入本地执行/探测桩：畸形或空探测结果、缺流、封面流、错误尺寸/FPS、非有限/非正/过短/过长时长、容器时长误导、视频时基回退、低FPS两帧容差、缺失显式媒体、输入路径/硬链接/符号链接冲突、ASS不支持/自动省略/实际滤镜加入、空或缺输出、执行或原子替换失败均有覆盖。探测阶段另断言旧目标仍存在，证明验收在替换之前进行。

## 边界与交接

本轮验证的是本地程序化合成与文件验收，不是AI人声、人物动画、口型、真人一致性、生成品质或供应商计费。合成器成功路径依据FFprobe接受文件；整文件解码只在真实测试样本执行，不把探测本身描述为每个未来输出都已完整解码或人工观看。

未在本worktree合入其他并行pipeline/CLI变更；主线程负责合并后完整engine/workbench回归、真实CLI和FFprobe/解码烟测、准确能力metadata、同一飞书文档追加与回读，以及接收后回收此干净worktree。真实provider、授权人物质量与桌面/390px浏览器验收仍未关闭，整体goal不因本地MP4可解码而完成。
