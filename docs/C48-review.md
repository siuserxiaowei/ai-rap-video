# C48 来源支持的报告导出复核

完成时间：2026-10-24。实现仅使用 Python 标准库，修改范围为 `rap_workbench/exports.py`、`tests/workbench/test_exports.py` 和本文。

读取并遵循 `WORKBENCH_SPEC.md`、`API_WIRE_CONTRACT.md`、现有 `server.py` 和 `catalog.py`。沿用服务端现有 `/api/report` 路由，未修改 HTTP 实现。报告仅整理本地研究数据；没有联网、使用浏览器、注册、付款或运行真实生成。

## 格式与来源保留

- JSON：UTC `generated_at`、方法、统一研究限制和未经改写的 `sites` 原结构，包含未知值、空值及扩展字段。中文 UTF-8 可读。
- CSV：每站一条逻辑记录，记录数量动态；当前目录输出 46 条。包含生成日期、核查日期、证据等级、输入输出、功能、价格摘要、免费边界、原始套餐 JSON、API 状态及说明、限制、原始来源 JSON、来源 URL 和观察。列表及对象用 JSON 保留层次；标准库 CSV 负责逗号、换行和双引号转义。
- CSV 公式防护：若去除前置空白后以 `=`、`+`、`-`、`@` 开始，或直接以制表符/回车/换行开始，在整个原字符串前加单引号，不丢失原始空白。仅 CSV 的危险单元格作此安全转换；JSON 原记录保持不变。
- Markdown：中文摘要与研究范围、逐站全部功能/价格/输入输出/限制/来源，以及传入的全部决策。目前包含 46 站和 50 项决策。决策保留依据、验收条件和原始状态，附依据站点官网；引用站点不在当前范围时明确说明。未提供决策或空目录均可导出。
- 证据含义：官网宣称与研究推断显式标注；`full_page` 不代表生成实测。`not_found` 和 `unknown` 不会改写为“不提供 API”。缺失内容显示“未记录”，不推测免费、商业许可或 API 可用性。

## 两站抽查

01 RapVideoGenerator：检查 `research/sites/01.json` 与 `research/evidence/01/pricing-jina.txt`。证据正文明确注册赠送 10 credits、视频最低 100 credits，因此免费歌曲不能等同免费视频；10 秒 720p 视频需要 200 credits。导出保留逐月收费、年付折月价及全年积分一次发放的区别，套餐缺失额度不补值。API 保留 `not_found` 与“仅检查首页和价格页、不能据此认定无 API”。完整 JSON/CSV 来源及 Markdown 来源范围保留。

02 RapVideo.ai：检查 `research/sites/02.json` 与 `research/evidence/02/pricing.jina.txt`。免费条款明确两类模板各一次 2 秒预览、每 Google 账号一次、480p、有水印、仅站内；完整视频需积分。导出保留该限制，以及套餐金额来自价格页原始 HTML JSON-LD、未验证结账的说明。年度套餐金额按年总价保留，不转换单次价格或补充未知积分。API 保留 `not_found` 与“未专门 API 搜索，不能判断是否提供”。

这些抽查仅确认本地证据与导出语义一致，不构成当前官网或实际生成质量验证。

## 验证结果

`python3 -m unittest discover -s tests/workbench -p test_exports.py -v`：6 项通过。

验证 JSON 全量 46 条原结构往返；CSV 全部 46 条及嵌套套餐、来源和限制往返；中文、逗号、换行与引号；四类公式前缀及前置空白/制表符；API 未知和缺字段；空数据导出；Markdown 46 站与 50 决策完整性。

真实本地 HTTP 服务验证 `/api/report?format=json|csv|markdown`：全部 200，UTF-8 MIME 分别为 `application/json`、`text/csv`、`text/markdown`，下载 `Content-Disposition` 文件扩展名正确，`Content-Length` 与实际字节数一致，并解析校验响应数据。

`python3 -m unittest discover -s tests/workbench -v`：37 项通过。未调用实际浏览器，遵守本轮页面访问策略终止后的限制。
