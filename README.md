# AI Rap Video · Rap Research Studio / AIRapStudio

本仓库包含公开网站研究、本地研究与创作 brief 工作台，以及独立开发的 `airap` 音视频处理模块。研究工作台当前未接入真实生成供应商；保存 brief 或完成文字分镜任务不会生成 AI 人声、口型视频或成片。

## 启动研究工作台

需要 Python 3.10+，工作台只使用标准库。在仓库根目录运行：

```bash
python3 -m rap_workbench.server --port 8788
```

打开 <http://127.0.0.1:8788/> 查看研究、检索筛选、比较最多三站及导出；<http://127.0.0.1:8788/create.html> 可保存、回读和下载创作 brief，取得文字分镜与历史竞品价格参考。默认绑定 `127.0.0.1`；8787 当前被其他进程占用，示例使用 8788。若 8788 已有本项目服务，直接访问或另选空闲端口。

当前研究样本为 **46 个不同主域，42 站取得相关官方正文，4 站部分读取**，采集日期为 2026-10-23 至 2026-10-24。正文读取不代表效果、下载、授权或服务上线已被实测；本次检索不代表全网穷尽。50 项产品与技术决策均有站点引用，各项状态及验证引用见 `docs/decisions.json`，其中仍有待浏览器和真实供应商验证的项目。

已交付 C01–C50 共 50 个 Codex 任务，以及 50 个独立 Gemini 会话；Codex 48 个任务完整验收，C44/C45 待真实浏览器验收。原 G50 的补充分析复用同一会话，不额外计数。后续复用 C48/C49/C50，在各轮隔离 worktree 实现 Sync 客户端、持久化记录、本地预览修复及真实字幕烧录；所有后续 worktree 均经审查、复测后回收，不增加独立agent数。最新529项检查通过，包含工作台88项与引擎441项；竖/横全高清字幕样本经探测、完整解码和选定中文帧查看。客户端默认关闭联网，本轮未调用真实供应商；网页渲染接口仍返回503。前端桌面与390px真实交互尚未验证，整体目标仍有未关闭验收项。

运行细节、HTTP 接口与命令行用法见 [WORKBENCH.md](WORKBENCH.md)，[Sync接口验收](docs/iterations/provider-sync-20261024/verification.json)、[引擎预览验收](docs/iterations/engine-preview-20261024/verification.json)和[字幕烧录验收](docs/iterations/subtitle-burnin-20261024/verification.json)分别记录覆盖范围，首次发布的独立终审快照见 [docs/C50-review.md](docs/C50-review.md)。

## 目录与证据

| 路径 | 内容 |
| --- | --- |
| `rap_workbench/`、`web/` | 本地 HTTP 后端、研究目录与 brief 页面 |
| `research/sites/`、`research/notes/`、`research/evidence/` | 结构化条目、研究笔记与原始公开来源 |
| `research/codex/`、`research/gemini/` | 任务与会话台账、输出和验收记录 |
| `docs/decisions.json`、`PLAN.md`、`RESEARCH_CONTRACT.md` | 50 项决策、执行计划与研究 schema |
| `docs/WORKBENCH_SPEC.md`、`docs/C41-review.md` 至 `docs/C50-review.md` | 工作台契约与分模块审查 |
| `scripts/`、`tests/workbench/` | 证据采集、报告与验收工具、工作台测试 |
| `.workbench/` | 本地 SQLite brief / job / provider 提交记录；不通过静态服务公开 |
| `airap/` | 独立的音视频处理模块，能力与测试证据另行核验 |

```bash
python3 -m unittest discover -s tests/workbench -p 'test_*.py' -v
node --check web/app.js
node --check web/create.js
```

这些命令覆盖本地自动化检查，不替代浏览器、真实供应商或付费生成验证。[飞书研究报告](https://vi8r050ecuz.feishu.cn/docx/TiqGd7dHWoAqBex3KCvcnzpVnKc) 已原生发布，接口、引擎与字幕迭代已追加至revision14并全文回读；原46站、50项决策与来源链接完整保留，原始字幕采样图也已回读验证。当前外部验收条件见 [阻塞审计](docs/BLOCKED_AUDIT.md)。

## AIRapStudio 模块与命令

`airap` 提供本地程序化预览：用测试图案、节拍或提供的本地音频、逐词字幕和 FFmpeg 合成 MP4。它与研究工作台的供应商接入是不同路径。当前不生成 AI 人声、人物动画或口型；mock 头像状态仅是规划数据，未渲染进视频。请求主题会记录为 `requested_theme`，实际视觉尚未应用主题。

- `airap.lyrics`：歌词、Flow 与节拍对齐处理。
- `airap.audio`：BPM、瞬态能量与音素时间信息处理。
- `airap.avatar`：音素/视素和口型适配相关处理。
- `airap.director`：剪辑时间线与镜头效果处理。
- `airap.subtitles`：逐词字幕及 ASS/SRT 导出。
- `airap.compositor`：FFmpeg 多轨道合成。
- `airap.pipeline`：串联各处理阶段的流水线入口。

本地预览与测试：

```bash
# 使用已安装pytest的Python环境；工作台自身不需要第三方库
python3 -m pytest -v

# 明确读取UTF-8歌词文件，默认仅生成器乐节拍
python3 -m airap.cli preview --lyrics-file sample.txt --bpm 130 --output preview.mp4 --output-dir output --json
```

`generate` 保留为 `preview` 的兼容别名。`--lyrics` 也接受直接文字；已有文件路径仍兼容读取。`--audio FILE` 使用提供的本地音频，缺失或不可读会报错；不提供该参数才合成节拍。人物图片暂不支持。输出文件参数只接受 `.mp4` 文件名，目录用 `--output-dir` 指定。

歌词上限为64 KiB UTF-8，BPM为40–300，按全部有效小节计算的预览时长最多120秒；超过限制明确拒绝，不再静默截断到16小节。结果元数据区分实测/请求时长、字幕是否烧录及真实音画来源。当前工作区已验证的解释器为 `.venv/bin/python`（Python3.15）；其他环境需Python3.10+、pytest、FFmpeg及FFprobe。生成的节拍和ASS存于每次独立的 `preview-assets-*` 子目录，供返回记录继续引用；由使用者按需清理。

字幕烧录需要FFmpeg的ASS滤镜。本机默认FFmpeg8.1.1仍不具备该滤镜；项目内另构建了含libass的8.1.1，通过 `--ffmpeg` / `--ffprobe` 显式选择。`--subtitle-mode required|auto|off` 控制烧录策略，`--subtitle-font` 设置请求字体。实际已验证required和auto烧录、off不烧录，以及不支持ASS时明确失败。不能将字幕文件存在或字体名字当作实际烧录/字体解析证明。完整命令、529项含真实ASS测试和构建配方见 [字幕工具链说明](docs/iterations/subtitle-burnin-20261024/TOOLCHAIN.md)。引擎成功前校验成片音视频流、尺寸、帧率与实测时长；验证失败保留旧输出。
