# AI Rap Video · Rap Research Studio / AIRapStudio

本仓库包含公开网站研究、本地研究与创作 brief 工作台，以及独立开发的 `airap` 音视频处理模块。研究工作台当前未接入真实生成供应商；保存 brief 或完成文字分镜任务不会生成 AI 人声、口型视频或成片。

## 启动研究工作台

需要 Python 3.10+，工作台只使用标准库。在仓库根目录运行：

```bash
python3 -m rap_workbench.server --port 8788
```

打开 <http://127.0.0.1:8788/> 查看研究、检索筛选、比较最多三站及导出；<http://127.0.0.1:8788/create.html> 可保存、回读和下载创作 brief，取得文字分镜与历史竞品价格参考。默认绑定 `127.0.0.1`；8787 当前被其他进程占用，示例使用 8788。若 8788 已有本项目服务，直接访问或另选空闲端口。

当前研究样本为 **46 个不同主域，42 站取得相关官方正文，4 站部分读取**，采集日期为 2026-10-23 至 2026-10-24。正文读取不代表效果、下载、授权或服务上线已被实测；本次检索不代表全网穷尽。50 项产品与技术决策均有站点引用，各项状态及验证引用见 `docs/decisions.json`，其中仍有待浏览器和真实供应商验证的项目。

已交付 C01–C50 共 50 个 Codex 任务，以及 50 个独立 Gemini 会话；Codex 48 个任务完整验收，C44/C45 待真实浏览器验收。原 G50 的补充分析复用同一会话，不额外计数。后续复用 C48/C49/C50 实现 Sync 客户端、持久化提交记录和本地计划/状态观察 CLI，三个隔离 worktree 已验收回收，合并后88项测试通过。客户端默认关闭联网，本轮未调用真实供应商；网页渲染接口仍返回503。前端桌面与390px真实交互尚未验证，整体目标仍有未关闭验收项。

运行细节、HTTP 接口与命令行用法见 [WORKBENCH.md](WORKBENCH.md)，最新接口迭代验收见 [verification.json](docs/iterations/provider-sync-20261024/verification.json)，首次发布的独立终审快照见 [docs/C50-review.md](docs/C50-review.md)。

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

这些命令覆盖本地自动化检查，不替代浏览器、真实供应商或付费生成验证。[飞书研究报告](https://vi8r050ecuz.feishu.cn/docx/TiqGd7dHWoAqBex3KCvcnzpVnKc) 已原生发布，后续接口迭代已追加至revision11并全文回读；原46站、50项决策和155个来源链接均保留。

## AIRapStudio 模块与命令

`airap` 保留歌词分析、音频分析、头像/口型适配、时间线导演、字幕和 FFmpeg 合成等模块入口。它与研究工作台的 provider 接入是不同路径；下列模块说明和命令不能证明真实 AI 人声、精确口型或成片质量已通过终审，外部并行开发的实现与测试由主线程另行确认。

- `airap.lyrics`：歌词、Flow 与节拍对齐处理。
- `airap.audio`：BPM、瞬态能量与音素时间信息处理。
- `airap.avatar`：音素/视素和口型适配相关处理。
- `airap.director`：剪辑时间线与镜头效果处理。
- `airap.subtitles`：逐词字幕及 ASS/SRT 导出。
- `airap.compositor`：FFmpeg 多轨道合成。
- `airap.pipeline`：串联各处理阶段的流水线入口。

保留原有测试与 CLI 用法：

```bash
# airap 测试入口；须按实际测试结果判断覆盖范围
pytest -v

# airap CLI 生成命令示例；能力与输出需另行验证
python3 -m airap.cli generate --lyrics "sample.txt" --bpm 130 --output "output.mp4"
```
