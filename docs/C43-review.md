# C43：HTTP 后端与 brief 持久化验收

本轮仅实现 `rap_workbench/server.py`、`rap_workbench/briefs.py` 及对应测试。Python 3.10+ 标准库；启动 `python3 -m rap_workbench.server --port 8787`，默认监听 `127.0.0.1`。前端未提供时 `/` 返回结构化 404。研究数据由现有 catalog 校验后加载，错误不降级成已验证数据。

## 接口与持久化

- 所有 wire 路由已接入。`GET /api/sites` 返回 `sites/total/filtered`，stats 保持 catalog 的六个约定字段，decisions 读取本地 `docs/decisions.json`。
- `validate_brief(payload)` 返回新字典，topic 去首尾空白；默认 `solo/studio/12/9:16/720p/空歌词/zh`。topic、lyrics 长度、枚举、整数时长、UTF-8 字符与未知字段都验证；拒绝路径、id、created_at 等额外输入。
- `BriefStore(path).create/list/get` 使用 SQLite JSON 和参数化 SQL；返回增加 UUID 与 UTC created_at 的完整 record；不存在的合法 UUID 返回 None，非法 UUID 抛 ValueError。每次操作使用单独数据库连接，支持 HTTP 线程并发与进程重开读取。
- 默认 brief DB 为仓库 `.workbench/briefs.sqlite3`；jobs DB 为同目录 `jobs.sqlite3`。HTTP 不允许指定本地数据库或文件路径。
- 可选模块 lazy import：`quote(payload)` 返回 dict；`export_json/csv(sites)`、`export_markdown(sites, decisions)` 返回字符串；`JobStore(path).create(payload, idempotency_key)` 返回 `(job, created_bool)`，get 返回 record 或 None。新建 job 201、重放 200；`IdempotencyConflict(ValueError)` 对应 409，`ProviderUnavailable(RuntimeError)` 对应 503。模块缺失明确 503 `MODULE_UNAVAILABLE`。

## 两条研究完整流程复核

复核范围为既有 01/02 records、notes，以及各自首页/价格页完整归档的工作流段落；没有注册、付费、上传媒体或执行第三方生成。以下为官网流程宣称及对本地后端的推导，不能据此声称质量或生成能力已验证。

### 01 RapVideoGenerator

来源：[首页](https://rapvideogenerator.com/)、[价格页](https://rapvideogenerator.com/pricing)，本地证据 `research/evidence/01/home-jina.txt`、`pricing-jina.txt`。

完整流程：主题或歌词 → 选择 beat/voice → 免费预览并编辑歌词 → 生成两版歌曲并试听/选择/下载 MP3 → 选择片段 → 添加自拍、场景与视频参数 → 消耗视频积分 → My Studio 下载 9:16 MP4；官网宣称失败自动退回积分。免费歌曲额度与最低视频积分不同，视频仅列 10/15 秒，1080p 还受套餐限制。

后端影响：保存 brief 是创作参数保存阶段，不能替代试听、片段选择、媒体同意或生成。故本轮不接收照片/音频路径，brief_preview 只能返回分镜参数；provider_render 未配置必须 503。原型允许的 12 秒、方形/横形来自工作台契约，不代表本站供应商支持；报价模块必须按来源与精确规格匹配，不能将注册赠送、跨站积分、年付折月数值转成单次视频报价。后续真实 adapter 需要独立的音频版本、片段、排队、失败/退款和输出记录，不能挪用 brief id 假装媒体 URL。

### 02 RapVideo.ai

来源：[首页](https://rapvideo.ai/)、[价格页](https://rapvideo.ai/pricing)，本地证据 `research/evidence/02/home.jina.txt`、`pricing.jina.txt` 和同页 `pricing.html` 的 JSON-LD 套餐信息。

完整流程：两张肖像或双人照（左侧 lead、右侧 hype） → 选舞台 → 选模板原曲、自带音轨或主题生成原创 rap → 按音源选择 Wan/Seedance 模型 → 配画幅、时长、清晰度 → 显示精确积分 → 提交渲染 → My videos 下载 MP4。自带音轨在浏览器裁为 2–15 秒；主题上限 120 字符是该站限制。免费仅指定模板的 2 秒、480p、有水印站内预览；失败退积分与七日媒体删除均为政策宣称。

后端影响：duo 与 stage 是可保存的创作意图，不能推断任意模型都支持这些组合。当前 topic 上限 240 按本地契约保留；将来 adapter 必须再验证供应商的 120 字符与媒体/音轨规格。原型 preview 必须保留 `is_generated_video: false`，不能冒称免费生成完整视频或音乐授权。任务幂等键需覆盖完整规范输入；模型超时、失败和重试应为真实任务状态，不能返回伪进度。模板音乐权利、素材删除策略与商用授权不能从“无水印”推导。

## 验证结果

执行 `python3 -m unittest discover -s tests/workbench -p 'test_*.py' -v`：19 tests passed，包含现有 8 项 catalog 测试、新增 5 项 brief 与 6 项真实 HTTP 测试。

真实 HTTP 检查了 POST brief 201 → GET 单条/列表 → 服务重启后 GET 保留；非法字段/JSON/UTF-8/重复键、负 Content-Length、超过 1 MiB、错误 MIME、Transfer-Encoding 均有结构化错误。静态请求只允许 web 内普通文件，拒绝明文/编码路径穿越、隐藏目录、`.git`、越界 symlink 和隐藏文件 alias；研究文件和仓库 docs 不能直接访问，没有宽泛 CORS。可选模块以接口桩检查了报价、三种下载 MIME/文件名、job 新建/重放/冲突/供应商 503；其真实实现由后续模块集成测试验收。

限制：当前是本地研究/brief 工具，无账户、照片上传、付款、真实供应商 adapter 或 AI 媒体生成；可选模块未合入时其路由明确不可用。未创建或改动前端文件。
