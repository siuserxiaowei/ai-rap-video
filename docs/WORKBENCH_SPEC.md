# Rap Research Studio：开发与验收契约

## 用户任务
研究负责人需要从有出处的网站样本找到合适的创作路径，比较定价边界，并把自己的 Rap 视频创意保存成可执行 brief。工作台是研究与流程验证工具；真实生成供应商尚未接入时，不能声称生成了 AI 人声或口型视频。

## 技术与模块边界
Python 3 标准库后端，原生 HTML/CSS/ES modules 前端。避免依赖安装和未经验证的账户/付款链路。公开研究数据来自 `research/sites/*.json`，schema 见 `RESEARCH_CONTRACT.md`。新增模块位于 `rap_workbench/`；保留外部进程正在开发的 `airap/`，不要覆盖。

入口 `python3 -m rap_workbench.server --port 8787`，默认绑定 127.0.0.1。静态页面 `/`，研究 API `/api/sites`、`/api/sites/<id>`、`/api/stats`；`GET /api/decisions` 读取 50 项决策；`GET /api/report?format=markdown|json|csv` 导出；创建 brief `POST /api/briefs`，列出及查看 `/api/briefs`、`/api/briefs/<id>`；报价 `POST /api/quote`；任务 `POST /api/jobs` 和 `GET /api/jobs/<id>`。

`rap_workbench/catalog.py`：load_sites(root)、filter_sites(sites, query='', category='', api_status='', evidence_status='')、stats(sites)、validate_site(record, root)。数据错误应返回清楚诊断，不悄悄补全为已验证。

`rap_workbench/briefs.py`：BriefStore(path)、create(payload)、list()、get(id)。SQLite 保存 JSON，输入 topic、mode（solo/duo）、stage、duration_seconds（10/12/15）、aspect_ratio（9:16/1:1/16:9）、quality（480p/720p/1080p）、lyrics（可空）、language（zh/en）。不上传真人照片，prototype 可仅用浏览器本地预览。ID 用 uuid，不接受任意文件路径。

`rap_workbench/jobs.py`：JobStore(path)，create(payload, idempotency_key)、get(id)、list()；任务模式只接受 `brief_preview`（返回分镜/参数记录），`provider_render` 未配置时明确 503/ProviderUnavailable，绝不成功返回假视频。可测试 state transitions，重复幂等键相同 payload 同一任务，不同 payload 冲突。

`rap_workbench/quotes.py`：quote(payload) 返回 estimate、currency、basis、assumptions、is_vendor_quote=false。报价必须可以追到具体研究条目；跨站 credits 不可相加；不可把订阅折月当单次单价。优先采用 RapReel 3 个单次套餐（8/12/15 秒）做对比示例，自建供应商成本单列为待核；若用户请求不匹配规格，应明确无可比报价。

`rap_workbench/exports.py`：export_json(sites)、export_csv(sites)、export_markdown(sites, decisions=[])。输出带日期、证据等级、链接、限制；CSV 应防公式注入，UTF-8 可读；所有 UI 以 textContent 渲染网站第三方字段。

`rap_workbench/server.py`：ThreadingHTTPServer、统一 JSON 错误、Content-Length 上限 1MiB、只暴露静态 web 和已指定 API；不得用 SimpleHTTPRequestHandler 无差别共享 repo 或 `.git`/env。校验 URL 和编号，静态路径不可穿越。无宽泛 CORS。

## 页面与样式
`web/index.html`、`web/styles.css`、`web/app.js` 为研究工作台；`web/create.html`、`web/create.js` 为创建 brief 流程。`web/shared.js` 只放共用 fetch/DOM helpers。

视觉：研究密集型 dashboard，清楚区分“来源读取”“待验证”和“真实生成未接入”。蓝/灰正文、琥珀色强调，系统中文字体；音乐风格可由少量 SVG 波形表达，不依赖外部图片或字体。桌面侧栏，手机顶部导航；搜索、类别/API/证据筛选、站点卡/表、最多 3 站比较、来源明细面板、统计、可下载 JSON/CSV/Markdown。提供加载、空结果、错误和重试。所有控件有可见标签、键盘焦点，44px 触区，390px 无横向溢出，prefers-reduced-motion。

创建流程：主题 → solo/duo → 场景 → 时长/画质/比例 → 歌词或留空 → 本地预览 → 保存 brief。页面清楚说明未进行 AI 视频生成，可下载 brief/分镜。禁止显示虚构进度、假作品、虚构使用量或不实价格。

## 测试与验收
标准库 unittest；关键行为测真实输入与异常：记录 schema、唯一域名/来源文件、筛选、幂等/冲突、参数拒绝、SQLite 持久化、CSV 注入防护、路径穿越、HTTP POST 与 GET 完整往返、供应商未接入的诚实错误。浏览器以 1440px/390px 检查研究筛选、比较、详情来源和 brief 保存下载。目录名 `tests/workbench/`，不影响外部 engine tests。

## 供应商后续开发
以官网有公开文档的平台（Sync/HeyGen/Runway/Luma 等，经各站研究确认）做 adapter 选择；真实成本、音频/视频端点、取消、重试、webhook 和权限需基于其文档实现。用户未提供授权人物媒体与专用供应商 key 时，不编造成功实例。当前先完成研究和本地可验收流程。
