# C48 复用：字幕模式与工具链流水线合同

2026-10-24。已读取本轮 PLAN 与仓库根 COORDINATION.md，仅修改本轮拥有的 config、pipeline、新专项测试和本文。未改原 C48 台账，也没有修改旧流水线测试 fixtures。

## 配置与兼容

ProjectConfig 在既有字段末尾追加 ffmpeg_path=None、ffprobe_path=None、subtitle_mode='auto'。既有位置参数、VideoConfig 与 StyleConfig 默认值保持兼容。

工具引用为非空有效 UTF-8 字符串，最多 4096 字节，不允许 Unicode 控制/格式字符。包含 `/` 的显式本地 FILE 必须解析为可执行普通文件；裸命令名只按它自身的 PATH 条目查找，不抢先使用当前目录同名文件，不替换为 ffmpeg/ffprobe 默认工具。需要选当前目录的工具时必须显式写 `./工具名`，与 CLI 采用相同选择规则。校验后的显式工具固定为解析路径，用于同一次预检和合成；空字符串、缺失文件、目录、无执行权限文件均在资产写入前失败，不回退到其他工具。

字体族必须是非空有效 UTF-8 文本，最多 256 字节，不含逗号或控制/格式字符，防止破坏 ASS style 列。中文和空格可用；保留原始名字并写入配置后的 ASS，校验默认字体与显式字体。该校验不查询字体库，不证明字体已安装或实际被 libass 采用。

subtitle_mode 仅接受 auto|required|off。默认构造仍只调用 VideoBuilder(config=...)；只有显式指定的工具才分别传入 ffmpeg_bin/ffprobe_bin，不干扰另一工具的默认发现。auto 不额外添加 burn_subtitles 参数，保留旧 fakebuilder 和真实 build_video 的默认调用；required 显式传 True，off 显式传 False。

## 前置检查与元数据

在生成 beat、ASS、输出目录或 per-run 资产目录之前，required 模式使用实际选定 builder.pipeline.has_filter('ass') 检查能力。不支持 ASS 或查询异常会明确失败；预检失败不改变已有输出。不会仅凭 PATH 中别的 FFmpeg 支持 ASS 就放行所选工具。

在 Python 流水线返回边界再次核对渲染结果：renderer.success 为真时，required 的 subtitles_burned 必须严格为 True（False、None、1、字符串及缺字段均不能替代）；off 若报告 subtitles_burned=True 则明确抛错。auto 继续诚实透传实际标记。renderer.success=False 保持失败，不把预检通过升级为成功。这一检查覆盖直接调用 pipeline 的使用者，不依赖 CLI 再次拒绝。对注入异常 renderer 已经写入文件的情况不声称回滚；真实输出原子替换仍由 C50 合成器负责。

metadata 新增 subtitle_mode 和 subtitle_font_requested。subtitles_burned 仍完全取自 RenderResult：预检通过、ASS 文件存在和字体请求名称都不能替代实际烧录结果。没有新增 font_resolved、font_used 或字体解析成功宣称。原有 procedural_preview、AI/人声/口型/人物图片 false、未应用主题、未截断歌词、规划 avatar、实测时长和失败语义全部保留。

## 本机定向验证

使用指定 Python 3.15 环境、工作目录为本 worktree：

`/Users/xiaowei/work/ai-rap-video-20261023/.venv/bin/python -m pytest tests/engine/test_subtitle_pipeline.py tests/engine/test_pipeline_contract.py -q`

98 项通过：56 项字幕流水线合同测试，加原 42 项流水线合同回归。测试覆盖新配置默认/位置参数兼容、三模式映射、默认调用兼容、所选双工具/单工具及裸引用解析、CWD 同名 shadow 不覆盖 PATH、显式 ./ 选择本地工具、无效引用不回退、不可执行文件与目录、默认及请求字体校验、中文 ASS 字体字段、required 预检失败前零资产写入与旧输出保护，以及 required/off 与 renderer 实际烧录状态矛盾时拒绝成功、required 严格布尔检查、缺标记拒绝、auto 透传和原失败状态保留。

这些测试使用受控 builder、虚构 beat fixture 和本机可执行文件哨兵；未实际执行这些工具。没有网络、供应商、付费、浏览器或截图操作。实际 ASS 烧录、精确工具链、帧像素/中文字形检查、全解码及联合回归由 root 与 C50 完成，本复核不将配置或 mock 成功当作真实字幕或字体解析验收。
