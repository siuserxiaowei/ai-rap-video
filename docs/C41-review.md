# C41 catalog 与研究数据复核

复核日期：2026-10-23。范围：当前 worktree 的 `research/sites/*.json`，以及下列三个站点的公开正文。本轮没有注册、付费或提交生成。使用 agent-reach 的 Jina Reader 后端读取官网，完整返回暂存 `/tmp/c41-*`；按任务边界只提交本报告，不改研究记录或其他模块。

## 三站 API 与免费边界

| 站点 | 本轮官方来源 | 复核结论与证据差异 |
|---|---|---|
| 01 RapVideoGenerator | [首页](https://rapvideogenerator.com/)、[价格](https://rapvideogenerator.com/pricing) | 当前价格页确认一次性赠送 10 credits，可做 30 秒歌曲、两个版本；视频从 100 credits 起。因此“免费生成 Rap 视频”的泛化描述不成立，现有 JSON 的免费边界准确。本轮首页和价格正文未发现公开 API 或 developer 入口，维持 not_found；只代表检索范围内未发现，不能推断没有 API。订阅卡金额在抓取正文中的展示不完整，月付额度与结账仍待核。 |
| 23 Kaiber | [首页](https://kaiber.ai/)、[价格](https://kaiber.ai/pricing) | 现价页明确 5 美元／5 天，之后转 Creator，每账户一次；这是付费试用。Starter、Creator、Pro 当前月付 10／29／99 美元，与现有 JSON 一致；没有新证据支持免费层。本轮首页和价格正文未发现公开开发 API，维持 not_found。首页产品宣传不能替代实际生成效果证据。 |
| 28 Sync | [Introduction](https://docs.sync.so/introduction)、[Quickstart](https://docs.sync.so/quickstart) | 官方正文确认 API、Python／TypeScript SDK，documented 有据。Quickstart 免费账户每月 3 次、每次最多 20 秒，其中 sync-3 最多 1 次且最多 15 秒，与现有 JSON 一致。Introduction 只给总上限；若只看该页会漏掉模型限制。本轮读取使用 docs.sync.so，既存记录使用 sync.so/docs；是来源入口差异，未发现套餐事实冲突。价格仍须区别月订阅、模型逐帧用量与 25 FPS 的每秒折算，不把 $0.05／秒推广到 sync-3。本轮未重新取得结账价格。 |

新读取正文与现有记录没有必须更改的已证实事实冲突；主要差异是首页宣传、价格页和 Quickstart 的信息粒度不同。以上均为供应商公开陈述，未验证输出质量或实际可领取的免费权益。

## 校验与接口取舍

- `validate_site(record, root)` 成功原样返回 record；失败抛 `CatalogValidationError(ValueError)`，含字段位置。拒绝缺必填字段、类型错误、无效日期／枚举／URL、非有限或负金额，以及不可 JSON 序列化内容。
- 所有来源 `local_path` 必须是 repo 内已有普通文件的相对路径；解析符号链接后仍须处于 repo 内，拒绝绝对路径和目录逃逸。full_page 必须有至少一个非空、非已识别错误／登录页的 official、documentation 或 pricing 来源。此规则能拒绝明显错误页，不能自动证明内容真实或完整。
- API 只接受 documented、not_found、unknown。documented 必须给有效非空 HTTP(S) URL。当前 10、12、20、22 的 api.url 为 null；契约只要求包含 url、未规定未知链接必须空字符串，因此对 not_found／unknown 保留 null，不进行补链。缺少 url 键仍拒绝。
- credits 兼容数字及已有的周期说明字符串，例如 `1,000 / month`；不把这些文本转换为跨站可比较的积分。金额只接受有限非负数字。
- `load_sites(root)` 读取 repo 的 research/sites，并拒绝文件名与 id 不一致、重复编号或主域。`filter_sites` 以 Unicode casefold 搜索，类别、API、证据条件采用 AND；无效枚举筛选明确报错。
- `stats` 直接返回 wire 的 total、full_page、by_category、by_evidence、by_api、checked_at，按主域去重，重复输入取第一条。checked_at 为最新记录日期，空目录为 null。域名按最后两段及有限的常见多段公共后缀归一化，支持 www／子域去重；这是标准库内的有界近似，未携带完整公共后缀表。`example.ai` 和 `example.com` 分别计数。新增特殊公共后缀或租户域时需要补充规则。

## 验证

`python3 -m unittest discover -s tests/workbench -p test_catalog.py -v`

通过 8 项测试：真实目录动态载入、UTF-8 搜索／组合筛选／wire 统计、字段错误、缺失与越界／绝对／符号链接证据、错误页与 secondary-only 的 full_page 拒绝、主域重复、文件名与坏 JSON 诊断、数字价格与原始积分文本。真实目录测试比较实际 JSON 文件数量，不硬编码最终站点数或最低数量。
