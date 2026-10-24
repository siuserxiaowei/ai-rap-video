# 发布范围复核：公开 GitHub 与本地 46 站 / 529 项快照

核验时间（UTC）：2026-10-24T03:25:23.932834+00:00。只读核验；未推送、改 remote、发帖、创建 PR、改代码/任务登记/目标状态，未使用浏览器。本次未重新运行旧 162 或新 529 项，而是核对 Git 对象、公开 API、已归档原始日志及哈希。使用已读取的 agent-reach SKILL.md / references/dev.md 所指定 GitHub gh CLI 后端。gh 2.96.0 可用；agent-reach 更新检查命令不在 PATH，限定位置亦未找到可执行文件，未安装或更新工具。

## 可直接用于合并稿的版本表

| 来源 / 版本 | 范围与可证事实 | 测试证据等级 | 合并稿应如何标注 |
| --- | --- | --- | --- |
| 旧总纲 YzORdyPJroCrXZxCoBKceiZ3nUb，读取快照 revision 3 | 原生源文件 source-master.json；包含 162 / 162 与工业级/AI 生成措辞，GitHub 同名 MASTER_FEISHU_DOC.md 对应旧交付口径 | 162 / 2.96s 是历史文档陈述，不能替代完整原始日志或 CI | 保留为历史材料，引用当前证据修订过度措辞；不把 162 与 529 相加 |
| 旧详本 AQqCdG2Q3ogetUxgdFxcwKFgnah，revision 3 | 标题为 42 家生态详本；source-42-research.json 不含 529 新验收 | 调研素材与技术方向；不等于当前 structured sites 数量、功能已实现或效果实测 | 作为历史生态候选 / 补充分类；来源待逐条对齐后并入，不能与 46 简单相加 |
| **公开 GitHub main / 4e37d762037196df2eb044d0240ec8b602b44b67** | public；提交 2026-10-23 16:02:02 UTC（北京时间 10-24 00:02:02）；494 个 blob。37 个 research/sites（01–37），24 个 airap 文件；rap_workbench 只有 __init__.py / catalog.py；7 个测试文件 | 静态测试定义可核对 154 engine + 8 catalog = 162。远端仅有 8 项目录测试原始日志；没有可见的 GitHub Actions / Checks / status 成功证据 | **已公开的历史代码快照**。从该仓库 clone 不能得到现有 46 站、完整工作台、Sync 记录与 ASS 新能力 |
| **本地 f0623e8325b7975a931b41f93949d272fc179c03** | 4e37d76 是其祖先；相对新增 63 个提交（含 merge）。46 主域 / 42 full_page / 4 partial、完整工作台、Sync 契约、本地预览修复、显式 ASS 字幕烧录 | 原始 final-tests.txt：**529 passed, 393 subtests passed in 13.29s**；441 engine + 88 workbench；0 failure/error/skip。日志哈希与 verification.json 一致 | **本地已验收、尚未同步到所核验公开 main**；不得写成“这些能力已全量推送 GitHub” |
| 当前 46 站报告 TiqGd7dHWoAqBex3KCvcnzpVnKc，revision 14 | source-46-research.json 已含 46 站与后续迭代，529 的当前证据入口 | 详细边界及媒体样本验收随本地证据归档；不等于远端代码同步 | 可作为此次统一入口的现版正文依据；历史文档保留版本归属并链接到统一入口 |

两份代码的 pyproject.toml 都仍是 package version 0.1.0；不要仅以 0.1.0 区分新旧，必须使用 SHA / 日期 / 测试范围。

## 162 项：算式成立，但完整旧通过运行未被公开日志证明

公开快照内六个引擎文件的 test_ 定义逐一计数为：audio 32、avatar 27、compositor 21、lyrics 36、pipeline 2、subtitles 36，合计 154；tests/workbench/test_catalog.py 为 8，合计 162。此计数与旧总纲吻合，但“测试存在”不等于“当次完整运行通过”。

[远端 c41 原始日志](https://github.com/siuserxiaowei/ai-rap-video/blob/4e37d762037196df2eb044d0240ec8b602b44b67/artifacts/tests/c41.txt) 确实逐项记载 8 项 OK、0.115s；[旧总纲](https://github.com/siuserxiaowei/ai-rap-video/blob/4e37d762037196df2eb044d0240ec8b602b44b67/MASTER_FEISHU_DOC.md) 的“162 passed in 2.96s”是唯一对应完整旧数量的已找到文字陈述。公开树没有完整 162 项运行日志，也没有引擎 154 项的旧时原始运行报告。

本地后续 artifacts/iterations/engine-preview-20261024/baseline-tests.txt / baseline-verification.json 则提供了继承六个引擎模块 **154 passed in 2.49s** 的完整复测日志。4e37d76 到引擎迭代基线 7c16fe3 的 airap 与这六份测试没有差异，因此可支持“继承引擎后来在本地复测通过”；它不能冒充旧文档那一次 162 / 2.96s 的原始日志，也不是公开 GitHub CI。

只读 GitHub API 返回：

- [Actions runs](https://api.github.com/repos/siuserxiaowei/ai-rap-video/actions/runs?per_page=100)：total_count=0。
- [HEAD check-runs](https://api.github.com/repos/siuserxiaowei/ai-rap-video/commits/4e37d762037196df2eb044d0240ec8b602b44b67/check-runs)：total_count=0。
- [HEAD commit status](https://api.github.com/repos/siuserxiaowei/ai-rap-video/commits/4e37d762037196df2eb044d0240ec8b602b44b67/status)：statuses=[]、total_count=0；聚合 state=pending 是无 status 的返回值，不能写成“CI 正在跑”，更不能写成 passed。
- 公开树无 .github workflow；[branches](https://api.github.com/repos/siuserxiaowei/ai-rap-video/branches) 只有 main（上述 SHA），[tags](https://api.github.com/repos/siuserxiaowei/ai-rap-video/tags) 与 [releases](https://api.github.com/repos/siuserxiaowei/ai-rap-video/releases) 均为空。

结论应写“未找到公开 CI / 完整旧原始日志证据”，不能反推旧测试从未运行，也不能排除私下或外部系统的运行。

## 公开仓库当前具体包含什么

[公开树的固定 SHA](https://github.com/siuserxiaowei/ai-rap-video/tree/4e37d762037196df2eb044d0240ec8b602b44b67) 经 API recursive tree（truncated=false）核对，与本地同 SHA 的全部 494 个 blob 路径和 Git blob hash 完全一致；不用 origin/main 本地缓存来替代此次远端事实。

- 旧 airap：歌词/节拍/对齐与 mock avatar 规划、ASS/SRT、director、FFmpeg compositor、pipeline 和仅 generate/version 的旧 CLI。其成功文案忽略 false result.success，不能按字面宣传为真实 AI 人声 / 口型成片。
- 37 站结构化 JSON、37 份 notes 与当时 evidence；50 Gemini 会话材料和当时已有 Codex 材料；50 项 decisions 与早期工作台 SPEC / API contract。契约文本存在不代表接口已经实现。
- rap_workbench 只有 catalog 实现和目录校验测试。**没有 web/、server.py、briefs.py、jobs.py、quotes.py、exports.py 或 Sync 三模块**。
- examples/sample_lyrics.txt 存在，可用于旧命令历史复现。output/ 仅有 rap_lyrics.ass；没有随该快照发布可审查的 MP4 成片。ASS 存在不证明画面字幕已烧录。
- 仅 artifacts/tests/c41.txt 这一份工程测试原始 artifact；没有后续 iteration docs / 529 日志 / 工具链配方与验收脚本。

因此旧总纲“代码与调研已全量推送”的措辞至多描述当时部分材料；它不覆盖后来已经完成但未推到这个公开 main 的本地成果。

## 本地 529 / ASS 新能力的证据与未远端清单

本地 [字幕验收](../../docs/iterations/subtitle-burnin-20261024/verification.json) 的 tested_application_commit 是 de7871e690b96a86b374395ab04ffd772afbdbae；其后到 f0623e8 的 airap、rap_workbench、tests 与 pyproject 无差异。归档核心应用文件的 SHA-256 与 f0623e8 文件逐项一致，不把后续文档提交误称为重新执行测试的 SHA。

[原始 529 日志](../iterations/subtitle-burnin-20261024/final-tests.txt) 的 SHA-256 为 `de850fd8ca4edc2f9114b2299a3d6a598d577459f9129d85d969f7ae8c538cc2`，与 verification.json 匹配，日志包含 collected 529 items 与最终 529 / 393 subtests / 13.29s。393 个子测试单列，不与 529 混加宣传为 922 项。

尚未出现在公开 main 的部分包括：

1. 研究 38–46、46 站完整导出、真实 HTTP 工作台与 web 页面，brief SQLite、文字分镜 job / 幂等、历史来源报价、JSON/CSV/Markdown 导出与安全边界。
2. Sync REST 客户端、私有 SQLite 提交记录、plan/show/受门禁 refresh CLI、官方接口归档与本机 HTTP 契约测试。网页 provider_render 仍诚实 503；无真实供应商或计费验收。
3. `preview` 首选命令、兼容 generate、--lyrics-file / --output-dir / --json / --ffmpeg / --ffprobe / 字幕模式与字体参数；缺失输入拒绝、全部歌词调度、实际流/时长/FPS 检验、每 cut 裁剪、原子输出保护与明确程序化预览 metadata。
4. ProjectConfig 三项工具/模式字段、ASS 过滤器能力发现与路径处理、required/auto/off、7 项真实特殊路径 ASS 测试、中文采样帧与两画幅 CLI / 完整解码验收脚本和记录。
5. 529 项测试源、各轮 review / acceptance / verification、工具链构建配方与官方 hash 清单。**二进制、字体和生成媒体即使在本地 f0623e8 也不在 Git 内**；位于忽略目录，不能承诺 clone 后直接拥有它们。

实际 ASS 样本支持指定中文字幕的定时烧录 / 像素变化与完整解码，不支持 AI 人声、人物动画、快 Rap 口型、供应商质量 / 成本或网页 UI 已验收。字体 family 是请求名，实际 face resolution 仍未独立验证。C44/C45 的桌面、390px、键盘与浏览器下载门槛仍未关闭。

## 可运行命令的分发边界建议

合并稿先声明：“公开 GitHub 当前为 4e37d76 历史快照；下列工作台和新字幕命令仅适用于本地 f0623e8 或未来实际发布并核对的更新版本。当前没有执行推送。”不要给读者一个 clone 命令后紧跟只存在于本地的新模块命令，也不要给不可远端获取的 SHA 配一个暗示必定可 fetch 的 checkout 指令。

### 旧公开快照：只能历史复现旧入口

```bash
# 在已取得的公开 4e37d76 源码根目录，准备 Python3.10+、pytest、FFmpeg / FFprobe 后
python3 -m pytest -q
python3 -m airap.cli generate --lyrics examples/sample_lyrics.txt --bpm 130 --output legacy-preview.mp4
```

此命令语法存在；本次未重跑，不保证重现旧 2.96s。旧 CLI 会用误导性的成功文案，不应作为统一入口的现版能力证明。该公开快照不支持 preview、--lyrics-file、--json、显式字幕工具参数，也无法运行 `python3 -m rap_workbench.server`。

### 本地 f0623e8：工作台与程序化预览

```bash
# 此目录是本地现版；新 clone 的旧公开 main 不能直接使用这些命令
cd /Users/xiaowei/work/ai-rap-video-20261023
.venv/bin/python -m rap_workbench.server --port 8788
```

服务会占用该终端；另开终端，在同一项目根目录执行预览：

```bash
cd /Users/xiaowei/work/ai-rap-video-20261023
.venv/bin/python -m airap.cli preview \
  --lyrics '中文烧录预览' --bpm 240 \
  --ffmpeg .workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffmpeg \
  --ffprobe .workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffprobe \
  --subtitle-mode required --subtitle-font 'Arial Unicode MS' \
  --output subtitle-preview.mp4 --output-dir output --json
```

工作台端口可另选，默认只绑定 127.0.0.1。第二条命令要求该本地 ASS 工具链和请求字体存在；不是随 Git 发布的便携工具。缺失的显式工具不得自动回退，所请求字体名不证明解析到同名 face。

### 复现完整 529：必须满足工具链前提

```bash
AIRAP_TEST_FFMPEG="$PWD/.workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffmpeg" \
AIRAP_TEST_FFPROBE="$PWD/.workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffprobe" \
.venv/bin/python -m pytest -q
```

这要求当前本地源 / 测试和已构建的 libass-enabled FFmpeg / FFprobe；不设这两个变量会跳过 7 个真实 ASS 可选用例，不能再称“529 passed / 0 skip”。平台与依赖要求、构建配方和哈希见 [TOOLCHAIN.md](../../docs/iterations/subtitle-burnin-20261024/TOOLCHAIN.md)；应用 Python 最低 3.10+、构建助手另需 Python3.12+，本次归档验收环境为 Python3.15.0 / pytest9.1.1 / macOS。不要把本机已安装依赖当作 clone 自动具备，也不要把提供字体名称当作下载 / 安装字体。

## 只读取证记录

GitHub API 原始响应保存在 `/tmp/rap-consolidation-gh-tree.json`、`-runs.json`、`-checks.json`、`-status.json`、`-branches.json`、`-tags.json`、`-releases.json`。其中 tree 与 Git 对象逐 blob 核对；repo public / main / pushed_at 另通过实时 gh api 复核（pushed_at 2026-10-23T16:02:05Z）。没有读取或打印凭据。

建议统一入口用一句话归档：“旧总纲与详本保留历史调研和 162 项口径；当前本地 46 站 / 529 项采用原始日志和分阶段边界。公开代码仍停在历史 4e37d76，新能力尚未同步到该远端。程序化预览与所选字幕样本已验收，真实 AI 人声 / 口型、供应商质量成本及浏览器门槛仍待验。”
