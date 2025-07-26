# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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