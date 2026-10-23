# Sync 客户端迭代复核（C48 复用）

2026-10-24。读取本迭代 PLAN 和 `research/providers/sync/20261024/` 已归档 quickstart、overview、create、get、estimate、idempotency 以及仅含 27 条公开路径的 `public-openapi.json`。没有读取根目录大 OpenAPI。只修改客户端、专项测试和本文；原 50 任务台账与工作台 `provider_render` 503 行为不变。

实现 `build_generation_request`、`validate_generation_request`、`normalize_generation`、`SyncClient.create/get/estimate/from_env`。只发送固定 `https://api.sync.so` 的三个合同路径；只接受 sync-3、恰好一项 image/video URL 和一项 audio URL，以及可选 outputFileName。拒绝额外字段、上传/TTS/其他模型。URL 字符串和输入数组顺序保持原样，返回独立副本。HTTPS 校验拒绝凭据、localhost、私网 literal IP、异常端口、控制字符和非规范数字地址；不解析 DNS 或抓取媒体，因此不声称验证远端媒体可达性或实际时长。

JSON 创建的文档差异：公开路径主要列 multipart，而 quickstart 图片示例与 common_CreateGenerationDto 明示本文使用的 JSON 格式；实现仅采用该明确子集。REST 请求和响应使用 camelCase，归一化快照采用约定 snake_case。五状态全部保留，COMPLETED 缺少 outputUrl 时 output_available=false，不构造下载地址。remote id 按协调后的 1–128 ASCII `[A-Za-z0-9._~-]+` opaque token，排除单独 `.`/`..`，不强加 UUID 或首字符规则。

所有 create 调用必须提供合法持久化 Idempotency-Key；重试前只序列化一次，始终重用同一个 key 和相同字节。最多 1–5 次尝试（默认 2），遵循有界 Retry-After；过长等待交还调用者，不提前重试。401 与冲突不重试；IDEMPOTENCY_IN_PROGRESS、429、部分暂时 HTTP 错误可有限重试。超时、未知接受结果和已知 remote id 保留为安全诊断，后续错误不会将曾经不确定的提交误判为确定拒绝。GET 失败只重试 GET，绝不转 POST 或生成新 key。

根据 root 后续澄清，estimate 不发送自造 Idempotency-Key：官方幂等承诺只适用于 create。估价是费用查询，可有限重试，不创建生成任务，也不构成真实预算保证。数值必须有限，duration/fps 必须正数，费用及帧数非负，estimatedCredits 可为 null。拒绝布尔伪数字、NaN/Infinity/溢出浮点、缺字段；返回三个文档规定 camelCase 字段，不附加虚构价格或媒体时长。

默认 allow_live=false，在调用 transport 前失败；from_env 只读取 RAP_ENABLE_SYNC_CLIENT 和 SYNC_API_KEY，必须同时显式满足门禁。没有探查其他密钥存储。默认 urllib 禁止重定向与环境代理，不将认证头带往 Location。读取上限 1 MiB，JSON 拒绝重复键、无效 UTF-8/代理码点、非有限数、非对象及超长数字词法；数字转换在 Python 3.9 也有显式 128 字符上限。

异常仅包含 http_status/code/generation_id/outcome_unknown/retry_after 等安全诊断，忽略供应商 message/error、原始 body 和签名 URL；已知 API key 出现在机器码或 ID 时脱敏或抛泛化错误。transport 原异常不通过 str/repr 回显。客户端不持久化操作，key 保留与恢复由 C49 journal 实现；调用者必须在 create 前持久化 key/payload，七天或更长的活动/未决保留由该层承接。

验证：`python3 -m unittest discover -s tests/workbench -p test_sync_provider.py -v`，11 项通过。使用虚构 key 和本机内存 fixtures，涵盖 payload 副本与顺序、URL/ID/key 拒绝、默认门禁、稳定重试、201/200 replay、五状态与缺输出、未知结果 remote id、401/409/429、GET 不产生 POST、估价字段与非有限数、无效/超大 JSON、数字转换上限、key 脱敏、默认 urllib 重定向拒绝与读取上限。

全工作台回归 `python3 -m unittest discover -s tests/workbench -v`：65 项通过（原 54 项 + 本次 11 项）。以上为离线合同测试，不是供应商质量/费用测试。没有实际供应商请求、付费、媒体下载、浏览器访问或已生成视频；真实本机 HTTP 联合契约验证由 root 完成，供应商实测与浏览器验收仍待真实条件满足。
