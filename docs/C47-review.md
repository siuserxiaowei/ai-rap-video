# C47：有来源的价格对比参考

本次只复核仓库保存的 2026-10-23 官网证据。实现不联网，不请求生成供应商，不上传照片，不登录、不付款。`quote(payload)` 返回历史竞品价格参考，不是实时供应商报价、结账单、发票或自建服务成本。

## 已实现的接口

`POST /api/quote` 由现有 `rap_workbench/server.py` 调用新模块，HTTP 成功响应仍为 `{"quote": {...}}`。输入仅限必填 `duration_seconds`、`quality`、`aspect_ratio` 与可选 `site_id`；默认站点为 `03`。未知字段、缺失字段及类型错误抛 `ValueError`，服务返回 400 / `INVALID_INPUT`。时长必须为正整数，明确拒绝 bool、浮点数及字符串。

仅将时长和画质与 RapReel 下面三档逐项匹配，不作秒价、插值、折扣或积分转换：

| 官方套餐 | 时长 | 画质 | 每条一次性官网标价 |
|---|---:|---|---:|
| Lite | 8 秒 | 480p | 2.99 USD |
| HD | 12 秒 | 720p | 3.99 USD |
| Pro | 15 秒 | 720p | 5.99 USD |

金额及套餐来自 [03 研究条目](../research/sites/03.json) 和 [官网价格页快照](../research/evidence/03/pricing.txt)；[原始 HTML](../research/evidence/03/pricing.html) 中三档 JSON-LD 的 `priceCurrency` 均为 USD。原官网来源为 [RapReel pricing](https://rapreel.com/pricing)。

官网仅声明 `vertical`，没有精确 `9:16` 尺寸。本工作台将 9:16 作为竖屏映射推断，并在每条 RapReel 返回的 assumptions 与匹配 basis 明示；`matched_spec` 保留官网支持的 `orientation: vertical`，不伪造官网画幅参数。1:1、16:9 或其他画幅返回 `estimate: null`。

常见原型配置 10 秒/720p/9:16 没有匹配，返回 `estimate: null`、`matched_spec: null`，basis 明确“无报价不代表免费或零价”。其他不匹配时长/画质同样处理。未支持站点返回 null，并将 `source_url`、`currency`、`checked_at` 设为 null，避免将 RapReel 来源错误归给该站。

返回始终包含 estimate、currency、basis、assumptions、`is_vendor_quote: false`、source_url、matched_spec，并补充 `quote_kind: competitor_reference`、site_id、checked_at。历史来源日期、非实时/非结账、免费静图与成片区别、真实供应商成本待核均有明确说明。

## 四站价格与“免费”口径复核

| 站点 | 价格证据与边界 | 免费口径 |
|---|---|---|
| 03 RapReel | 上述 8/12/15 秒一次性成片套餐；币种有 JSON-LD 支持；未验证实付、税费或生成 | 免费静态舞台预览，不能说免费成片。见 [价格快照](../research/evidence/03/pricing.txt)。 |
| 01 RapVideoGenerator | 首页 Starter 逐月 US$19.99；年付标示 US$9.99/月，是年付折月而非逐月收费。600-credit 包 US$9.99，10 秒/720p 为 200 credits；不能把包价直接当单条价，也不能跨站换算。见 [首页快照](../research/evidence/01/home-jina.txt)、[价格快照](../research/evidence/01/pricing-jina.txt)。 | 一次注册赠送 10 credits 可制作 30 秒双版本歌曲；视频最低 100 credits，赠送额不等于免费视频。 |
| 06 Airapvid | Light $29.90/月含 200 credits；标准 Mini 720p/12 秒 10 credits。首次限定 Mini 480p 约 12 秒试用为 $1.29/5 credits；$9.99/12-credit 包与同价 Ultra 单条成片交付不同。首页旧计价/模型存在冲突，不能拼成可靠统一报价。见 [06 条目](../research/sites/06.json)、[价格快照](../research/evidence/06/pricing-jina.txt)。 | 欢迎赠送 20 credits；价格页 FAQ 明确 Free 不支持视频；计算器的积分示例不能证明免费账户可生成视频。 |
| 12 AI-Rap.Video | 单次 $9.90/84 credits，最低配置约 1 条 12 秒/720p；Creator $19/月含 168 credits，不能把整月套餐标成单条价。证据币种写 `$`，本模块不擅自给它换成 USD 或转换成 RapReel 报价。见 [价格快照](../research/evidence/12/pricing.txt)、[12 条目](../research/sites/12.json)。 | [首页快照](../research/evidence/12/homepage.txt)明确注册不包含免费 credits。 |

01/06/12 只用于审计计价与免费边界，本模块未宣称支持它们的报价。各站 credits 的权益、模型和有效期不同，不能互换或相加；年付折月不能当月付，也不能直接当一次性生成成本。免费文本、歌曲、静图或欢迎积分均不自动意味着免费说唱视频。

## 验证结果

- `python3 -m unittest discover -s tests/workbench -p 'test_quotes.py' -v`：6 项通过。覆盖全部三档、10 秒等不匹配规格、未支持画幅/站点、类型/字段拒绝、JSON 严格序列化、输入不变和结果独立性。
- 新测试直接启动当前真实 `make_server`，使用本地 TCP HTTPConnection 调用 `/api/quote`，没有模拟 quote 模块或 HTTP 路由；核验三档 200、无匹配 200/null、错误字段/类型 400 与 wire 响应结构。
- `python3 -m unittest discover -s tests/workbench -v`：29 项通过，含既有 brief、catalog、evidence、server 与新增 quote 测试。

本次改动仅 `rap_workbench/quotes.py`、`tests/workbench/test_quotes.py` 与本 review 文档。没有改 server、研究记录或前端。
