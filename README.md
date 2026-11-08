<div align="center">

# 🎥 YouTube Summarizer

### A powerful Flask application for AI-powered YouTube video and playlist summarization

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.0.2-green.svg)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?logo=docker&logoColor=white)](https://www.docker.com/)

</div>

---

**YouTube Summarizer** is a Flask web application that generates AI-powered summaries of YouTube videos and playlists. The app extracts transcripts from YouTube videos, creates concise summaries using multiple AI models (Google Gemini and OpenAI GPT models), and can convert summaries to audio using Google's Text-to-Speech API.

## 📋 Table of Contents

- [Features](#-features)
- [Login Authentication (Optional)](#-login-authentication-optional)
- [Prerequisites](#-prerequisites)
- [Usage with Docker](#-usage-with-docker-recommended)
- [Usage without Docker](#-usage-without-docker)
- [How to Use](#-how-to-use)
- [Project Structure](#-project-structure)
- [API Requirements](#-api-requirements)
- [Troubleshooting](#-troubleshooting)
- [Testing](#-testing)
- [Contributing](#-contributing)
- [Changelog](CHANGELOG.md)

## ✨ Features

- 📹 **Video Summarization** - Generate AI-powered summaries for individual YouTube videos
- 📋 **Playlist Support** - Process and summarize entire YouTube playlists
- 🤖 **Multi-Model AI Support** - Choose from Google Gemini and OpenAI GPT models for summarization
- 🔊 **Audio Generation** - Convert summaries to MP3 audio files using Text-to-Speech
- 💾 **Smart Caching** - Store summaries and audio files to minimize API calls
- 🎨 **Clean Interface** - Simple, responsive web UI for easy interaction
- ⚡ **Batch Processing** - Handle multiple videos or playlists simultaneously
- 🔐 **Optional Authentication** - Secure your application with passcode-based login

## 🔒 Login Authentication (Optional)

YouTube Summarizer includes an optional login system to secure access to your application. This is particularly useful when deploying the application publicly or sharing it with a limited group of users.

### Security Features

- **Simple passcode authentication** - Single user access with a configurable passcode
- **Brute force protection** - Automatic IP-based lockout after failed attempts
- **Session management** - Secure session handling with configurable session keys
- **Rate limiting** - Configurable maximum attempts and lockout duration

### Environment Variables

Configure login functionality using these environment variables:

```bash
LOGIN_ENABLED=true                    # Enable/disable login (default: false)
LOGIN_CODE=your_secret_passcode      # The passcode users must enter
SESSION_SECRET_KEY=your_random_key   # Secret key for session encryption
MAX_LOGIN_ATTEMPTS=5                 # Failed attempts before lockout (default: 5)
LOCKOUT_DURATION=15                  # Lockout time in minutes (default: 15)
FLASK_DEBUG=false                    # Flask debug mode for `python app.py` (default: false; never enable in production)
```

### Setup Examples

**Docker Compose** - Add to your `.env` file:
```bash
GOOGLE_API_KEY=your_google_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
LOGIN_ENABLED=true
LOGIN_CODE=MySecurePasscode123
SESSION_SECRET_KEY=a-long-random-string-for-session-encryption
MAX_LOGIN_ATTEMPTS=3
LOCKOUT_DURATION=30
FLASK_DEBUG=false
```

**Manual Setup** - Export environment variables:
```bash
export LOGIN_ENABLED=true
export LOGIN_CODE="MySecurePasscode123"
export SESSION_SECRET_KEY="a-long-random-string-for-session-encryption"
export MAX_LOGIN_ATTEMPTS=3
export LOCKOUT_DURATION=30
export FLASK_DEBUG=false
```

### User Experience

When login is enabled:
- Users are redirected to `/login` when accessing the application
- After successful authentication, users can access all features normally
- Failed login attempts are tracked per IP address
- After exceeding max attempts, users are temporarily locked out
- Sessions persist until logout or browser closure

### Security Recommendations

- **Use a strong passcode** - Combine letters, numbers, and symbols
- **Generate a random session key** - Use a cryptographically secure random string
- **Configure appropriate lockout settings** - Balance security with user experience
- **Use HTTPS in production** - Encrypt all communication with SSL/TLS
- **Regularly rotate credentials** - Change passcode and session key periodically

### Testing Override

The test suite bypasses authentication. This requires both `TESTING=true` in the environment **and** a Flask app configured with `TESTING=True` (done by the test fixtures), so a stray `TESTING` variable on a server does not disable login.

## ⚙️ Deployment & Security Settings

| Variable | Default | Purpose |
|---|---|---|
| `DATA_DIR` | `data` in Docker, `.` otherwise | Where the summary cache, audio cache, login attempts, session secret and UI-saved settings live |
| `TRUST_PROXY_HOPS` | `0` | Number of reverse proxies in front of the app. Only then is `X-Forwarded-For` trusted for client IPs (login lockout). Leave at `0` when exposed directly |
| `ENABLE_DEBUG_ENDPOINTS` | `false` | Enables `/debug_transcript` |
| `MAX_TTS_CHARS` | `50000` | Maximum text length accepted by `/speak` |
| `NETWORK_TIMEOUT` | `60` | Default socket timeout (seconds) for network calls without their own timeout, e.g. transcript fetches |
| `SSE_MAX_CONNECTIONS` | `20` | Maximum concurrent progress streams (each holds a server thread) |
| `SUMMARY_WORKERS` | `2` | Background threads that process summary requests |
| `SUMMARY_REQUEST_TTL` | `3600` | Seconds finished summary requests stay retrievable |
| `SUMMARY_MAX_ACTIVE_PER_SESSION` | `3` | Summary requests one browser can have running at once |
| `GUNICORN_THREADS` | `32` | Request threads in the single gunicorn process |

Notes:
- **Settings page:** with login disabled, anyone who can reach the app can open it and change settings (enable login to restrict it). Secrets are never displayed; leave a secret field blank to keep its current value. Changes are written to `DATA_DIR/.env`, which is loaded at startup and overrides other environment values.
- **Session secret:** if `SESSION_SECRET_KEY` is not set, one is generated once and stored in `DATA_DIR/.secret_key`.
- **Single process:** the app keeps its state in memory, so `gunicorn_config.py` runs exactly one worker process with many threads. Do not raise the worker count.

## 🌐 Webshare Proxy Support

YouTube Summarizer supports using webshare proxies for fetching YouTube transcripts. This can help bypass IP restrictions, rate limiting, or geographic blocks that may prevent transcript retrieval from certain server environments.

### Proxy Configuration

Configure webshare proxy support using these environment variables:

```bash
WEBSHARE_PROXY_ENABLED=true                    # Enable/disable proxy (default: false)
WEBSHARE_PROXY_HOST=proxy.webshare.io         # Proxy server hostname
WEBSHARE_PROXY_PORT=8080                      # Proxy server port
WEBSHARE_PROXY_USERNAME=your_username         # Webshare proxy username
WEBSHARE_PROXY_PASSWORD=your_password         # Webshare proxy password
```

### Setup Examples

**Docker Compose** - Add to your `.env` file:
```bash
GOOGLE_API_KEY=your_google_api_key_here
WEBSHARE_PROXY_ENABLED=true
WEBSHARE_PROXY_HOST=proxy.webshare.io
WEBSHARE_PROXY_PORT=8080
WEBSHARE_PROXY_USERNAME=myusername
WEBSHARE_PROXY_PASSWORD=mypassword
```

**Manual Setup** - Export environment variables:
```bash
export WEBSHARE_PROXY_ENABLED=true
export WEBSHARE_PROXY_HOST="proxy.webshare.io"
export WEBSHARE_PROXY_PORT="8080"
export WEBSHARE_PROXY_USERNAME="myusername"
export WEBSHARE_PROXY_PASSWORD="mypassword"
```

### When to Use Proxies

Consider enabling proxy support when:
- Transcript fetching fails with "YouTube is temporarily blocking requests" errors
- Running the application on cloud servers (AWS EC2, Google Cloud, etc.)
- Experiencing rate limiting from YouTube's transcript API
- Working with videos that may have geographic restrictions

### Security Recommendations

- **Keep proxy credentials secure** - Store them in environment variables, not in code
- **Use reputable proxy providers** - Choose trusted services like Webshare.io
- **Monitor proxy usage** - Track bandwidth and request costs
- **Test thoroughly** - Verify transcript fetching works both with and without proxies

### Troubleshooting

If you experience issues with proxy configuration:
1. Verify all proxy environment variables are set correctly
2. Check proxy credentials with your webshare provider
3. Ensure the proxy service is active and has available bandwidth
4. Test without proxy first to isolate issues
5. Check application logs for proxy-related error messages

## 🔧 Prerequisites

- **Google API Key** (required) with access to:
  - YouTube Data API v3
  - Google Generative AI (Gemini)
  - Google Cloud Text-to-Speech API
- **OpenAI API Key** (optional) for GPT models

## 🐳 Usage with Docker (Recommended)

### 1. Clone the Repository
```bash
git clone <repository-url>
cd youtube-summarizer
```

### 2. Set Up Environment Variables
Create a `.env` file in the project root:
```bash
GOOGLE_API_KEY=your_google_api_key_here
OPENAI_API_KEY=your_openai_api_key_here  # Optional, for GPT models
```

### 3. Run with Docker Compose
```bash
mkdir -p data
docker compose up -d
```

The application will be available at `http://localhost:5001`

### 4. Stop the Application
```bash
docker compose down
```

### Docker Notes
- Summaries, audio and settings are persisted in the `./data` directory on your host machine
- The container runs as a non-root user (uid 1000); on Linux make sure `./data` is writable by that uid
- With Podman on SELinux hosts, add `:Z` to the volume in `docker-compose.yml`
- The container restarts automatically and has a `/health` health check
- Logs can be viewed with: `docker compose logs -f`

## 💻 Usage without Docker

### 1. Clone the Repository
```bash
git clone <repository-url>
cd youtube-summarizer
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables
Create a `.env` file or export the environment variables:
```bash
export GOOGLE_API_KEY=your_google_api_key_here
export OPENAI_API_KEY=your_openai_api_key_here  # Optional, for GPT models
```

On Windows:
```cmd
set GOOGLE_API_KEY=your_google_api_key_here
set OPENAI_API_KEY=your_openai_api_key_here
```

### 5. Run the Application

For development:
```bash
python app.py
```

For production (using Gunicorn):
```bash
gunicorn -c gunicorn_config.py app:app
```

The application will be available at `http://localhost:5001`

## 🚀 How to Use

1. **Open the Web Interface**: Navigate to `http://localhost:5001` in your browser

2. **Login (if enabled)**: 
   - If authentication is enabled, you'll be redirected to the login page
   - Enter the configured passcode to access the application
   - You'll be automatically redirected to the main interface

3. **Enter YouTube URLs**: 
   - Paste one or more YouTube video URLs
   - Playlist URLs are also supported
   - Multiple URLs can be entered on separate lines

4. **Generate Summaries**: Click the "Summarize" button to process the videos. Work runs in the background, so long playlists are not cut off by proxy timeouts; each summary card appears as soon as it is ready

5. **View Results**: 
   - Summaries appear below each video
   - Cached summaries are displayed in the sidebar
   - Click the speaker icon to generate and play audio

## 📁 Project Structure

```
youtube-summarizer/
├── app.py                # Flask app: routes, settings, client setup
├── ai_models.py          # Model registry and Gemini/OpenAI summary generation
├── auth.py               # Passcode login, lockout, require_auth
├── cache.py              # Summary cache load/save (atomic)
├── sse.py                # Server-Sent Events progress stream
├── summary_jobs.py       # Background summary requests (thread pool + request store)
├── tts_helpers.py        # Text-to-speech synthesis helpers
├── voice_config.py       # TTS voices and audio cache management
├── youtube_helpers.py    # YouTube API and transcript helpers
├── gunicorn_config.py    # Production server config (1 process, threads)
├── templates/            # index, login, settings pages
├── static/               # CSS, page and theme JS, icons
├── tests/                # pytest suite
├── Dockerfile
└── docker-compose.yml
```

## 🔑 API Requirements

This project supports multiple AI providers. You can use either or both:

### Google APIs (Required for YouTube access and Gemini models)
1. **YouTube Data API v3** - For fetching video metadata and playlist information
2. **Generative AI API** - For accessing Google's Gemini models
3. **Cloud Text-to-Speech API** - For converting summaries to audio

To set up Google APIs:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the required APIs
4. Create an API key and add it as `GOOGLE_API_KEY` to your `.env` file

### OpenAI API (Optional, for GPT models)
1. **OpenAI API** - For accessing GPT-4o, GPT-4 Turbo, and GPT-3.5 Turbo models

To set up OpenAI API:
1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Create an account and generate an API key
3. Add it as `OPENAI_API_KEY` to your `.env` file

### Available AI Models
- **Google Gemini 2.5 Flash** - Fast and efficient (default)
- **Google Gemini 2.5 Pro** - More capable for complex content
- **OpenAI GPT-5** - Most advanced AI model available
- **OpenAI GPT-5 Mini** - Faster GPT-5 variant
- **OpenAI GPT-4o** - Advanced multimodal capabilities
- **OpenAI GPT-4o Mini** - Fast and cost-effective

## 🛠️ Troubleshooting

### Common Issues

1. **"GOOGLE_API_KEY environment variable is not set"**
   - Ensure your `.env` file exists and contains your API key
   - For Docker: Make sure the `.env` file is in the same directory as `docker-compose.yml`

2. **"No transcripts are available for this video"**
   - The video doesn't have captions/transcripts available
   - The video might be private or age-restricted

3. **API Quota Errors**
   - Check your Google Cloud Console for API usage limits
   - The app uses caching to minimize API calls

4. **Port Already in Use**
   - Change the port in `docker-compose.yml` or when running the app
   - Example: `python app.py --port 5002`

### Login-Related Issues

5. **Stuck on login page / Invalid passcode**
   - Verify `LOGIN_CODE` environment variable is set correctly
   - Ensure `LOGIN_ENABLED=true` is set
   - Check for typos in the passcode (case-sensitive)

6. **"Too many failed attempts" / Account locked**
   - Wait for the lockout duration to expire (default: 15 minutes)
   - Or restart the application to clear the lockout
   - Reduce `MAX_LOGIN_ATTEMPTS` or increase `LOCKOUT_DURATION` if needed

7. **Session expires immediately**
   - Ensure `SESSION_SECRET_KEY` is set and consistent
   - Check that cookies are enabled in your browser
   - Verify the session key doesn't contain special characters that might cause issues


## 🧪 Testing

The project includes comprehensive unit and integration tests.

### Quick Test
```bash
make quick-test   # core app tests
make test         # full suite
```

### Full Test Suite with Coverage
```bash
make coverage
```

Browser (Playwright) tests are skipped unless Playwright and its browsers are installed:
```bash
pip install playwright && playwright install chromium
make test-browser
```

### Test Structure

- `tests/test_app.py` - Flask endpoint tests
- `tests/test_transcript_and_summary.py` - Transcript and summary generation tests
- `tests/test_cache.py` - Cache functionality tests
- `tests/test_integration.py` - End-to-end integration tests
- `tests/test_sse.py` - Server-Sent Events registry and formatting
- `tests/test_pagination.py` - Cached summary pagination

## 🔍 Code Quality

### Run All Quality Checks
```bash
./run_quality_checks.sh
# or
make quality
```

### Auto-fix Formatting Issues
```bash
./run_quality_checks.sh --fix
# or
make fix
```

### Individual Checks
```bash
make format   # Check code formatting
make lint     # Run linting (pylint, flake8)
make test     # Run tests only
```

### Development Commands
Use the Makefile for convenient development commands:
```bash
make help      # Show all available commands
make install   # Install all dependencies
make run       # Run Flask app locally
make clean     # Clean up cache files
```

### Quality Tools
- **Black** - Code formatting
- **isort** - Import sorting
- **Flake8** - Style guide enforcement
- **Pylint** - Static code analysis
- **Bandit** - Security linting
- **Coverage** - Test coverage reports

## 🤝 Contributing

Feel free to submit issues, fork the repository, and create pull requests for any improvements. Please ensure all tests pass before submitting a PR. 