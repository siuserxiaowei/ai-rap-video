# HTTP wire contract

This is the coordination contract for parallel implementation. Core behavior is in WORKBENCH_SPEC.md. All JSON uses UTF-8. Structured API errors are `{ "error": { "code": "...", "message": "..." } }` with an appropriate HTTP status. APIs accept only bounded JSON bodies, no raw local paths.

| Route | Success response |
|---|---|
| GET /api/sites?q=&category=&api_status=&evidence_status= | `{sites: [...], total: number, filtered: number}` |
| GET /api/sites/01 | `{site: {...}}` |
| GET /api/stats | `{total, full_page, by_category, by_evidence, by_api, checked_at}` |
| GET /api/decisions | `{decisions: [...]}` |
| GET /api/briefs | `{briefs: [...]}` |
| POST /api/briefs | `{brief: {...}}`, status 201 |
| GET /api/briefs/<uuid> | `{brief: {...}}` |
| POST /api/quote | `{quote: {...}}` |
| POST /api/jobs | `{job: {...}}`, 201 new / 200 idempotent replay |
| GET /api/jobs/<uuid> | `{job: {...}}` |
| GET /api/report?format=json\|csv\|markdown | raw downloadable content, correct MIME and filename |

Brief payload fields: `topic` (required, 1–240 chars), `mode` (solo/duo), `stage` (rooftop/studio/street/lobby), `duration_seconds` (10/12/15), `aspect_ratio` (9:16/1:1/16:9), `quality` (480p/720p/1080p), `lyrics` (optional, max 4000 chars), `language` (zh/en). Returned brief adds `id` and `created_at`.

Quote accepts `duration_seconds`, `quality`, `aspect_ratio`, optional `site_id`. It returns only a source-supported comparable price or `estimate: null` with an explanation. Includes `currency`, `basis`, `assumptions`, `is_vendor_quote: false`. It is not an invoice or supplier live quote.

Job payload: `mode` (brief_preview/provider_render), `brief` (validated brief fields), optional `idempotency_key` (can also come from Idempotency-Key header). A brief_preview succeeds with `status: completed`, `kind: brief_preview` and `result: {storyboard: [...], parameters: {...}, is_generated_video: false}`. It has no fake media URL. provider_render without configured adapter returns 503 with PROVIDER_UNAVAILABLE. Same key/same normalized input gets same job; same key/different input returns409.

Server may adapt internal method names from each module without changing this wire contract. No module except server.py owns HTTP routes. Frontends own their page files and can use native fetch; do not rewrite each other's files. C44 owns index.html, styles.css and app.js. C45 owns create.html, create.js and create.css. Shared style changes should be messaged to root, not silently committed.
