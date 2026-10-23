# C45 / 50 — 创作 brief 页面实现审查

实现范围：`web/create.html`、`web/create.css`、`web/create.js`。使用独立 CSS，与研究工作台蓝灰色正文、蓝色控制和琥珀强调保持一致；未修改 C44 的入口页面、样式或脚本。返回研究工作台的路径为 `/`。

## 研究如何影响流程

1. **RapReel**（研究记录 `research/sites/03.json`，证据 `research/evidence/03/home.txt`，检查日期 2026-10-23；[官网](https://rapreel.com/) / [价格页](https://rapreel.com/pricing)）：公开页面先提供舞台静图预览，再让用户查看规格和按条价格。由此采用“主题与人物 → 舞台 → 规格与歌词 → 本地参考 → 保存”的明确顺序，持续展示参数及三段分镜文字规划。当前应用没有其图像与视频能力，因此明确标注“文字规划”“未进行 AI 视频生成”，没有把规划包装为其免费静态舞台效果。价格查询作为独立辅助操作，不阻碍 brief 保存。
2. **RapVideoGenerator**（研究记录 `research/sites/01.json`，证据 `research/evidence/01/home-jina.txt`，检查日期 2026-10-23；[官网](https://rapvideogenerator.com/) / [价格页](https://rapvideogenerator.com/pricing)）：公开页面区分主题与自写歌词，并将歌词确认、音乐及后续照片视频分阶段处理。由此将必填主题与可空歌词分开，保留语言、目标画质及场景的显式标签。留空歌词如实保存为空；不自动补词、不把免费歌曲或订阅折月价解释成免费视频。页面在规格附近说明当前只是计划，实际效果待制作。

以上仅复用仓库内已有官网研究和证据，未重新联网核验、注册、付费或实测这两个供应商，未据此推断生成品质或转化效果。

## 技能与交互检查

已读 UI/UX Pro Max SKILL、`design-system/rap-research-studio/MASTER.md`、`docs/DESIGN_NOTES.md`，沿用已验证的 Data-Dense Dashboard 方向及系统中文字体，不引入远程字体或依赖。补充运行 `error summary validation --domain ux`，命中 Focusable Error Summary、Error Messages、Error Placement：失败表单聚焦顶部摘要，链接到字段，字段下保留错误及 `aria-describedby`；请求状态使用 live region。

桌面侧栏、手机顶部导航；布局无固定窄屏宽度，390px 使用单列内容和两列字段；所有主要按钮最小 44px，键盘焦点可见，尊重 `prefers-reduced-motion`。照片尺寸上限为 10 MB，仅通过 objectURL 预览并释放 URL；没有上传、base64 或照片持久化。所有返回数据、用户文本和第三方字段以 `textContent` 渲染。

## HTTP 契约

- `POST /api/briefs` 严格只含 topic、mode、stage、duration_seconds、aspect_ratio、quality、lyrics、language 八个字段。歌词保留用户原文，主题去除首尾空白。
- 保存后通过 `GET /api/briefs/<uuid>` 真正回读；初始加载和刷新通过 `GET /api/briefs` 列表。打开和下载每条保存记录时再次 GET。保存后的 id、created_at 不进入后续 create 或 job brief。
- `POST /api/jobs` 仅请求 `{mode: "brief_preview", brief: <八个字段>}`。成功要求 completed / brief_preview / is_generated_video=false / storyboard 数组。缺模块显示真实 API 错误，仍可查看明确标注的本地文字规划；无假媒体、假进度或虚构任务。
- `POST /api/quote` 只传 duration_seconds、quality、aspect_ratio。要求 is_vendor_quote=false，estimate=null 明示“暂无可比报价，不代表 0 元”，展示 basis 和 assumptions；模块错误提供原按钮重试，改变规格后清除旧结果。
- 可下载服务端回读的 brief JSON；分镜 JSON 标明来源与 is_generated_video=false。浏览器照片不会进入两类 JSON。

## 已执行验证

- `node --check web/create.js`：通过。
- `git diff --check`：通过。
- 使用真实 `WorkbenchServer`、临时 SQLite 数据库及标准库 HTTP 客户端：三个新静态文件均 200；创建 brief 返回 201，随后 GET 单条及 GET 列表内容一致；空歌词、中文与 `<script>` 文本原样回读；solo/en/15秒/16:9/1080p 组合创建成功；返回记录携带 id/created_at 重新 POST 得到真实 400（前端显式字段白名单避免此问题）。
- 当前工作树尚无 quotes/jobs 模块；两条真实 HTTP 请求分别得到 503 / MODULE_UNAVAILABLE，符合页面错误处理的预期。未伪造成功响应。

## 交给 root 统一验收

尚未进行真实浏览器的 1440px/390px、键盘、照片选择、下载内容和截图验收。报价与 job 成功分支待对应模块合并后由 root 端到端验证。当前已进行语法与真实保存/回读 API 检查，没有把静态审查表述为浏览器实测。
