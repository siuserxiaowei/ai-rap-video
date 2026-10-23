# C42 review — 2026-10-24

新增 41–46 六个域名的结构化研究、逐站笔记与公开首页正文/原始元数据。核查日期为上海时间 2026-10-24；快照 metadata 保留 2026-10-23T16:00–16:01 UTC 的实际采集时刻、字节数、SHA-256 和错误字段。六个首页均有产品相关有效正文，故为 full_page；此等级表示来源读取完整，不表示已验证服务或生成质量。首页已包含价格/额度，未另外请求价格页。未登录、上传照片、付款或提交生成。

- 41 HotelLobbyAI.art：保留顶部“原创合成音频”与后文“保留 Hotel Lobby 原音”的冲突。10 songs/月及40 songs/年不能换成任意规格视频数。
- 42 HotelLobby.net：FAQ 明确多项规则待 generation opens 前公布，记为规划/供应商宣称，上线可用性待核。
- 43 HotelLobbyVideo：区分原音参考模式与无声 freestyle；估算短片数不替代逐规格 credit 表。
- 44 RapDuo.video：3 credits 免费预览固定5秒、水印、只可观看；免费注册不等于可下载成片。
- 45 Rapduo.net：保留完整12秒一次性视频包计价，不虚构免费完整生成或中文支持。
- 46 HotelLobbyAI.best：仅取得 credits 和年付每月配额，现金价格未知；50赠额不足1650/2000 credits的完整片。

所有 API 记为 not_found，含义为本轮未定位公开文档；不宣称不存在 API。页面 $ 币种没有额外确认，不强行补为 USD。商业权限及原歌曲使用许可均保留待核。

采集工具增加 `--ids 41,42`，先验证候选 ID/HTTP(S) URL，再只采集所选站点；默认3并发，可用 `--workers` 调整。保留错误正文、网络错误、HTTP状态、UTC时间、SHA-256；分类区分 readable、login_required、error_page、inaccessible、needs_review。增量 index 依据ID合并已有记录，不丢失未选旧站；导入脚本不创建目录或发起网络。

验证：`python3 -m unittest discover -s tests/workbench -v`，12 tests 通过；测试仅 mock 网络，覆盖错误/登录页分类、URL/ID拒绝、选择参数、增量index保留及快照元数据。`catalog.load_sites(Path('.'))` 完整验证当前worktree全部43站，包含六个新增站；没有重新抓取旧站。
