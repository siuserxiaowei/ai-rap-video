# Subtitle CLI review — iteration 20261024

本轮复用原 C49，未修改原登记。完整阅读本轮 PLAN.md 与仓库根 COORDINATION.md。工作树基线 `5e5674b`；使用指定既有 Python 3.15.0 虚拟环境，未下载/安装或执行外部服务。

## CLI 变更

preview 和兼容 generate 增加 `--ffmpeg`、`--ffprobe`、`--subtitle-mode auto|required|off`、`--subtitle-font`。先按原接口构造 ProjectConfig(output_dir=...)，再设置 ffmpeg_path / ffprobe_path / subtitle_mode；显式字体写 config.style.font_name，兼容本工作树尚未合入 C48 新 dataclass 字段的情况。省略工具仍传 None、模式默认 auto、字体仍保留既有 Arial Black，原有 JSON、退出码和程序化预览边界保持。

工具引用必须非空、非纯空白、有效 UTF-8、最多 4096 字节，不能有控制/格式控制或行分隔字符。显式路径必须是可执行普通本地文件；bare 名称只查找其自身在 PATH 中的命令。传给配置的字符串保留原样，包括空格、中文、引号、冒号、逗号和 POSIX 反斜杠。不更换名称、不回退 PATH 工具、不下载。此处只验证可执行引用；真正的 FFmpeg/FFprobe 运行能力与 ASS preflight 由 pipeline/media 层验证。

字体请求必须是非空、有效 UTF-8、最多 256 字节的单个 family，拒绝逗号及控制/格式控制或行分隔字符；合法原始名字保留，不能把 256 个字符误当作 256 字节。没有从字体名字推断安装、匹配或实际解析成功。

人类输出新增 metadata 中的 subtitle_mode / subtitle_font_requested，并继续独立显示 RenderResult 派生的 subtitles_burned；字体旁注明 `font resolution not verified`。缺失元数据仍标 unknown，JSON 原样保留约定字段，不自行增加 resolved-font 结论。成功结果若要求 required 却未确认 burned=true、off 却未确认 burned=false，或 metadata mode 回退到其他模式，均返回 INVALID_RESULT 非零；明确的 renderer failure 保留 PREVIEW_FAILED，不会被上述成功校验覆盖。无效参数/引用/字体均在初始化前以 INVALID_INPUT 非零结束，JSON 为单个有效对象。

## 验证

新增 52 项字幕 CLI 参数化测试，使用明确的 fake orchestrator/result 与本地临时 dummy executable：两种命令、精确路径转发、三种 mode、默认兼容、bare-name 精确查找、空/过长/控制/非法 UTF-8 引用、缺失/目录/不可执行工具无回退、字体 UTF-8 字节边界与 ASS family 约束、请求字体不等于 resolved font、auto 的真实返回 burn 标记、required/off 矛盾与模式回退拒绝、unsupported ASS 错误与 false result、实际模块进程的非法工具退出码。

```text
$ /Users/xiaowei/work/ai-rap-video-20261023/.venv/bin/python -m pytest tests/engine/test_subtitle_cli.py tests/engine/test_cli_contract.py -q
........................................................................ [ 67%]
...................................                                      [100%]
107 passed in 0.24s
```

本工作树完整回归包括原有 387 项与新增 52 项，0 failures / errors / skips；`git diff --check` 无输出。真实日志如下：

```text
$ /Users/xiaowei/work/ai-rap-video-20261023/.venv/bin/python -m pytest -q
........................................................................ [ 16%]
........................................................................ [ 32%]
........................................................................ [ 49%]
........................................................................ [ 65%]
.................................................................................................................................. [ 95%]
.....................                                 [100%]
439 passed, 393 subtests passed in 12.19s

exit_code=0
```

## 验收边界

本工作树没有合入并验收 C48/C50 本轮新实现；以上证明 CLI 输入、配置转发、元数据呈现和失败语义，不证明 ASS 烧录或所请求字体真正被解析。root 仍须用项目本地 ASS-enabled FFmpeg/FFprobe 合并验证 required/off、字幕前中后帧像素、实际中文帧、两种 full-HD CLI、FFprobe 与完整解码，以及不支持工具时保留已有输出。

未进行外部联网、provider、付费调用、真人素材、浏览器或截图；未声明 AI 人声、原音创作、人物动画、口型或浏览器 UI 验收。媒体帧检查也不能关闭原 C44/C45 门槛。
