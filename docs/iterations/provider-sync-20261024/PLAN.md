# Iteration 2: documented Sync client and durable observation

Status: planned before implementation, 2026-10-24. Original goal stays active. Research report revision10 remains the verified first release; C44/C45 browser gates remain open. No browser/tool bypass is permitted.

## Result to produce

Implement the next-stage provider boundary already listed in PLAN.md: a source-backed REST client, a durable submission journal, and a usable local preparation/observation CLI. Keep the public `provider_render` route unavailable until live credentials, authorized assets, billable-duration verification and quality validation are complete. Do not claim that a contract server generated AI media.

Reuse the existing C48/C49/C50 agents in three new isolated worktrees. This is a follow-up iteration, not another set of 50 agents. Do not overwrite their original research/codex/Cxx acceptance records.

| Worker | Worktree | Owned files |
|---|---|---|
| C48 follow-up | provider_sync_client | rap_workbench/sync_provider.py; tests/workbench/test_sync_provider.py; docs/iterations/provider-sync-20261024/client-review.md |
| C49 follow-up | provider_sync_journal | rap_workbench/provider_journal.py; tests/workbench/test_provider_journal.py; docs/iterations/provider-sync-20261024/journal-review.md |
| C50 follow-up | provider_sync_cli | rap_workbench/provider_cli.py; tests/workbench/test_provider_cli.py; docs/iterations/provider-sync-20261024/cli-review.md |
| Root | integration | source capture and manifest; final real-HTTP contract fixture; merged verification; update the same Feishu document |

## Official-source contract

Sources are archived in research/providers/sync/20261024/. Use only the documented public API and docs OpenAPI, not the larger root OpenAPI's undocumented endpoints.

- Fixed API origin https://api.sync.so; POST /v2/generate; GET /v2/generate/{id}; POST /v2/generations/estimate.
- x-api-key authentication. Idempotency-Key is required by this client for create, 1–128 characters matching `[A-Za-z0-9._~-]+`. Reuse one serialized request and key across retries. 201 first accepted, 200 replay; replay is not completion.
- For this iteration support only sync-3 with exactly one image/video URL and one audio URL. No uploads, TTS, webhooks, batch, or public submission endpoint.
- JSON create is demonstrated by the quickstart and common_CreateGenerationDto; public path schema mainly advertises multipart. Record this documentation mismatch, do not invent unsupported JSON fields.
- Raw response fields are camelCase (`outputUrl`, `errorCode`), statuses PENDING/PROCESSING/COMPLETED/FAILED/REJECTED. API does not promise a usable output URL on every response. Missing output must never become a fabricated URL or a download-success claim.
- Estimate request uses model/duration/fps/reasoningEnabled, response uses estimatedFrameCount/estimatedGenerationCost (USD)/estimatedCredits (number or null). Numeric inputs/results must be finite. Estimation does not fetch media or verify its actual billable duration; it cannot by itself enforce a real submission budget.
- 409 conflict is not retryable with changed inputs. IDEMPOTENCY_IN_PROGRESS may retry with same key. Unknown outcome/timeout retains the key and last known state. Never resubmit from a failed GET or generate another key to evade an unresolved submission. Key retention is seven days or longer while active/unresolved; local journal does not delete old actions automatically.

## Python interfaces

### sync_provider.py (C48)

- build_generation_request(*, visual_type, visual_url, audio_url, model='sync-3', output_file_name=None) -> JSON dict. Validate HTTPS URLs, no credentials/private literal IP/localhost; preserve URL strings exactly (including signed query) and input order. Reject unsupported fields/types rather than guessing model behavior.
- validate_generation_request(payload) -> copied validated dict.
- normalize_generation(payload) -> `{id, status, output_url, output_available, error_code}`. Validate id, enum and optional HTTPS output URL; no raw provider message or request URL in errors. COMPLETED without output_url is represented honestly as output_available=false.
- SyncClient(api_key=None, *, allow_live=False, transport=None, timeout=15, max_attempts=2, sleep=...) with create(payload,idempotency_key), get(generation_id), estimate(duration,fps=30,reasoning_enabled=False,model='sync-3'). create/get return normalized snapshots. estimate returns documented camelCase fields after validation.
- Injected transport callable `(method, url, headers, body_bytes_or_None, timeout) -> (http_status, headers_dict, body_bytes)`. Default uses urllib, rejects redirects, bounds response size, never logs key/body/URLs. `allow_live=False` fails before transport even if key exists. Tests use only dummy keys and local fixture transport with allow_live=True.
- SyncClient.from_env() requires BOTH RAP_ENABLE_SYNC_CLIENT=1 and nonempty SYNC_API_KEY. Do not inspect any other credential store. Root only checked presence: both absent.
- Errors SyncConfigError(ValueError), SyncTransportError(RuntimeError), SyncProtocolError(SyncTransportError). Safe public properties http_status/code/generation_id/outcome_unknown/retry_after. Never expose raw body, key or signed URLs through repr/str/errors. Retries bounded; create always same key/body; GET failures never trigger POST.

### provider_journal.py (C49)

SubmissionStore(path) with prepare(idempotency_key,payload)->(record,created_bool), get(local_id)->record/None, list(), payload_for_retry(local_id)->original JSON, mark_submitting(local_id), record_acceptance(local_id,snapshot), apply_snapshot(local_id,snapshot), record_submission_unknown(local_id,error_code=None,remote_id=None), record_observation_error(local_id,error_code), events(local_id).

Each record: id (local UUID), created_at/updated_at, idempotency_key, payload_digest, state (READY/SUBMITTING/SUBMISSION_UNKNOWN or the five documented statuses), remote_id or null, output_url or null, output_available bool, revision, last_error_code or null. Persist original payload privately in SQLite, not in the returned public record/event log. Store normalized snapshots supplied by client; validate independently. Atomic UNIQUE key prevents duplicates across instances/threads. Same key/same canonical JSON returns original record; object field order irrelevant, array order and URL strings matter. Terminal states cannot be downgraded by stale responses; PENDING cannot overwrite PROCESSING. An observation error updates diagnostics and never infers a terminal failure. Unknown submission preserves key and may carry a documented remote id for later polling. No network in this module.

### provider_cli.py (C50)

`python3 -m rap_workbench.provider_cli plan --manifest FILE [--journal PATH]` accepts manifest with visual_type, visual_url, audio_url, optional model/output_file_name/idempotency_key. Bounds file size, rejects unknown fields, prepares journal before any remote action, and prints local id/key/digest, target endpoint, model/input types and explicit no-generation/no-billing status. Never print media query strings or API keys. Same supplied key can be resumed from disk. Default journal `.workbench/provider-submissions.sqlite3`.

`show --id UUID [--journal PATH]` is local only, prints safe metadata and has_output, redacts actual signed output URL. `refresh --id UUID --allow-network [--journal PATH]` may only GET an already-known remote id via SyncClient.from_env; no POST/submit command exists in this CLI. No key, no gate, no explicit flag, or no remote id must fail without networking. It records observations without resetting an unknown/active task to failed. Document that CLI does not submit generation and current UI provider_render remains503.

## Acceptance

Use no live Sync credentials, no paid generation, no real person media and no browser. Run existing54 regression tests plus meaningful adversarial cases: redirects/key leakage, malformed/oversized JSON, nonfinite estimates, input URL/key rejection, stable POST retries, rate/unknown/conflict handling, response model, SQLite restart and concurrency, out-of-order terminal observations, exact key/payload recovery, local CLI zero-network plan/show and refresh guards. Root will run one real local HTTP fixture covering client -> request -> pending -> processing -> completed and unknown/failed cases. Evidence must call these contract tests, not provider quality tests.

After root integration and verification, reclaim the three clean follow-up worktrees, preserve original C44/C45 worktrees and goal state, reconcile stale progress docs, append an iteration update to the existing Feishu document and read it back. Live generation and browser acceptance remain unverified until their real prerequisites exist.
