# 统一总纲的能力与证据口径审查

2026-10-24，C50原agent只读复核；仅新增本文，不改产品代码、远端文档、registry或原验收状态。来源：旧`MASTER_FEISHU_DOC.md`、本目录三份source JSON、legacy条目表、当前airap代码与subtitle-burnin（phase4）verification。未联网、未运行UI/浏览器或重新生成媒体；不新增agent数。

## 审查基准

| 快照 | ID / revision | 应承担的作用 |
| --- | --- | --- |
| 原总纲 | YzORdyPJroCrXZxCoBKceiZ3nUb / 3 | 可更新为唯一入口；保留GitHub入口、模块导航和旧稿出处，不能沿用旧完成声明 |
| 42详本 | AQqCdG2Q3ogetUxgdFxcwKFgnah / 3 | 旧生态/开源候选与完整架构蓝图；不是本轮供应商效果实测 |
| 当前46站研究 | TiqGd7dHWoAqBex3KCvcnzpVnKc / 14 | 逐站来源、价格/API/限制、50决策、后续三轮验收及原生字幕样本图 |

已独立对照`docs/iterations/subtitle-burnin-20261024/verification.json`：其中8个受测代码/脚本SHA-256均匹配当前文件，final-tests日志SHA也匹配；日志末行为`529 passed, 393 subtests passed in 13.29s`。这是对应本地版本的自动化证据，不能改写成新跑一遍、GitHub CI通过、公开仓库已含相同代码或真实供应商效果通过。

## 必须修正的高风险声明

| 原声明或合并风险 | 合并后的准确口径 |
| --- | --- |
| “工业级/全自主/端到端AI说唱成片”“电影级”“开箱即用” | 当前为研究工作台＋本地程序化预览与字幕合成。真实AI人声、人物图片动画和口型未渲染；企业级可靠性、部署和生成质量未验收 |
| 旧“162/162全通过”作为当前总成绩 | 162是旧稿历史口径；最新529=引擎441＋工作台88，零失败/错误/跳过。393内部subtests另记，不相加成922；162、387、88、103等历史/子集不可再次累计 |
| “140+ BPM不崩塌/极速精确口型/实时低延迟”“完美卡点”“毫秒级重拍裁切” | 未做真实快Rap/多人/遮挡质量或吞吐延迟基准。当前头像是mock状态数据，没有进最终视频；真实切点样本为24fps第6帧/0.25秒，任意切点受FPS量化。毫秒/厘秒是参数表示，不是实测音画精度 |
| “音素强制对齐”“绝对纯净干音/完整UVR5分离” | `RuleBasedAligner`依据歌词、总时长和beat grid估计时序，不能当作读取真实音频的强制对齐。MockStemSeparator是频带滤波；Demucs/UVR5 wrapper可回退mock，存在适配器不证明真实模型已安装或分离质量已验收 |
| “已用角色图/一致性LoRA/全身动作/主题场景生成” | pipeline明确拒绝character image，`theme_applied=false`，视觉为procedural_placeholder；角色、LoRA、姿态/人物渲染列为后续规划 |
| 4K成片、长曲稳定性、任意模型上限 | 白板E4的4K保留为待验证目标。当前本地CLI实测1080×1920和1920×1080、30fps短样本；不能外推4K或完整3–4分钟成片。代码120秒预算上限也不等于全部120秒质量/压力测试已通过 |
| “实际中文字幕通过”外推全字体/所有帧/网页验收 | phase4受控样本0.1/0.5/0.9秒差异像素为0/2996/0；3张选定媒体帧可辨“中文烧录预览”，4种全高清CLI样本完整解码。字体family仍只是请求，实际font face未独立核验；这些视频帧不能关闭C44/C45网页门槛 |
| “开源免费/零API成本/全商用/合法所有音色/版权无忧”“16GB显存即可工业部署” | 保留旧稿商业/许可段为待核线索；代码、权重、训练数据、声音/肖像、伴奏权利及套餐权利分别核查。无API调用费不等于GPU/存储/运维零成本，显存需求须按模型/精度/长度实测；未做本轮法律或商业保证 |
| “已有Sync SDK/API即已接通生成”“估价可硬控成本” | Sync客户端/持久化journal/本地plan-show与门禁GET refresh仅合同测试；CLI无submit，生产provider_render仍503。真实供应商请求/付费生成均0，未验证实际媒体时长、账单、下载与质量；JSON/multipart文档差异仍保留 |
| “全部已推GitHub”“本地529即公开commit的成绩” | GitHub作为代码入口保留；本次不push，也不联网证明当前公开HEAD。历史公开源码锚点与之后本地受测commit/文件hash必须分开标注，不能声称最新工作台/字幕工具链均已同步公开仓库 |

旧42详本中的“全球领先/最大/顶尖/100%动作保留/完美分离/5秒高保真克隆/几分钟出片/3–4分钟角色不走形”等均没有本次独立样本，不可直接变成统一总纲的当前事实或排名。历史开源项目候选仍值得保留，正文应采用中性用途与待核项，而非删除所有内容或继续复制营销结论。

必须明确的已知冲突：旧Hedra Character-3/Studio价格不能覆盖当前26号的v3 API/独立预付钱包；旧Udio描述不能恢复当前35号记录中的audio/video/stems下载停用，也不能把链接分享当文件导出；34号Suno未找到官方公开API文档，不能用第三方接口补成官方；18号Freebeat的官方MCP入口不等于已取得可复制REST端点。其他重叠产品的功能/免费/价格也按本轮记录日期与来源保留边界。

## 不能丢失的42详本whiteboard

原节点`doxcnXi5NPWHxHnJJDktW2PyIFc`、token `Df8Hwq0f1hdRCcbfZHic1K3qnpb`、type=mermaid。它有5个子图、17个节点、6条模块依赖边；只抽取普通p/h/table会静默丢失这部分。统一稿应保留原白板内容或可复核的完整Mermaid/节点表，并标注“旧稿端到端目标蓝图，按下表区分当前与规划”。不能把旧节点ID/token直接当作新总纲中已创建的新画板实例。

| 原节点 | 必须保留的意图 | 当前标注 |
| --- | --- | --- |
| A1 | 主题/歌词提示词 | 本地文字输入；未做AI歌词生成 |
| A2 | 参考节拍（BPM/调性） | BPM参数/beat grid已有；不能声称已自动分析并应用调性 |
| A3 | 歌手形象Character Sheet | 待实现，当前人物图片输入拒绝 |
| B1 | Lyrics & Flow结构化生成、Rhyme/Syllable/Bars | 本地分析/分小节调度已有；生成新词为规划 |
| B2 | Rap伴奏生成/分轨加载，808/Snare/Hi-hat | 合成器乐节拍或提供本地音频已有；专业音乐生成/分轨质量待测 |
| B3 | 说唱人声合成与克隆，SVS/Flow-Guided TTS | 未接入、未生成 |
| B4 | UVR5干音分离＋Beat/Onset | 数值与mock/适配层不能当真实UVR5已测 |
| C1 | Multi-View Character LoRA一致性 | 规划，未训练/渲染 |
| C2 | 每bar自动分镜脚本/Scene Prompts | brief/模板分镜与cut调度已有；语义生成及画面执行待做 |
| C3 | Street/Stage/Cyberpunk背景与B-roll生成 | 当前程序化占位，theme未应用 |
| D1 | Vocal Stem音素→视素对齐 | 规则估计与规划数据；真实音频强制对齐未测 |
| D2 | LivePortrait/EchoMimic/Wav2Lip快节奏口型 | 规划；mock不能称实际口型视频 |
| D3 | Pose/Motion Guidance台风插帧 | 规划；点头数学状态不是已渲染人物 |
| E1 | Beat Grid重拍裁切拼接 | 本地trim/concat与实测帧切点已有；毫秒级精度未证 |
| E2 | Shake/Glitch/Zoom动效 | 本地滤镜调度已有；主观音画质量未证明 |
| E3 | Kinetic Typography | ASS/SRT及选定中文烧录样本有实证；不是ASR或真实演唱逐字同步验收 |
| E4 | 4K/9:16/16:9最终导出 | 两种全高清方向已测；4K保留目标/待核 |

6条原依赖边全部保留：Input→AudioEngine、Input→VisualEngine、AudioEngine→LipSyncMotion、VisualEngine→LipSyncMotion、AudioEngine→PostProduction、LipSyncMotion→PostProduction。原图没有细画节点间边，不应捏造成已有运行依赖或悄悄删掉尚未实现模块。

## 简洁合并覆盖清单

1. 统一入口继续用YzOR原ID；回链42详本、46站revision14与GitHub，不新建重复报告，不声称本次推送代码。保留两种组织方式（端到端平台/模块化工坊）的产品分析和六类生态框架，但去掉“已成熟行业定论”与效果排名语气。
2. 旧总纲实际43项，42详本42项，差异为Manus AI Rap。旧稿线索、原URL、名称别名及11个独立GitHub仓库不能丢；GitHub按owner/repo保留，不能用github.com主域合并掉全部项目。Manus、Neume、Somio等当前产品身份/定位不因被旧稿列出就获证实。
3. 当前数量固定为46个有结构化证据的不同主域：42全文、4部分（15/30/32/36）。旧43资源与之精确URL主域匹配10项；本地28号官方introduction自称“Sync Labs”，可额外合并SyncLabs/Sync产品别名，因此与coverage审查一致为11个重叠、32个待核线索。synclabs.so域名重定向/归属本轮未验证。若显示78项索引，必须同时写46条有证记录＋32待核候选，不能称已验证78站；两个“42”也不可混淆或相加。
4. 完整保留46站逐条出处、checked_at、证据等级、免费/付费/API及限制；不让旧稿一句话结论覆盖原记录。保留50决策与当前状态：36 verified、10 implemented_pending_browser、2 planned_next_stage、1 partially_implemented_live_pending、1 implemented_contract_tested_live_pending，不能把“50轮”写成50项都已实现。
5. 保留本地工作台、预览CLI、Sync合同工具、字幕toolchain复现入口与phase4证据链接；明确默认FFmpeg仍不含ASS，项目内构建需显式选择。`generate`是preview兼容别名，优先展示preview/lyrics-file、模式与二进制参数；不要继续称“一键AI说唱MV”。标准库说明仅适用于工作台，不能掩盖引擎的FFmpeg/FFprobe/libass前置条件。
6. 保留42详本17节点白板、技术矩阵的取舍意图、旧总纲模块和历史162记录、46站文件中的88合同→387预览→529字幕演进，以及原生字幕图。最新图tag是`img`（src=OtYwblJK3oepYoxxV5ucUBBxn9g），仅查`image`标签会漏掉；不能把含6字的选定视频样本变成网页截图验收。跨文档图片要实际插入/回读，不能把源token字样当新目标已展示。
7. 醒目保留：50个Codex已交付、48完整验收、C44/C45真实桌面/390px/键盘/浏览器下载未过；50个独立Gemini会话，复用C48–C50和同G50补充不加数量。真实provider/授权样本/质量/成本仍待，overall goal未完成。

生成consolidated-master.xml后的最小复核：46站标题、50决策、32条候选及原链接、17节点/6边/5子图、三源回链、原生图片与关键source URL均可找到；最新529及历史测试标注不混算；全文检索4K/工业级/实时/完美/100%/零成本/全量推送，逐处确认已降为历史/规划/待核或有对应证据。最终远端创建/更新和回读由root执行，本文没有远端发布结论。
