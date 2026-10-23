# Rap Research Studio 运行与验收说明

本工具把公开来源研究与创作参数组织在一起，当前交付范围是研究目录、比较、来源详情、报告导出、brief 保存/回读、文字分镜和历史竞品价格参考。真实视频渲染没有 provider adapter；`provider_render` 返回明确不可用，不提交供应商计费或生成假媒体。

## 本地运行

Python 3.10+，无需为工作台安装第三方库。从仓库根目录运行：

```bash
python3 -m rap_workbench.server --port 8788
```

访问 <http://127.0.0.1:8788/> 和 <http://127.0.0.1:8788/create.html>。默认只绑定本机；当前 8787 被其他进程占用，勿停止其他进程。示例端口 8788 已有本项目服务时可直接访问；需要新实例则选择其他空闲端口。Ctrl+C 停止自己启动的服务。服务启动时加载研究快照；更新 `research/sites/` 后重启该实例再核对数量。

brief 默认存储于 `.workbench/briefs.sqlite3`，job 存储于 `.workbench/jobs.sqlite3`。它们是本机持久化数据；重启仍能读取。原型没有用户账户、多人数据隔离、公开部署或媒体上传接口，当前页面的照片仅用浏览器 object URL 作本地参考，不进入 brief。

## 页面流程

1. 在研究目录用关键词、六类用途、API 资料和证据状态组合筛选；最多选三个站点比较，详情展示原始 URL、支持范围和待核限制。
2. 导出完整目录 JSON、CSV 或 Markdown；Markdown 同时包含 50 项决策。导出范围为全目录，搜索结果不会改变导出范围。
3. 在创建页输入主题、solo/duo、场景、10/12/15 秒、画幅、目标画质、语言与可空歌词；这些是本地创作参数，不代表某个供应商接受这些组合。
4. 保存后从后端回读记录，可刷新列表、打开或下载 brief JSON；另可请求和下载文字分镜。文字规划标记 `is_generated_video=false`。
5. 可查询 RapReel 历史一次性套餐参考。只精确匹配 8 秒/480p、12 秒/720p、15 秒/720p；创建页不提供 8 秒，因此该档仅 API 可查。9:16 是对官网 vertical 的映射推断。无匹配返回 `estimate=null`，不表示免费；`is_vendor_quote=false`，不是实时报价、自建服务成本或结账金额。

## HTTP 接口

| 方法与路径 | 用途及关键边界 |
| --- | --- |
| `GET /api/sites` | 返回 `sites/total/filtered`；支持 `q/category/api_status/evidence_status`，条件为 AND |
| `GET /api/sites/<两位编号>` | 完整站点记录 |
| `GET /api/stats` | 按主域去重的数量、类别、API、证据和最近核查日期 |
| `GET /api/decisions` | 本地 50 项决策记录 |
| `GET /api/report?format=json\|csv\|markdown` | UTF-8 下载，保留日期、证据、限制和来源；CSV 中和公式前缀 |
| `POST /api/briefs` | 校验并保存八个创作字段，返回 UUID 和创建时间 |
| `GET /api/briefs`、`GET /api/briefs/<uuid>` | 列表与回读 |
| `POST /api/quote` | 输入时长、画质、画幅及可选站点编号；仅支持上述历史价格参考 |
| `POST /api/jobs` | `brief_preview` 生成文字分镜；`provider_render` 返回 503 `PROVIDER_UNAVAILABLE` |
| `GET /api/jobs/<uuid>` | 回读文字规划任务 |

POST 使用 UTF-8 `application/json`，请求体上限 1 MiB。brief 八字段为 `topic/mode/stage/duration_seconds/aspect_ratio/quality/lyrics/language`，不接受文件路径、照片或客户端指定 UUID。job 可用 `Idempotency-Key`；同键同规范输入复用，同键不同输入返回 409。静态服务只读取 `web/` 内文件，不直接公开仓库或原始证据。

## 研究口径和复核

2026-10-23 至 2026-10-24 取得 46 个不同主域记录，其中 42 个 `full_page`、4 个 `partial`（15 Musicful、30 Kling、32 Pika、36 FineShare Singify）。分类为 Rap 19、音乐视频 11、通用视频 6、口型 4、音乐 3、编辑 3；API 为 `documented` 17、`not_found` 29。数据以 `catalog.load_sites` 动态校验为准。

`full_page` 仅表示至少有相关官方正文，不能推出价格、生成、下载、版权或上线状态均被验证。`documented` 只表示有相关公开接口资料，仍需读具体覆盖范围；`not_found` 仅表示本次未定位文档。不同站点的 credits、年付折月、免费歌曲/静图/预览不能直接换算成同一个视频价格。

C01–C50 为 50 个 Codex 任务的执行计划；调用、完成、部分验收和完整验收由主线程按实际台账审计，前端视觉缺口不能计作完整验收。`research/gemini/summary.json` 记录 50 个独立有效会话；`supplemental-G50.json` 延续原 G50，不构成第 51 个会话，也不新增外部事实证据。补充分析里“已开放”“未正式开放”及 46 的美元/积分混写不能覆盖逐站 JSON 的待核结论。`docs/decisions.json` 有 D01–D50，引用编号均存在，当前状态全部 `planned`；决策方向与实现验收应分别记录。

完整研究 schema 见 [RESEARCH_CONTRACT.md](RESEARCH_CONTRACT.md)，模块契约见 [docs/WORKBENCH_SPEC.md](docs/WORKBENCH_SPEC.md)。分模块审查记录是各自提交时的快照，其旧测试数量和站点数不能代替当前集成复测。

## 自动化检查与尚待完成的验收

```bash
python3 -m unittest discover -s tests/workbench -p 'test_*.py' -v
node --check web/app.js
node --check web/create.js
git diff --check
```

单测包含研究校验、来源路径、筛选、SQLite 往返、请求拒绝、任务幂等/冲突、未接入供应商、报价与导出；其中真实 HTTP 测试使用临时数据库和本机服务。证据采集器的网络异常测试使用 mock，不能证明其重新抓取了全站。当前最终集成结果见 [docs/C50-review.md](docs/C50-review.md)。`airap` 的测试由主线程另行执行，本套测试不证明其能力。

桌面和 390px 真实页面、键盘焦点、照片选择、筛选/比较、保存与浏览器下载仍未验证。浏览器 CUA 已因当前页面访问策略被终止；本轮未调用其他浏览器或替代工具绕过。HTTP 成功和静态 CSS 检查不能替代这些验收。

下一步须依据当前官方文档实现一个实际 provider，使用专用凭据和获授权的人物/音轨样本，验证中文快 Rap、双人/遮挡、真实音频与口型、媒体下载、延迟、费用、失败重试及对账；随后完成桌面/390px视觉与交互验收。飞书发布还需原生创建、真实 URL 和标题、46 站、来源、50 决策的回读记录，由主线程完成后更新发布状态。当前不声称整体目标已完成。
