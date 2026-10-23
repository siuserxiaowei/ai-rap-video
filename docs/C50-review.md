# C50 / 50 独立终审记录

日期：2026-10-24。结论：本地研究与 brief 工作台已有可运行实现和自动化证据；真实供应商、桌面/390px 交互及飞书创建回读仍有未关闭项，不能标记整体目标完成。本轮只改 `README.md`、`WORKBENCH.md` 和本文，没有修改研究原始文件、业务代码或 `airap`。

## 范围和证据

已读 `PLAN.md`、`COMPLETION_AUDIT.md`、`WORKBENCH_SPEC.md`、完整研究契约、C41–C49 review、`rap_workbench/`、`web/`、50 项决策，以及 Gemini summary 和原 G50 补充分析。研究复核仅读取仓库归档正文，不声称本轮重新联网、登录、上传素材、付费或提交生成。C48 集成基线为 `5530a0f`，C49 最终集成基线为 `087248b`；本轮在后者独立复跑完整测试。

| 验收事项 | 本轮证据与结论 |
| --- | --- |
| 样本数量与 schema | `load_sites(Path('.'))` 成功：46 个不同主域，42 full_page、4 partial；全部来源路径由 catalog 校验存在且在仓库内 |
| 部分读取 | 15 Musicful、30 Kling、32 Pika、36 FineShare Singify，保留关键资料缺口，不按42个完整产品实测计数 |
| 分类与 API | Rap 19、music_video 11、video 6、lip_sync 4、music 3、editor 3；documented 17、not_found 29；API 资料不代表完整 Rap 流程 |
| 50 项决策 | D01–D50 唯一，所有 `evidence_site_ids` 均对应现存记录；50 条状态仍全为 planned。引用存在不能证明因果、用户需求或实现已验收 |
| 50 Gemini | summary 的 attempted/accepted/unique 均为50；逐份G01–G50复数得到50 accepted、50个returncode=0、50个SUCCESS和50唯一conversation_id，并有50份原始stdout文件；最终计账仍由主线程复查 |
| G50 补充 | `same_conversation=true`，不额外计为独立会话；共享来源上的独立分析不等于独立外部证据 |
| 50 Codex | 本轮 C50 交付前台账尚未完整；主线程须按C01–C50真实调用、完成、部分与完整验收分别审计，不按文件数宣布全通过 |
| brief / job | SQLite 持久化与 HTTP 往返已有自动化覆盖；文字任务结果为 `is_generated_video=false`，无媒体URL，provider_render 明确503 |
| 价格 | 03 RapReel 历史精确规格匹配；9:16 竖屏映射明示推断；未知不补0，免费静图不算成片，非供应商实时价格 |
| 导出 | C48 JSON保留原记录，CSV保留嵌套字段并中和公式，Markdown完整保留来源、限制、推断与决策状态；C49集成后的真实HTTP及数据往返测试通过，浏览器下载仍未验证 |
| 界面 | 原生DOM/textContent、显式标签、focus样式与窄屏CSS可静态检查；真实浏览器验收未完成，不能写无障碍/390px全通过 |
| airap | 保留外部并行开发的模块和命令，删除“工业级”“极速”“毫秒级”等未经本轮证明的表述；未审计其实现或生成能力，测试由主线程承担 |
| 飞书 | 主线程负责原生创建与回读；本轮没有可验证远端URL，不编造链接或发布成功 |

## 五站 API、下载与上线状态复核

以下以2026-10-23/24归档为准，均没有实际生成、下载媒体或验证商用权限：

| 站点 | 可追溯证据 | 终审结论 |
| --- | --- | --- |
| 08 Media.io | `research/sites/08.json`；`research/evidence/08/developer-jina.txt`、`rap-product-jina.txt` | 官方开发平台存在；本次只取得平台介绍，未取得可复用鉴权/请求schema/Rap端点，not_found不能改成无API。专题为条件式模型工作流，不能确定默认含音频/口型、实际导出或上线可用；5–10秒与9:16是示例建议 |
| 26 Hedra | `research/sites/26.json`；`research/evidence/26/quickstart.txt`、`generate-video.txt` | v3异步API、模型schema与estimate有明确文档；API预付美元钱包与Studio credits分开。下载URL是文档流程宣称，未实际调用。不得套用旧Character模型与旧订阅；720p/4秒为Veo示例，Avatar/中文Rap/最大时长仍待核 |
| 32 Pika | `research/sites/32.json`；`research/evidence/32/api-llms.txt`、`kling-lipsync.txt`、`pikaformance-login.txt` | documented针对公开多模型资料与Kling Lipsync；后者明确需video_url/audio_url并输出MP4。不能等同Pikaformance API。Pikaformance登录门及猜测路径404不能确认talk/sing/rap或当前可用。网页与API credits不通用，modality标签与必填字段矛盾仍保留；此站partial |
| 35 Udio | `research/sites/35.json`；`research/evidence/35/downloads.txt`、`api.txt`、`terms.txt` | 官方帮助快照明确audio/video/stems下载停用，不能沿用旧MP3/WAV/分轨能力；站内分享不是文件下载。官方public API帮助页称目前不提供公开API。条款正文缺失，商用许可与权属待核；不能作为已验证外部MV音轨源 |
| 42 HotelLobby.net | `research/sites/42.json`；`research/evidence/42/home.txt` FAQ | 首页展示MP4/预览/计价，但FAQ称规格、队列、失败计费、保存期将在generation opens前公布。结论应为规划/供应商宣称、上线可用性待核；不能据页面确定已上线或确定未正式开放。没有定位公开API文档；原曲及自带音轨授权待核 |

## 报告与推断隔离

工作台详情及C48导出将 `best_for/observations` 标为研究判断，保留 `limitations` 和 API 原始说明，不把官方营销当实测。本轮没有用 Gemini 补充输出覆盖站点事实。

`supplemental-G50.json` 的“41、43–46功能已开放使用”“42尚未正式开放”超出只读证据；46还将2000 credits/月写出美元符号，现金价格实际上未确认。“涉嫌诱导”“留存受损”等也是没有用户数据的分析推断。只能采用C42逐条核对后的JSON，不直接当作已证实事实、价格或质量评分。

初读 `scripts/build_feishu_report.py`（C48基线）发现：Codex只计文件数、Gemini只筛accepted、verification只查非空，标题固定100个agent任务；逐站limitations/API被截短，可能损失限制。`best_for`原文也应明确标分析。已交主线程修复发布门槛和完整限制呈现；本轮按文件边界不改脚本。最终发布前必须核查修复版输出，不能让“报告可生成”替代真实任务/页面/回读验收。

## 实跑检查

- `4d36025` 基线：`python3 -m unittest discover -s tests/workbench -p 'test_*.py' -v`，37项通过，耗时4.918秒。
- 合入C48的 `5530a0f` 基线：相同完整命令43项通过，耗时5.611秒。
- 合入C49的 `087248b` 基线：相同完整命令54项通过，耗时7.422秒，exit code 0，无失败、错误或跳过。实际环境为Python 3.9.6、Node v26.8.1；运行说明沿模块契约建议Python 3.10+。
- `node --check web/app.js`、`node --check web/create.js`、`git diff --check` 通过；C49新增静态集成测试也重新执行了两份JS语法检查。

54项检查包含真实临时HTTP服务的46站详情、筛选和统计、brief创建/GET/SQLite重开/服务重启、job幂等与503、价格有据或null、三种导出的MIME/attachment/长度/46站与50决策、CSV公式前缀、非法输入与静态路径边界。网络采集异常测试使用mock；前端测试是HTML解析和源代码规则检查，不执行页面。旧review数量不作为本轮通过证据。

浏览器CUA因当前页面访问策略被终止；本轮遵守限制，没有调用浏览器或替代工具绕过。桌面/390px布局、键盘弹窗焦点、筛选比较、照片选择、保存/重开及浏览器下载内容均未真实交互验证。静态代码与真实HTTP不能冒充上述检查通过。

## 未关闭事项与交接

1. 主线程完成其最终发布版本复测和C50接收后的50 Codex台账核对；C44/C45保留部分验收与视觉待做，未完整验收的worktree不能伪记已回收。
2. 在允许的页面访问环境完成桌面与390px实际视觉、键盘、照片、保存和下载验收，记录结果与失败修复。
3. 用当前正式文档实现一个真实provider，准备专用凭据和授权人物/音频样本，实测中文快Rap、双人/遮挡、人声与口型、媒体输出、耗时、费用和失败重试对账。原型规划或airap命令不能代替这一步。
4. 修复并核验原生飞书草稿，再由主线程创建一次、取得真实URL并回读标题、46站/42正文/4部分、来源链接、50决策、自动化结果与未关闭缺口。

本审查可作为范围清楚的文档交付验收；上述硬门槛未关闭前，整体goal继续保留未完成状态。
