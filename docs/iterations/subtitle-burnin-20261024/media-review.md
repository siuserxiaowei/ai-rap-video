# C50 复用迭代：显式媒体工具与真实ASS路径验收

日期：2026-10-24；起始基线 `5e5674b`。已读本轮 `PLAN.md`、仓库根 `COORDINATION.md` 和root提供的本地官方FFmpeg转义/ass文档。本轮复用原C50，不更改原任务台账。仅修改两个compositor模块、`tests/engine/test_subtitle_media.py`与本文，未修改其他worker文件。

## 工具与能力检测

`VideoBuilder(config=None, ffmpeg_bin=None, ffprobe_bin=None)`向既有FFmpegPipeline转发两项选择，新增参数放在原参数之后。仅None允许默认发现；显式空白、空值、非字符串、控制字符、非法UTF-8或超过4096 UTF-8字节的引用明确拒绝。非空显式引用保留原字符串及空格，执行失败不会改用PATH。子进程始终使用argv，没有shell层。

滤镜发现同时识别严格三列 `[T.][S.][C.]` 和现有Homebrew构建的旧式两列 `[T.][S.]`，并要求滤镜名称与合法 `A/V/N/| -> A/V/N/|` 媒体链列。`T.. = Timeline support`等legend、错误旗标、缺少媒体链的行不成为滤镜。`-version`失败、`-filters`非零退出、不可执行或超时都不宣称ass可用；本地能力命令加15秒上限。成功解析结果继续缓存。

## ASS filename的两层转义

依据FFmpeg官方[filtergraph说明](https://ffmpeg.org/ffmpeg-filters.html)与[quoting说明](https://ffmpeg.org/ffmpeg-utils.html)，先编码option value的冒号、反斜杠和单引号，再编码filtergraph的反斜杠、单引号及`[] , ;`分隔符；两层都保护空白，避免首尾被移除。`ass=filename=`后使用已编码的未包引号值，不再叠加一层单引号。subprocess argv不增加shell转义层。

本地文档依据为 `/tmp/rap-ffmpeg-filters-20261024.txt` 的4.2节（约1155–1188行）和ass节，以及 `/tmp/rap-ffmpeg-quoting-20261024.txt` 的2.1节。POSIX文件名中的字面反斜杠原样保留，不再替换为正斜杠；空格、apostrophe、冒号、逗号、方括号、分号和中文均经实际文件打开/渲染验证。

## 实跑检查

解释器：`/Users/xiaowei/work/ai-rap-video-20261023/.venv/bin/python`。真实ASS工具由root构建并提供，本模块不会安装、下载或切换全局工具：

```text
AIRAP_TEST_FFMPEG=/Users/xiaowei/work/ai-rap-video-20261023/.workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffmpeg
AIRAP_TEST_FFPROBE=/Users/xiaowei/work/ai-rap-video-20261023/.workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffprobe
```

| 检查 | 实际结果 |
| --- | --- |
| 新unit：`python -m pytest tests/engine/test_subtitle_media.py -k 'not real_ass_burn' -q` | 27 passed, 7 deselected in 0.06s；当时工具链尚在构建，未将真实用例写作通过 |
| 原有媒体与compositor回归 | 69 passed in 1.21s |
| 设置上述两项环境变量后：`python -m pytest tests/engine/test_subtitle_media.py tests/engine/test_media_acceptance.py tests/test_compositor.py -q` | **103 passed in 3.29s，exit code 0，零失败、零跳过**；含27个新unit、7个真实ASS路径用例与69个既有回归 |
| 补充实际解析检查 | 默认FFmpeg的movie filename filter对7类同样特殊路径的程序化MP4往返打开成功；这仅是通用两层解析证据，真实ASS证据以上一行为准 |
| `git diff --check` | 通过 |

7个真实ASS用例涵盖普通路径、空格、单引号、冒号/逗号/方括号/分号、字面反斜杠与中文、全部组合以及文件名首尾空格。每例生成同规格的320×180/24fps程序化off/required视频；ASS事件为0.25–0.75秒的“字幕 TEST”。视频使用无损设置，解码framemd5证明：前6帧和第18帧起与off版一致，中间12帧逐帧不同，总24帧。另验证实际`subtitles_burned=true`、音视频流、实测时长，以及完整音画解码，不以flag或ASS文件存在代替画面差异。

真实用例仅在两项AIRAP_TEST_*都未设置时允许跳过；只设置一项、空值、无效工具或无ass支持均失败，不能悄悄选用PATH。本次最终命令显式提供root工具链，7项全部实际执行，未skip。既有回归继续覆盖原子替换/失败保留旧输出、输入覆盖保护、逐cut trim及双色帧顺序、尺寸/FPS/实测duration。

## 验证边界

本轮没有供应商、网络、浏览器或UI截图操作；所有媒体均为本机合成信号及临时测试文件，没有提交生成媒体。帧差异证明这些路径下有按时出现/消失的ASS像素，不单凭它宣称字体实际解析为所请求family、CJK字形正确或一般排版质量。root负责独立CJK样本画面检查、完整竖/横CLI烟测和最终合并回归、工具链构建/来源收据、同一飞书报告追加回读及worktree回收。

本模块保留程序化预览、无真实AI人声/口型等既有边界；媒体字幕验证不能关闭原C44/C45桌面/390px验收。真实provider质量/费用和原浏览器门槛仍未关闭，整体goal继续不能标完成。
