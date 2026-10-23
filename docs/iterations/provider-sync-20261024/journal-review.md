# Sync submission journal review — iteration 20261024

仅本迭代新增，不覆盖原 C49 台账。基线 `81e0870`，Python 3.9.6。遵循本目录 PLAN.md，完整阅读归档 [官方幂等文档](../../../research/providers/sync/20261024/idempotency.txt)，并核对 public-openapi.json 的 GenerationId / Generation / CreateGenerationDto。本模块没有网络调用、凭据读取或生成提交。

## 实现与接口

`SubmissionStore(path='.workbench/provider-submissions.sqlite3')` 提供 PLAN 中全部方法。`prepare(key,payload)` 返回 `(public_record, created_bool)`；get 未知合法 local UUID 返回 None；list 返回公开记录列表；payload_for_retry 返回原始 JSON 独立副本。全部 mark/record/apply 方法返回公开记录；events 返回按持久化顺序的元数据事件。未知 local UUID 的写入、events 与 payload_for_retry 抛 KeyError；非法 ID / 字段抛 ValueError；同 key 不同 canonical JSON 抛 `IdempotencyConflict(ValueError)`。错误文本不回显 payload、媒体 URL 或远端原始消息。

SQLite 使用每操作独立连接、BEGIN IMMEDIATE、key UNIQUE 约束。首次私存原始 payload JSON，另存排序对象键的 canonical JSON 及 SHA-256 digest。重排对象字段等价；数组顺序、每个 URL 字符与签名 query 变化均冲突。重放不会替换原 payload 或增加 action。payload 仅接受 1 MiB 内、有限数字、UTF-8 的 JSON 对象；拒绝非字符串对象键、Python tuple/bytes 等非 JSON 类型与过深嵌套。具体 Sync 请求结构由 client 的独立请求验证负责，journal 不依赖 sync_provider 或任何尚未完成模块。

public record 字段严格为 id、created_at、updated_at、idempotency_key、payload_digest、state、remote_id、output_url、output_available、revision、last_error_code。原 payload 不进入 public record / list / events。events 仅有本地 ID、更新时间、revision、state、remote_id、是否有输出、机器错误码、事件种类及可选 observed_state；不存输入或输出媒体 URL。public record 按固定契约可含真实 output_url，因此调用方打印时仍须采用白名单或移除签名 URL；CLI 同事已确认。

新建父目录尽可能 0700，数据库预创建 0600，数据库与 SQLite sidecar 尽力收紧为 0600；在本机 POSIX 测试断言通过。拒绝数据库路径为 symlink / 非普通文件。journal 不自动删除任何 action，因此不会因本地七天期满而重绑定活跃或未知 key。

## 状态与独立验证

本地状态 READY / SUBMITTING / SUBMISSION_UNKNOWN，远端状态仅 PENDING / PROCESSING / COMPLETED / FAILED / REJECTED。mark_submitting 仅将 READY 变为 SUBMITTING；对未知、已接受或终态保持原态，避免清掉不确定性。unknown 可绑定安全 remote_id 供后续查询，但不会覆盖已知远端 state。observation error 只更新 last_error_code、revision 与审计事件，不能推断 FAILED，不能换 key，也不能创建 URL。

远端 ID 按官方 string 类型、root 协调规则独立校验：1–128 ASCII `[A-Za-z0-9._~-]+`，排除单独 `.` / `..`，保留大小写；本地 ID 则为 canonical UUID。机器错误码为同长度的安全 ASCII token 或 null。normalized snapshot 拒绝未知字段和未知状态，独立验证 output_available 必须是与状态/URL 一致的 bool；输出 URL 必须为无凭据、无控制字符的公网 HTTPS URL，拒绝 localhost、private literal IP、畸形/模糊数字 IP、非法端口等；不解析 DNS，也不请求该 URL。

远端 ID 一旦绑定不可被另一任务的响应覆盖。PROCESSING 不被 PENDING 覆盖；三个终态保持首次已知终态，矛盾或较早状态仅留下 snapshot_ignored 元数据事件。首次 COMPLETED 无 URL 时保持 output_available=false；后续同状态可补充真实 URL，已知 COMPLETED 的真实 URL 不被稀疏重放抹掉。PENDING 中出现的 URL 不能在缺少输出的 COMPLETED 中升级为“下载可用”。任何输出可用性只描述有来源的 URL 引用，未验证文件仍可下载或质量合格。

## 验证结果与边界

新增 10 项专项测试覆盖：SQLite 重开与独立副本、原 payload 私存、0600/0700、canonical 指纹、对象/数组/签名 URL 语义、12 线程独立 store 并发一个 action/一个 submitting 事件、PENDING→PROCESSING→COMPLETED、所有终态与 stale 保护、缺输出与后补输出、unknown 与 GET 错误、错 remote ID 原子拒绝、未知状态/坏 snapshot、URL/错误码/ID/JSON 拒绝与无敏感数据回显、旧 action 不自动删除。

完整工作台回归 **64 tests，0 failures / errors / skips，20.112s，exit 0**；其中原有 54 项保持通过。`git diff --check` 无输出。测试使用临时 SQLite 与合成 example URL；日志专项测试没有网络或真实 key，已有 HTTP 回归仅访问本机工作台。未进行 Sync 服务质量、账单时长、原音/人声/口型、真实授权媒体或浏览器测试；public provider_render 仍由现有模块保持 503。本模块通过不构成真实供应商接入或生成成功。

## 完整真实回归日志

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
test_acceptance_progress_stale_order_output_enrichment_and_terminal_preservation (test_provider_journal.SubmissionJournalTests) ... ok
test_canonical_object_order_but_array_or_signed_url_changes_conflict (test_provider_journal.SubmissionJournalTests) ... ok
test_concurrent_independent_instances_create_one_action_and_one_submitting_event (test_provider_journal.SubmissionJournalTests) ... ok
test_incomplete_output_reference_cannot_become_completed_download_claim (test_provider_journal.SubmissionJournalTests) ... ok
test_keys_payloads_diagnostics_local_ids_and_missing_records (test_provider_journal.SubmissionJournalTests) ... ok
test_local_key_retention_does_not_delete_old_or_unresolved_actions (test_provider_journal.SubmissionJournalTests) ... ok
test_output_urls_are_independently_validated_without_exposing_input (test_provider_journal.SubmissionJournalTests) ... ok
test_restart_exact_retry_private_payload_and_permissions (test_provider_journal.SubmissionJournalTests) ... ok
test_unknown_and_observation_error_do_not_infer_failure_or_reset_known_state (test_provider_journal.SubmissionJournalTests) ... ok
test_wrong_remote_ids_unknown_states_and_malformed_snapshots_are_atomic (test_provider_journal.SubmissionJournalTests) ... ok
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
Ran 64 tests in 20.112s

OK

exit_code=0
```
