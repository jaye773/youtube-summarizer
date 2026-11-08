# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- Settings page no longer renders API keys, login code, session secret or proxy password (blank fields keep the current value)
- Error responses no longer include stack traces
- Removed `/debug_model`, `/events/status`, `/events/broadcast` and `/sse-test`; `/debug_transcript` requires `ENABLE_DEBUG_ENDPOINTS=true`
- `X-Forwarded-For` is only trusted with `TRUST_PROXY_HOPS`; `TESTING` alone no longer disables auth
- `/preview-voice` validates `voice_id` (path traversal)
- Per-client-IP rate limits (Flask-Limiter) on `/summarize`, `/speak` + `/preview-voice` and `POST /login`, configurable via `RATE_LIMIT_SUMMARIZE`, `RATE_LIMIT_TTS`, `RATE_LIMIT_LOGIN`, `RATE_LIMIT_ENABLED`; 429 responses are JSON
- CSRF hardening: session cookie is `SameSite=Lax` (optional `SESSION_COOKIE_SECURE`); POST/PUT/PATCH/DELETE require `Content-Type: application/json` (415 otherwise) and `/settings`, `/delete_summary` no longer parse non-JSON bodies

### Changed
- Docker image runs gunicorn with `gunicorn_config.py` (1 process, gthread) as a non-root user, with a health check
- Gemini calls use the `google-genai` SDK (replaces deprecated `google-generativeai`)
- Settings saved in the UI persist across restarts (`DATA_DIR/.env` is loaded at startup); generated session secret persists in `DATA_DIR/.secret_key`
- SSE moved to `sse.py`; idle streams are no longer dropped every 5 minutes
- Upgraded `youtube-transcript-api` 1.1.0 → 1.2.4 (instance API, `NETWORK_TIMEOUT` applied per request, clearer errors for blocked/unavailable/age-restricted videos); webshare proxy also supports rotating residential mode when `WEBSHARE_PROXY_HOST`/`PORT` are unset, and the proxy line is logged once instead of on every fetch
- Summaries are stored in SQLite (`DATA_DIR/summaries.db`, WAL mode) instead of `summary_cache.json`; each write commits one row instead of rewriting the whole file, and listing/search query the database. An existing `summary_cache.json` is imported automatically on first start and renamed to `summary_cache.json.migrated`
- Page JavaScript moved out of the templates into `static/js/` (`index.js`, `login.js`, `settings.js`, `theme-init.js`, `settings-theme.js`); only the tiny theme-flash guard stays inline in `<head>`

### Removed
- Unused async worker system (`worker_manager`, `job_queue`, `job_models`, `job_state`, `error_handler`, `sse_manager`, `/summarize_async`, `/jobs`) and its client scripts and tests
- `Dockerfile.sse`, `docker-compose-sse.yml`, `docker-compose-podman.yml`, `docker/`, `nginx-sse-fixed.conf`

### Fixed
- Deleting a summary now deletes its cached audio
- Long playlists no longer depend on one long HTTP request (which reverse proxies with a 60 s read timeout would cut off)

### Added
- Background summaries: `POST /summarize/start` returns `202 {request_id}` immediately and the work runs on a small thread pool (`SUMMARY_WORKERS`, default 2); `GET /summarize/<request_id>` returns status and results so far (only to the session that started it). Each result is pushed over SSE as a `summary_result` event and completion as `summary_done`, so cards render as they finish. The UI uses this flow, polls when SSE is unavailable, and falls back to `POST /summarize` on older servers. `POST /summarize` still works synchronously
- New settings: `SUMMARY_WORKERS`, `SUMMARY_REQUEST_TTL`, `SUMMARY_MAX_REQUESTS`, `SUMMARY_MAX_ACTIVE_PER_SESSION`

### Added
- **Webshare Proxy Support**: Added support for using webshare proxies for YouTube transcript fetching
  - New environment variables: `WEBSHARE_PROXY_ENABLED`, `WEBSHARE_PROXY_HOST`, `WEBSHARE_PROXY_PORT`, `WEBSHARE_PROXY_USERNAME`, `WEBSHARE_PROXY_PASSWORD`
  - Helps bypass IP restrictions, rate limiting, and geographic blocks when fetching transcripts
  - Comprehensive test suite for proxy configuration and functionality
  - Documentation added to README.md with setup examples and troubleshooting guide

### Changed
### Deprecated
### Removed
### Fixed
- Fixed audio cache directory creation test that was failing in test environment
### Security

## [1.0.0] - 2025-06-21

### Added
- Initial release of YouTube Summarizer
- Support for summarizing individual YouTube videos
- Support for summarizing entire YouTube playlists
- AI-powered summaries using Google's Gemini AI model
- Text-to-Speech audio generation for summaries
- Smart caching system to minimize API calls
- Clean, responsive web interface
- Docker and Docker Compose support for easy deployment
- Comprehensive test suite with coverage reporting
- GitHub Actions CI/CD pipeline
- Quality checks including Black, isort, Flake8, Pylint, and Bandit
- Detailed documentation with troubleshooting guide

### Security
- Environment variable based API key management
- No hardcoded secrets or credentials
- Proper input validation and error handling

### Performance
- Efficient caching mechanism for summaries and audio files
- Batch processing support for multiple videos
- Optimized Docker image with multi-stage builds 