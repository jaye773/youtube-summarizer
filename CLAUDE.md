# YouTube Summarizer - Claude Code Documentation

## Project Overview

YouTube Summarizer is a Flask web application that summarizes YouTube videos and playlists with Google Gemini or OpenAI models, and reads summaries aloud with Google Cloud Text-to-Speech. The browser starts a background summary request (`POST /summarize/start`), which runs on a small thread pool; progress and each finished result are pushed over Server-Sent Events (SSE), with `GET /summarize/<request_id>` as the polling fallback. `POST /summarize` still summarizes synchronously for API clients.

## Architecture

| File | Responsibility |
|---|---|
| `app.py` | Flask app: configuration, API client setup, routes, settings page, error handlers |
| `ai_models.py` | `AVAILABLE_MODELS` registry, prompt, Gemini (`google-genai` Client) and OpenAI summary generation |
| `auth.py` | Passcode login, per-IP lockout, `require_auth` decorator |
| `cache.py` | `SummaryCache` (SQLite summary store with a dict-like interface), one-time JSON migration, cache entry builder |
| `sse.py` | SSE connection registry, session-scoped broadcast, message formatting, stream generator |
| `summary_jobs.py` | Background summary requests: bounded `SummaryExecutor` (`SUMMARY_WORKERS` threads) and the in-memory `RequestStore` (per-session ownership, TTL, size caps) |
| `youtube_helpers.py` | URL parsing, YouTube Data API calls, transcript fetching (webshare proxy aware) |
| `tts_helpers.py` | Text cleanup and TTS synthesis |
| `voice_config.py` | Available voices, fallbacks, audio cache keys and cleanup |
| `gunicorn_config.py` | Production server: **1 process**, gthread, `GUNICORN_THREADS` threads |
| `templates/` + `static/js/` | Pages and their scripts: `index.js`, `login.js`, `settings.js` (classic scripts, globals used by inline `onclick`), `theme-init.js` / `settings-theme.js` (ES modules importing `theme-manager.js`). Templates keep only the small `<head>` theme-flash guard inline; put new page JS in `static/js/`, not in templates |

### Request flow
1. The UI sends `POST /summarize/start` with `{"urls": [...], "model": "<key>"}`. It is validated, recorded in `summary_jobs.store` (owned by `session["session_id"]`) and submitted to `summary_jobs.executor`; the response is `202 {"request_id", "status": "queued", "status_url"}`. `429` when the session already has `SUMMARY_MAX_ACTIVE_PER_SESSION` requests running or the store is full of running requests.
2. The worker runs `_run_summary_batch()` (shared with the synchronous `POST /summarize`): for each URL, cache lookup → YouTube details → transcript → `generate_summary()` → cache write via `_summarize_and_cache`. An error in one URL becomes that URL's error result; the batch continues.
3. Events go to the session's `/events` stream with `sse.broadcast(..., session_filter=session_id)`. A `before_request` hook assigns every browser a `session_id`.
   - `summary_progress` / `summary_complete`: progress bar and per-video notices (unchanged).
   - `summary_result`: `{request_id, seq, index, kind, item[, playlist_title]}` per finished result. `kind` is `item` (a whole top-level result: video, error, or failed playlist), `playlist` (a playlist started; `item.summaries` is empty) or `playlist_video` (one finished video of the playlist at URL `index`). `seq` is 0,1,2… per request.
   - `summary_done`: `{request_id, status: completed|failed, error, results_count}`.
4. `GET /summarize/<request_id>` returns `{request_id, status, done, model, url_count, error, results, items}` (`results` has the same shape as the `/summarize` response, filled in as results arrive; `items` is the list of `summary_result` payloads). 404 for unknown/expired ids and for other sessions. The UI renders items in `seq` order, polls this endpoint when SSE is not connected (and every 15 s anyway), and calls it once at the end to reconcile. If `/summarize/start` returns 404 (older server) the UI falls back to `POST /summarize`.
5. Finished requests are kept for `SUMMARY_REQUEST_TTL` seconds (default 3600); at most `SUMMARY_MAX_REQUESTS` are stored (oldest finished evicted first).

### State and process model
All state is in process memory or in files under `DATA_DIR`:
- `summaries.db` (SQLite, WAL mode; summaries), `audio_cache/` (MP3s keyed on voice + text), `login_attempts.json`
- `.env` written by the settings page (loaded at startup, overrides the environment)
- `.secret_key` (generated session secret when `SESSION_SECRET_KEY` is unset)

On first start, an existing `summary_cache.json` is imported into `summaries.db` in one transaction and renamed to `summary_cache.json.migrated`. `app.summary_cache` is a `SummaryCache`: it behaves like a dict, but every write commits immediately (no `save_summary_cache` needed) and entries read from it are copies, so assign changes back. Under `TESTING` it is an in-memory database.

Because SSE connections, login lockouts, rate-limit counters and background summary requests live in memory, **the app must run as a single process**. Background summaries run on `SUMMARY_WORKERS` executor threads (not gunicorn request threads). Concurrency comes from threads; each open SSE stream holds one thread, so streams are capped by `SSE_MAX_CONNECTIONS` (default 20, below `GUNICORN_THREADS`, default 32).

`DATA_DIR` defaults to `data` in Docker and `.` otherwise.

## AI Models
Defined in `ai_models.AVAILABLE_MODELS` (key → provider + model id):
- Google: `gemini-2.5-flash` (default), `gemini-2.5-pro`
- OpenAI: `gpt-5`, `gpt-5-mini`, `gpt-4o`, `gpt-4o-mini`

To add a model: add it to `AVAILABLE_MODELS` (the UI reads the list from `/api_status`) and, for a new provider, add a branch in `generate_summary()`.

## Environment Variables

Required: `GOOGLE_API_KEY` (YouTube, Gemini, TTS). Optional: `OPENAI_API_KEY`.

| Variable | Default | Notes |
|---|---|---|
| `LOGIN_ENABLED` / `LOGIN_CODE` | `false` / – | Passcode login |
| `SESSION_SECRET_KEY` | generated, persisted | |
| `MAX_LOGIN_ATTEMPTS` | `5` | |
| `LOCKOUT_DURATION` | `15` | **minutes** |
| `TRUST_PROXY_HOPS` | `0` | Trust `X-Forwarded-For` only behind this many proxies |
| `ENABLE_DEBUG_ENDPOINTS` | `false` | Enables `/debug_transcript` |
| `MAX_TTS_CHARS` | `50000` | `/speak` text limit |
| `NETWORK_TIMEOUT` | `60` | Per-request timeout for transcript fetches; also the process default socket timeout |
| `SSE_MAX_CONNECTIONS` | `20` | |
| `SUMMARY_WORKERS` | `2` | Threads processing background summary requests |
| `SUMMARY_REQUEST_TTL` | `3600` | Seconds a finished background request stays retrievable |
| `SUMMARY_MAX_REQUESTS` | `200` | Stored background requests (finished ones evicted first) |
| `SUMMARY_MAX_ACTIVE_PER_SESSION` | `3` | Queued/running background requests per browser session |
| `GUNICORN_THREADS` | `32` | |
| `RATE_LIMIT_ENABLED` | `true` | Per-IP limits (Flask-Limiter, in memory); always off when `TESTING` is set at import |
| `RATE_LIMIT_SUMMARIZE` | `10 per minute;100 per day` | `/summarize`; empty string disables |
| `RATE_LIMIT_TTS` | `30 per minute;300 per day` | Shared by `/speak` and `/preview-voice`; empty disables |
| `RATE_LIMIT_LOGIN` | `10 per minute` | `POST /login`; empty disables |
| `SESSION_COOKIE_SECURE` | `false` | HTTPS-only session cookie |
| `TTS_VOICE` | `en-US-Chirp3-HD-Zephyr` | |
| `WEBSHARE_PROXY_*` | – | Proxy for transcript fetching (HOST+PORT: fixed proxy; unset: Webshare rotating residential) |
| `FLASK_DEBUG` | `false` | Only for `python app.py` |
| `TESTING` | – | Test mode; auth bypass also requires `app.config["TESTING"]` |

## Common Operations

```bash
make run            # Flask dev server on :5001
make test           # pytest suite (browser tests skip without Playwright browsers)
make quick-test     # core app tests
make coverage
make quality        # format + lint
docker compose up -d
```

Production: `gunicorn -c gunicorn_config.py app:app` (what the Dockerfile runs). Never raise `workers` above 1.

## Testing
- `tests/test_app.py` – routes, auth, settings, security regressions
- `tests/test_transcript_and_summary.py` – transcript and model calls (mocked)
- `tests/test_cache.py`, `tests/test_pagination.py`, `tests/test_integration.py`, `tests/test_sse.py`
- `tests/test_rate_limit_csrf.py` – rate limits (429, per-IP, shared budgets) and CSRF (JSON-only, cookie flags)
- `tests/test_background_summaries.py` – `/summarize/start` + status endpoint, session isolation, TTL, error isolation (patch `summary_jobs.executor` with `SummaryExecutor(synchronous=True)` for deterministic tests)
- `tests/test_dark_mode_integration.py`, `tests/test_theme_performance.py`, `tests/test_visual_dark_mode.py` – Playwright/theme tests (`make test-browser`)

Tests import `app` with `TESTING=true`, which skips real API client creation. Patch module globals such as `app.summary_cache` (a plain dict works; the routes handle both), `app.tts_client`, `ai_models.gemini_client`, `ai_models.openai_client`.

CI (`.github/workflows/tests.yml`): flake8 on the app modules, pytest with coverage, and a Docker build + `/health` smoke test.

## Security Notes
- Settings page never renders secret values; blank secret fields keep the current value.
- Error responses never include stack traces; details go to the server log.
- `voice_id` is allowlisted (`validate_voice_name`) before it becomes part of a cache filename.
- Login passcode comparison is constant-time (`hmac.compare_digest`).
- Rate limiting: decorate new endpoints that spend AI credits with `@summarize_rate_limit` and TTS endpoints with `@tts_rate_limit` (shared per-IP budgets defined in `app.py`, placed below `@require_auth`). 429s are JSON for `API_ROUTE_PREFIXES`. Tests enable limits with `app.config["RATE_LIMIT_ENABLED"] = True` plus `limiter.reset()`.
- CSRF: `SameSite=Lax` cookie, and a `before_request` hook rejects POST/PUT/PATCH/DELETE without `Content-Type: application/json` (415). Parse bodies with `get_json_body()`, never `get_json(force=True)`.

## Known Limitations
- In-memory state (SSE connections, login lockouts) means one process. Summaries are already in SQLite, which several processes on one host can share; scaling out further still needs shared login state and SSE fan-out (e.g. Redis).
- `youtube-transcript-api` is pinned exactly (1.2.4) because YouTube changes regularly break transcript fetching; upgrade deliberately and run a real fetch. `get_transcript` uses the instance API (`YouTubeTranscriptApi(proxy_config=..., http_client=...).list()`), creating one instance per call (the class is not thread-safe).
- Background requests are in memory: a restart loses queued/running requests (the UI reports the request as lost).
