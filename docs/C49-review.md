# C49：工作台集成与前端静态质量评审

日期：2026-10-24。测试基线：`5530a0f`（本分支已 `git merge main`，含真实 C47 quotes 与 C48 exports）。仅新增 `tests/workbench/test_integration.py` 与本评审，不修改应用模块。

## 结论与验收边界

自动化检查 **passed**：新增 11 项集成/静态测试，全工作台共 54 项测试，0 failures、0 errors、0 skips，7.410 秒，exit code 0。环境为 Python 3.9.6、Node v26.8.1。`git diff --check` 无输出，exit code 0。

浏览器验收 **blocked / 未验证**：当前页面访问策略已终止 CUA，本评审没有调用浏览器，也没有用替代工具绕过。桌面 1440px 与手机 390px 的实际布局、横向溢出、实际控件尺寸、视觉对比度、弹窗、键盘顺序与焦点恢复、真实输入/点击/下载、照片预览均未验证。C44/C45 前端应维持 partial / accepted=false，直到浏览器验收完成。无自动化失败不等于整个体验已验收。

## 自动化证据

| 范围 | 结果与证据 |
| --- | --- |
| 真实研究目录 | 46 条记录、46 个主域、01–46 唯一 ID；42 full_page、4 partial；17 documented、29 not_found；6 类均有样本。161 个 source 引用指向 160 个本地文件；Udio 同一文件两次引用用于不同支持范围，没有重复计算站点。 |
| 原文有效性 | 每条运行 catalog 验证，检查路径落在仓库内且可读 UTF-8；每个 full_page 独立要求至少一个 100 字符以上、无错误/登录/拦截标题的主要来源正文。只证明本地归档符合证据边界，不证明供应商功能可用或当前网页仍一致。 |
| 真实 HTTP 筛选与明细 | 完整目录与本地原记录逐项相等；6 类、API 与证据 AND 筛选、空搜索、46 个详情 GET、统计与 50 项决策均通过。 |
| brief 持久化 | 真实 POST 201 → GET → 列表 → 新 BriefStore 重开 → 关闭 HTTP server 后重启 GET；中文、多行歌词、引号与 SQL 形状的文本保留且无破坏。 |
| jobs | 不 mock 模块：brief_preview 201、规范化重放 200、不同 payload 409；GET 与新 JobStore 重开一致；provider_render 503 / PROVIDER_UNAVAILABLE 且不写任务。分镜时长总和正确，is_generated_video=false，无伪造媒体地址。 |
| 报价 | 真实 quote 模块经 HTTP 对 10/12/15 秒返回 200；保留 estimate/currency/basis/assumptions/is_vendor_quote=false；有价结果追到 RapReel，无匹配保持 null。C47 原有测试另覆盖 8 秒套餐、无插值与无来源规格。 |
| JSON/CSV/Markdown 下载 | 3 种实际 HTTP 响应均 200；MIME、UTF-8、attachment 文件名、Content-Length 正确；所有 46 站名称、官网、核查日期和全部来源 URL/路径存在。JSON 完整记录逐项相等；CSV 46 行，输入/输出/功能/限制/来源/观察/套餐嵌套 JSON 均逐站还原相等；Markdown 保留 50 项决策与研究边界。没有以 503 或 skip 代替下载验收。 |
| CSV 注入 | `= + - @` 及前导 TAB/CR/LF 公式形状字段均前置单引号；csv 解析后仍保留 7 个逻辑行和原始中文、换行、逗号及引号。 |
| 输入与路径 | 无主题、非法布尔时长/画质/未知 photo 字段、超长歌词、数组/坏 JSON/重复字段/NaN/非法 UTF-8/孤立代理码均结构化 400；错误 MIME 415，超过 1 MiB 413；拒绝新增 brief。明文/编码穿越与隐藏路径 403，仓库文件与未知 route 404，异常筛选/重复 query/非 UUID/坏编码/NUL 400。 |
| 页面与资源 | 两页与四个 JS/CSS 的真实 GET/HEAD、MIME、UTF-8、nosniff 和长度通过。HTMLParser 静态检查无重复 DOM ID，输入都有非空显式或包裹 label，ARIA/锚点引用存在，导航双向可达，脚本与样式文件存在，脚本静态 `$()` ID 引用存在；两个脚本 `node --check` 通过。 |
| 静态交互设计规则 | 两份 CSS 含 focus-visible、44px 规则、760px 响应式断点与 prefers-reduced-motion。代码通过 textContent 渲染第三方字段，未使用 innerHTML/document.write/insertAdjacentHTML。这些是源代码静态覆盖，**不是浏览器测试，也不能证明实际 390px 布局或键盘行为**。 |

## 页面研究边界复核

研究页统计把 full_page 标为“已读取正文”，旁注“来源读取 · 非效果实测”，全局提示“已读正文不代表功能或授权已验证”。站点卡保留“官网宣称 / 未实测”；详情继续区分输入、输出、功能、API 范围、限制、研究观察及 source.supports，未把 API documented 等同于可直接使用。

首页、比较弹窗均提示 credits 不跨站相加、年付折月不等于单次价格；价格摘要/免费范围/限制由原研究记录展示。创建页称“价格参考”，提示非供应商实时报价、非付款金额、无报价不代表 0 元。quotes 返回竞品历史套餐，明确自身供应商成本待核、竖屏到 9:16 是映射推断；不把订阅、credits 与单次成片混算。

“原音/人声生成”能力没有从口型或音乐视频分类中自动推出：来源详情显示各站 inputs/outputs/features/limitations，原始研究记录仍保存生成歌曲与上传已有音频的差别。创建页明确“分镜是文字规划，不包含 AI 人声、口型、音轨或成片”，照片只在当前浏览器本地预览；真实 provider_render 诚实返回 503。本次未验证任何真实音质、原创性、声纹授权、音画同步或视频生成。

## 发现与跟进

未发现自动化阻断缺陷。发现一个可改善的追溯入口：本次基线的创建页渲染 quote.basis 与 assumptions，但未直接显示 API 返回的 quote.source_url 可点击链接，需要回目录查 RapReel。已报告 root；root 已采纳，将在应用模块增加仅允许 HTTPS 的来源链接，随后另行重跑 JS 与全套检查。此改进未包含于本提交或下方测试基线。

阅读依据：WORKBENCH_SPEC、API_WIRE_CONTRACT、DESIGN_NOTES、RESEARCH_CONTRACT、design-system MASTER、全部 rap_workbench 与 web 源码。采用 ui-ux-pro-max 静态审查，针对“form input visible labels”查询命中 Input Labels / Form Labels；没有将推荐项当作实际可访问性证明。

## 原始测试日志

下方为最终完整命令的真实输出（保留现有模块测试与新增测试，未删改失败或跳过项）。初轮运行发生于合并 quotes/exports 前，出现 MODULE_UNAVAILABLE；合并后完整重跑以下结果，未把初轮失败计作通过。

```text
$ python3 -m unittest discover -s tests/workbench -v
test_all_supported_options_and_boundaries (test_briefs.BriefTests) ... ok
test_defaults_are_normalized_without_mutating_input (test_briefs.BriefTests) ... ok
test_invalid_fields_rejected (test_briefs.BriefTests) ... ok
test_sqlite_reopen_roundtrip_and_unknown_id (test_briefs.BriefTests) ... ok
test_threaded_creates_are_durable_and_unique (test_briefs.BriefTests) ... ok
test_duplicate_primary_domain_rejected_and_stats_deduplicated (test_catalog.CatalogTests) ... ok
test_evidence_missing_traversal_absolute_and_symlink_rejected (test_catalog.CatalogTests) ... ok
test_full_page_needs_successful_primary_source (test_catalog.CatalogTests) ... ok
test_load_filter_and_json_stats (test_catalog.CatalogTests) ... ok
test_loading_reports_filename_and_invalid_json (test_catalog.CatalogTests) ... ok
test_price_numbers_and_credit_labels (test_catalog.CatalogTests) ... ok
test_repository_records_validate_without_assuming_final_count (test_catalog.CatalogTests) ... ok
test_schema_errors_are_field_specific (test_catalog.CatalogTests) ... ok
test_collect_keeps_metadata_and_error_body (test_evidence.EvidenceTests) ... ok
test_incremental_cli_preserves_index_and_collects_only_selected (test_evidence.EvidenceTests) ... ok
test_response_classification (test_evidence.EvidenceTests) ... ok
test_selection_validation (test_evidence.EvidenceTests) ... ok
test_csv_all_rows_nested_fields_and_sources_roundtrip (test_exports.ExportTests) ... ok
test_csv_special_characters_and_formula_neutralization (test_exports.ExportTests) ... ok
test_empty_exports (test_exports.ExportTests) ... ok
test_json_preserves_all_original_records_and_sources (test_exports.ExportTests) ... ok
test_markdown_complete_sites_decisions_and_api_unknown_boundary (test_exports.ExportTests) ... ok
test_real_http_all_export_mime_attachment_data (test_exports.ExportTests) ... ok
test_01_catalog_filters_stats_details_and_empty_search (test_integration.RealWorkbenchHTTPIntegrationTests) ... ok
test_02_brief_create_get_sqlite_reopen_and_server_restart (test_integration.RealWorkbenchHTTPIntegrationTests) ... ok
test_03_jobs_real_idempotency_conflict_provider_and_sqlite (test_integration.RealWorkbenchHTTPIntegrationTests) ... ok
test_04_real_quote_is_sourced_or_explicitly_incomparable (test_integration.RealWorkbenchHTTPIntegrationTests) ... ok
test_05_all_three_downloads_keep_full_data_sources_and_boundaries (test_integration.RealWorkbenchHTTPIntegrationTests) ... ok
test_06_csv_injection_newlines_and_unicode_are_safe_without_lost_records (test_integration.RealWorkbenchHTTPIntegrationTests) ... ok
test_07_invalid_inputs_and_paths_are_structured_and_do_not_write (test_integration.RealWorkbenchHTTPIntegrationTests) ... ok
test_08_actual_static_pages_and_assets_get_and_head (test_integration.RealWorkbenchHTTPIntegrationTests) ... ok
test_46_unique_primary_domains_and_real_primary_bodies (test_integration.RepositoryEvidenceIntegrationTests) ... ok
test_honesty_copy_and_responsive_focus_rules_present (test_integration.StaticFrontendIntegrationTests) ... ok
test_html_labels_ids_navigation_assets_and_javascript_references (test_integration.StaticFrontendIntegrationTests) ... ok
test_real_server_201_200_409_503_and_get (test_jobs.JobHTTPTests) ... ok
test_concurrent_retries_across_stores_only_create_one_job (test_jobs.JobTests) ... ok
test_conflicting_payload_or_mode_does_not_write (test_jobs.JobTests) ... ok
test_invalid_payloads_never_write (test_jobs.JobTests) ... ok
test_no_key_creates_independent_jobs (test_jobs.JobTests) ... ok
test_normalized_idempotency_reopen_and_independent_results (test_jobs.JobTests) ... ok
test_preview_is_a_complete_downloadable_plan_for_each_duration (test_jobs.JobTests) ... ok
test_provider_unavailable_creates_nothing_and_does_not_consume_key (test_jobs.JobTests) ... ok
test_real_server_invalid_input_is_400 (test_quotes.QuoteHTTPTests) ... ok
test_real_server_packages_and_no_match (test_quotes.QuoteHTTPTests) ... ok
test_all_exact_official_packages (test_quotes.QuoteTests) ... ok
test_json_roundtrip_and_independent_results (test_quotes.QuoteTests) ... ok
test_no_interpolation_or_unverified_spec (test_quotes.QuoteTests) ... ok
test_strict_fields_and_types (test_quotes.QuoteTests) ... ok
test_bad_json_fields_mime_and_body_limit (test_server.ServerTests) ... ok
test_catalog_queries_stats_decisions (test_server.ServerTests) ... ok
test_optional_module_wire_adapters (test_server.ServerTests) ... ok
test_optional_modules_unavailable_are_honest_503 (test_server.ServerTests) ... ok
test_real_http_brief_roundtrip_and_restart (test_server.ServerTests) ... ok
test_static_files_confined_to_web_no_cors (test_server.ServerTests) ... ok

----------------------------------------------------------------------
Ran 54 tests in 7.410s

OK

exit_code=0
```
