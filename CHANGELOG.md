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

### Changed
- AI models updated: `gemini-3.5-flash-lite` (new default), `gemini-3.8-flash`, `gemini-4-argon`, `gpt-6-luna`, `gpt-6.1-terra`, `gpt-6.1-sol`. Retired keys (`gemini-2.5-*`, `gpt-5`, `gpt-5-mini`, `gpt-4o*`) map to successors instead of failing; the model selector is built from `/api_status`
- OpenAI calls set `reasoning_effort="low"` and a 25,000-token completion budget so reasoning tokens can no longer leave the summary empty
- Docker image and CI use Python 3.13 (was 3.11); CI also runs the tests on 3.9. `coverage` bumped to 7.6.1, the first release with Python 3.13 wheels
- Docker image runs gunicorn with `gunicorn_config.py` (1 process, gthread) as a non-root user, with a health check
- Gemini calls use the `google-genai` SDK (replaces deprecated `google-generativeai`)
- Settings saved in the UI persist across restarts (`DATA_DIR/.env` is loaded at startup); generated session secret persists in `DATA_DIR/.secret_key`
- SSE moved to `sse.py`; idle streams are no longer dropped every 5 minutes

### Removed
- Unused async worker system (`worker_manager`, `job_queue`, `job_models`, `job_state`, `error_handler`, `sse_manager`, `/summarize_async`, `/jobs`) and its client scripts and tests
- `Dockerfile.sse`, `docker-compose-sse.yml`, `docker-compose-podman.yml`, `docker/`, `nginx-sse-fixed.conf`

### Fixed
- Deleting a summary now deletes its cached audio

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