# C46：任务持久化与供应商边界

本轮只实现本地分镜参数任务。`brief_preview` 完成的是可下载 JSON 计划：三段时间连续、时长合计等于 brief 时长，保留规范化参数及用户歌词。结果明确 `is_generated_video=false`，不含媒体 URL、生成音频或假进度。

`JobStore` 使用标准库 SQLite，连接按操作关闭。幂等键有 UNIQUE 约束，`BEGIN IMMEDIATE` 把读取、比较规范化请求和插入放入同一事务；跨线程、不同实例、进程重开使用相同数据库时均不依赖内存状态。相同 key 和相同规范化输入复用任务；不同输入抛 `IdempotencyConflict`。省略 key 的请求各建任务。key 只标识请求，不属于规范输入。

`provider_render` 当前总是抛 `ProviderUnavailable`，由现有服务器映射为 503；事务回滚，不留假任务、不消耗 key、不提交扣款。没有读取任何密钥、上传人物素材或调用付费 API。供应商模块只定义失败边界；未从研究中的旧参数推测真实 API。

## 失败与计费复核

- [RapVideoGenerator 研究 01](../research/sites/01.json)：官网声称失败视频自动退积分；音乐和视频分步计费，画质决定每秒积分。研究未实测，因此本地任务不能套用其退款承诺，也不能把歌曲成功等同于视频交付。
- [RapReel 研究 03](../research/sites/03.json)：免费静图与按条付费成片分开；成功交付后风格不满意通常不退款，缺陷或账单争议需审核。分镜预览应有独立类型，不能显示已购买成片或保证退款。
- [Sync 研究 28](../research/sites/28.json)：口型同步依赖现有音频和视频/图片，不负责原创歌曲；异步状态包含 COMPLETED、FAILED、REJECTED，费用依模型、帧数和订阅变化。未来 adapter 需记录供应商任务 ID、提交状态、成本依据和失败原因，并基于正式文档核对 webhook、取消、重试及账单核对规则。当前 brief 的时长/画质不足以构成真实提交或报价。

未来付费适配器须在持久化请求身份后提交，并处理“供应商已接收、本地未确认”的重试窗口；不能简单把网络超时当成未扣款再提交。本轮没有开放这样的提交路径，也不虚构状态流转。

## 验证

`python3 -m unittest discover -s tests/workbench -p 'test_jobs.py' -v` 覆盖三种时长、参数保真、无媒体标记、规范化幂等、冲突、8 个并发重试、持久化重开、无 key、非法字段、未接入供应商及真实 HTTP 201/200/409/503/400 与 GET 往返。

执行结果：任务测试 8/8 通过；`python3 -m unittest discover -s tests/workbench -v` 全部 31/31 通过（含既有 brief、catalog、evidence、server 回归）。
