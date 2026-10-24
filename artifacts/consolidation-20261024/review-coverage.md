# 合并覆盖审查（只读）

2026-10-24。仅检查本地三份飞书原文快照、legacy-entries.json、research/sites/*.json 和现有官方证据；未改产品代码、源文档、registry 或 goal，未联网或使用浏览器。原 YzO 总纲宜作为统一入口，另外两份保留为来源；本审查不写飞书。

## 数量与去重结论

| 范围 | 实际条目 / 唯一实体数 | 说明 |
|---|---:|---|
| 42 家详本 AQqCdG2Q3ogetUxgdFxcwKFgnah | 42 / 42 | 六类分别 12、8、10、4、6、2 |
| 总纲 YzORdyPJroCrXZxCoBKceiZ3nUb 的生态清单 | 43 / 43 | 六类分别 13、8、10、4、6、2；额外一条为 Manus AI Rap（manus.im） |
| 两份旧稿交集 / 并集 | 42 / 43 | 详本 42 项全部包含在总纲；无详本独有项 |
| 现有验证目录 | 46 | load_sites 验证通过；42 full_page、4 partial，并非 46 项生成效果实测 |
| 旧稿并集与验证目录重叠 | 11 | 包含 SyncLabs / Sync 实体别名；若只按域名原串比较会漏掉它而得到 10 |
| 旧稿补充候选 | 32 | 42 详本贡献 31 项，额外 Manus 贡献 1 项；均未因本次合并而取得独立核验资格 |
| 合并检索索引 | 78 | 46 + 32；应称“已建证据记录 46 项 + 待核线索 32 项”，不能称“已验证 78 站” |

已从原 HTML 的六个生态分类逐条独立计数，与 legacy-entries.json 的名称及顺序完全一致；不能用全文所有链接、所有列表项或标题数字直接计数。source-46-research.json 的逐站 h2 实际为 01–46 共 46 条，与目录一致。

去重规则：普通站点统一主机名大小写、www 与结尾斜杠；GitHub 按 owner/repo 去重，不能把整个 github.com 算一项。补充的 32 项中有 11 个不同 GitHub 仓库和 21 个其他项目/站点线索；“Hallo / Hallo2”和“Wav2Lip / Wav2Lip-HD”各只有一个给定仓库链接，现按各一条，不据名字拆成多个项目，也不宣称仓库已包含全部派生版本。

## 重叠 11 项

Freebeat→18、Neural Frames→19、BeatViz→20、Kaiber→23、DomoAI→25、Hedra→26、SyncLabs→Sync/28、RunwayML→Runway/29、Kling AI→30、Suno AI→Suno/34、Udio→35。保留旧稿名称/原链接作检索别名，事实、价格、免费及 API 边界优先引用当前目录相应条目的日期与来源，不沿用旧稿效果形容词。

Sync 别名依据：research/evidence/28/introduction.txt 来自 https://sync.so/docs/introduction，正文自称“Sync Labs”；research/sites/28.json 将其作为官方文档来源。由此可将旧稿名 SyncLabs 与当前 Sync 产品实体合并；本次没有验证 synclabs.so 的当前重定向或域名归属，不应写成已验证的域名迁移事实。该官方正文也含效果宣传，不能据此认定“完美/工业级/实时”性能已测。

## 32 项候选的中性用途摘要

以下用途仅是依据旧稿分类整理的后续核查方向，**均未独立核验**；不构成当前产品功能、可用性、API、价格或商用许可确认。

| 后续核查方向 | 候选（数量） | 建议中性摘要 |
|---|---|---|
| 音乐、伴奏与歌词工作流 | Rapchat、LyricStudio、Soundverse AI、Neume AI、Boomy、Soundful、Loudly、Beatoven.ai、Somio AI（9） | 可进一步核查音乐/伴奏生成、歌词辅助或录制编辑环节；Neume、Somio 的当前产品身份与定位也需重新确认。 |
| 通用创作自动化线索 | Manus AI Rap / manus.im（1） | 旧稿另列的创作工作流自动化候选；尚不能确认它是独立 Rap 人声或伴奏生成产品。 |
| 声音合成、转换与分离 | ACE Studio、DiffSinger、GPT-SoVITS、RVC、Kits.ai、Weights.gg、Uberduck、UVR5（8） | 可进一步核查歌声合成、声音转换、音色资源或人声/伴奏分离用途；训练/克隆同意、代码与模型权重许可须分别核对。 |
| 人像/人物音频驱动研究线索 | LivePortrait、EchoMimic、OmniHuman、EMO、Hallo / Hallo2、AniPortrait、SadTalker、Wav2Lip / Wav2Lip-HD（8） | 可进一步核查音频驱动人像或人物动作迁移方案；不预设快速 Rap、140 BPM、遮挡和高画质效果成立。 |
| 动作引导线索 | Viggle AI、MimicMotion、Champ（3） | 可进一步核查参考动作或姿态引导；不宣称解决所有遮挡、服饰动力学或“完美动作复刻”。 |
| 音乐视觉与分镜线索 | Noisee.ai、AirMusic、Atlabs（3） | 可进一步核查音乐可视化、歌词画面组织或分镜辅助；自动卡点、语义理解、第三方链接支持及发布能力均待核。 |

上述 32 项的原始链接均在 legacy-entries.json 中，可原样保留为“旧稿提供链接”，不需要在本次合并中把访问/许可待核项改写成已确认产品。GitHub 11 仓库为 DiffSinger、GPT-SoVITS、RVC、LivePortrait、EchoMimic、Hallo、AniPortrait、SadTalker、Wav2Lip、MimicMotion、Champ，必须各自保留 repo 路径。

## 合并表述边界

- 建议入口摘要：“合并两份历史生态资料、46 项带出处研究记录，以及本地工程验收状态。旧稿共 43 个不同实体，其中 11 个与现有研究重叠，另有 32 个待核候选；所有官网宣称、旧稿观点、工程测试和真实生成效果分开标注。”
- source-46-research.json 记载 529 项测试通过（441 引擎、88 工作台；另有子测试记录），仅引用为对应本地版本的已记载测试证据；本次未重跑。公开 repo/commit 4e37d76 是历史源码锚点，不能把之后本地 529 项结果或新能力自动归到该历史公开提交，更不能暗示已推送代码。
- 旧总纲的 162 passed、140+ BPM 防抖、完美卡点、工业级、广播级、100% 动作保留、开源免费/可商用等，需要标为历史表述或改成中性待核内容，不能当作本轮实测事实。开源代码存在不等于模型权重或商业使用无条件授权。
- 本地程序化预览、已验证的合成/字幕边界不等于生成了 AI 人声、人物动画或验证了口型质量。原 C44/C45 真实 UI 验收阻塞，以及真实供应商质量/成本门槛继续保留；本次文档合并不能关闭它们。
