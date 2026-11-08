# YouTube Summarizer - Claude Code Documentation

## Project Overview

YouTube Summarizer is a Flask web application that summarizes YouTube videos and playlists with Google Gemini or OpenAI models, and reads summaries aloud with Google Cloud Text-to-Speech. Summarization runs synchronously inside the `/summarize` request; progress is pushed to the browser over Server-Sent Events (SSE).

## Architecture

| File | Responsibility |
|---|---|
| `app.py` | Flask app: configuration, API client setup, routes, settings page, error handlers |
| `ai_models.py` | `AVAILABLE_MODELS` registry, prompt, Gemini (`google-genai` Client) and OpenAI summary generation |
| `auth.py` | Passcode login, per-IP lockout, `require_auth` decorator |
| `cache.py` | Summary cache load/save (atomic, lock-protected) and cache entry builder |
| `sse.py` | SSE connection registry, session-scoped broadcast, message formatting, stream generator |
| `youtube_helpers.py` | URL parsing, YouTube Data API calls, transcript fetching (webshare proxy aware) |
| `tts_helpers.py` | Text cleanup and TTS synthesis |
| `voice_config.py` | Available voices, fallbacks, audio cache keys and cleanup |
| `gunicorn_config.py` | Production server: **1 process**, gthread, `GUNICORN_THREADS` threads |
| `templates/` + `static/js/` | Pages and their scripts: `index.js`, `login.js`, `settings.js` (classic scripts, globals used by inline `onclick`), `theme-init.js` / `settings-theme.js` (ES modules importing `theme-manager.js`). Templates keep only the small `<head>` theme-flash guard inline; put new page JS in `static/js/`, not in templates |

### Request flow
1. `POST /summarize` with `{"urls": [...], "model": "<key>"}`.
2. For each URL: cache lookup → YouTube details → transcript → `generate_summary()` → cache write.
3. Progress and completion events are sent with `sse.broadcast(..., session_filter=session["session_id"])` to the user's `/events` stream. A `before_request` hook assigns every browser a `session_id`.

### State and process model
All state is in process memory or in files under `DATA_DIR`:
- `summary_cache.json` (summaries), `audio_cache/` (MP3s keyed on voice + text), `login_attempts.json`
- `.env` written by the settings page (loaded at startup, overrides the environment)
- `.secret_key` (generated session secret when `SESSION_SECRET_KEY` is unset)

Because SSE connections and the summary cache live in memory, **the app must run as a single process**. Concurrency comes from threads; each open SSE stream holds one thread, so streams are capped by `SSE_MAX_CONNECTIONS` (default 20, below `GUNICORN_THREADS`, default 32).

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
| `NETWORK_TIMEOUT` | `60` | Process default socket timeout (bounds transcript fetches) |
| `SSE_MAX_CONNECTIONS` | `20` | |
| `GUNICORN_THREADS` | `32` | |
| `TTS_VOICE` | `en-US-Chirp3-HD-Zephyr` | |
| `WEBSHARE_PROXY_*` | – | Proxy for transcript fetching |
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
- `tests/test_dark_mode_integration.py`, `tests/test_theme_performance.py`, `tests/test_visual_dark_mode.py` – Playwright/theme tests (`make test-browser`)

Tests import `app` with `TESTING=true`, which skips real API client creation. Patch module globals such as `app.summary_cache`, `app.tts_client`, `ai_models.gemini_client`, `ai_models.openai_client`.

CI (`.github/workflows/tests.yml`): flake8 on the app modules, pytest with coverage, and a Docker build + `/health` smoke test.

## Security Notes
- Settings page never renders secret values; blank secret fields keep the current value.
- Error responses never include stack traces; details go to the server log.
- `voice_id` is allowlisted (`validate_voice_name`) before it becomes part of a cache filename.
- Login passcode comparison is constant-time (`hmac.compare_digest`).

## Known Limitations
- In-memory state means one process; scaling out needs shared storage (e.g. Redis/SQLite) for cache, sessions and SSE fan-out.
- `youtube-transcript-api` is pinned to 1.1.0 because `youtube_helpers.get_transcript` uses the static API removed in later releases.
- Long playlists are processed within a single request; the browser waits for the full response.
