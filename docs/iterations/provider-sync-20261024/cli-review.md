# C50 复用迭代：Sync 本地准备与观察 CLI

日期：2026-10-24。本轮复用原 C50，不新增 Codex/Gemini 任务数，不覆盖第一次 C50 验收。仅修改 `rap_workbench/provider_cli.py`、`tests/workbench/test_provider_cli.py` 和本文。没有调用浏览器、真实 Sync API、付费生成或真人素材；工作台生产 `provider_render` 继续由原边界返回 503。

## 使用与持久化边界

从仓库根目录运行；默认 journal 为 `.workbench/provider-submissions.sqlite3`，可逐条命令用 `--journal PATH` 指定本地文件。

```bash
python3 -m rap_workbench.provider_cli plan --manifest /path/to/manifest.json
python3 -m rap_workbench.provider_cli show --id LOCAL_UUID
python3 -m rap_workbench.provider_cli refresh --id LOCAL_UUID --allow-network
```

manifest 只接受 `visual_type`（image/video）、`visual_url`、`audio_url`、可选 `model`（仅sync-3）、`output_file_name`、`idempotency_key`。媒体 URL 必须通过客户端的 HTTPS、无用户密码、无本地/private literal IP 检查；不在 CLI 获取媒体。JSON 文件上限64KiB，拒绝非对象、未知字段（含api_key/headers/凭据）、重复JSON键、非有限常数、无效UTF-8和孤立代理码。错误输出不回显输入值、文件路径或第三方异常。

`plan` 只构建经过校验的请求并执行 `SubmissionStore.prepare`。它不建立 SyncClient、不估价、不提交远端任务，也不发送计费请求。先保存键、原请求及指纹，再输出本地编号、键、指纹、模型/输入类型和固定目标端点，以及明确的“本地保存，未生成/未提交计费”标记。媒体URL、签名query和文件名不会输出。没有提供键时生成UUID并随请求保存在磁盘；要恢复该动作应使用 `show` 或原键，不要把再次无键 plan 当作原动作恢复。

`show` 从本地journal白名单显示安全metadata与 `has_output`，不输出原请求、事件原文或实际output URL。`refresh` 必须同时具备 `--allow-network`、已保存remote id、`RAP_ENABLE_SYNC_CLIENT=1`和非空`SYNC_API_KEY`；缺任一前提都在构建客户端前失败。随后仅 `SyncClient.from_env().get(remote_id)`，从不调用create/submit，也不提供submit子命令。API key只从指定环境变量读取，不检查其他凭据存储；输出层额外遮盖与该key相同的字符串，防止误把key作为动作键输出。

刷新成功将已规范化快照交journal应用，遵循其终态与防倒退规则。GET异常只记录观察错误，不推断远端失败，不改变未知/活动任务的原动作身份，不新建键、不重试提交。COMPLETED无输出仍为 `has_output=false`；看到output URL只表示有输出引用，CLI从不下载媒体，响应明确 `output_downloaded=false`。本地journal私下保存原始签名URL，因此应限制该SQLite文件及备份的访问；不通过网页暴露。

## 官方归档复核

完整读取迭代 `PLAN.md` 和 `research/providers/sync/20261024/idempotency.txt`，检查公开 `public-openapi.json`、quickstart/create/get/estimate相关schema；重新计算manifest中7份来源的字节数与SHA-256，全部吻合。公开OpenAPI为3.1.0，共27个路径；本轮遵循公开的 `/v2/generate`、`/v2/generate/{id}`、`/v2/generations/estimate`，没有使用更大根OpenAPI中的未公开路径。CLI本身只有本地操作和已有任务GET。

幂等合同规定键1–128字符、`[A-Za-z0-9._~-]+`，首次发送前保存，201为首次接受、200为重放，重放并不等于完成。JSON对象键序不影响等价性，但数组顺序和URL完整字符串（包括签名query）影响；更换签名URL不能悄悄复用旧动作。官方保护期为接受后七天，活动/未知时更久；本地CLI不自动删除journal，也不因超时换键或绕过未知提交。CLI没有提交入口，未来的实际提交方仍须正确实现这些规则。

文档差异：quickstart明确给出sync-3 image+audio的JSON创建示例，`common_CreateGenerationDto`也有JSON字段模型；公共路径 `/v2/generate` 的requestBody主要声明multipart/form-data文件上传。本轮按已给定接口准备最小JSON模型，不实现上传、TTS、webhook、batch、segments或其他猜测字段；live接受该JSON请求仍待实际供应商验证。

estimate端点声明只根据提供的model/duration/fps/reasoningEnabled估算，既不获取媒体，也不创建generation，结果为USD等字段；未经真实素材时长、帧率和计费规则核实，不能把估价当硬预算保障。CLI不提供估价或提交命令，本轮未测任何真实扣款、成本、音画质量、授权或媒体下载。

## 验证记录

客户端/journal并行实现时只做语法与schema检查，未伪造核心import、skip或将待测写成通过。合入main `26d9eb9`（实际客户端与journal）后运行CLI专项及全套；再合入 `78b6ae7`（root真实本机HTTP契约测试）后，最终完整复跑结果如下，均exit code 0：

| 命令与基线 | 实际结果 |
| --- | --- |
| `python3 -m unittest discover -s tests/workbench -p 'test_provider_cli.py' -v`，26d9eb9 + 本轮CLI | 11项通过，0.706秒，无失败/错误/跳过 |
| `python3 -m unittest discover -s tests/workbench -p 'test_*.py' -v`，26d9eb9 + 本轮CLI | 86项通过，8.050秒，无失败/错误/跳过 |
| 相同完整命令，78b6ae7 + 本轮CLI | **88项通过，12.691秒，无失败/错误/跳过**；包含root新增的2项localhost联合契约测试 |
| `python3 -m py_compile rap_workbench/provider_cli.py tests/workbench/test_provider_cli.py` | 通过 |
| `git diff --check` | 通过 |
| 归档manifest校验 | 7份来源bytes/SHA-256全部吻合；public OpenAPI为27路径，JSON/multipart差异确实存在 |
| CLI AST调用审查 | 无create/submit/estimate或mark_submitting/record_acceptance/record_submission_unknown调用，仅本地prepare和GET观察相关操作 |

测试使用dummy key、本地临时SQLite、内存transport和localhost服务器；包括实际 `python -m rap_workbench.provider_cli` 子进程的plan/show跨进程回读。未使用真实密钥、付费网络或供应商生成结果。原 `provider_render` 503 回归也在88项集合中重新通过；有REST客户端代码并不等于生产生成链路已接通。

新增CLI检查覆盖：本地plan/show持久化和同键恢复、签名URL改变导致冲突、生成键后回读、过大/非法/含凭据manifest、signed输出遮盖、显式flag/gate/key/remoteid缺失不构建client、注入dummy transport的GET-only状态观察、终态不倒退、未知提交GET超时保留身份、完成无输出、拒绝submit/敏感argv、实际模块CLI进程重启。

未关闭：真实Sync凭据和授权人物/音频素材未提供，live JSON/multipart兼容、实际计费时长/成本、生成质量与媒体下载未验证；桌面/390px浏览器验收仍blocked。root须在接收本CLI后核对最终提交版本，并完成同一飞书文档更新与回读。localhost契约fixture不证明供应商生成或整体goal完成。
