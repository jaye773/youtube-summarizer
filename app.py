import hmac  # For constant-time passcode comparison
import html  # For HTML escaping user inputs
import os
import socket
import traceback
import uuid
from datetime import datetime

import httplib2
import openai
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from google.api_core.client_options import ClientOptions
from google.cloud import texttospeech
from googleapiclient.discovery import build
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from voice_config import (
    AVAILABLE_VOICES,
    CACHE_CONFIG,
    DEFAULT_VOICE,
    cleanup_audio_cache,
    get_fallback_voice,
    get_optimized_cache_key,
    get_voice_with_fallback,
    get_voices_by_tier,
    should_cleanup_cache,
    validate_voice_name,
)

import auth
from auth import (
    clean_expired_attempts,
    configure as configure_auth,
    is_ip_locked_out,
    load_login_attempts,
    record_failed_attempt,
    require_auth,
    reset_failed_attempts,
    save_login_attempts,
)

import youtube_helpers
from youtube_helpers import (
    clean_youtube_url,
    get_playlist_id,
    get_video_id,
    get_video_details,
    get_videos_from_playlist,
    get_transcript,
)

from tts_helpers import clean_text_for_tts, synthesize_audio
from cache import build_cache_entry, load_summary_cache, save_summary_cache
import ai_models
import sse
from ai_models import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    generate_summary,
    generate_summary_gemini,
    generate_summary_openai,
    get_summary_prompt,
)

# --- CONFIGURATION ---
# Use data directory if running in Docker/Podman, otherwise use current directory
DATA_DIR = os.environ.get("DATA_DIR", "data" if os.path.exists("/.dockerenv") else ".")
os.makedirs(DATA_DIR, exist_ok=True)

# Load configuration files before any setting is read:
#  1. the project .env (never overrides variables already set in the environment);
#  2. DATA_DIR/.env, written by the settings page, which DOES override so that
#     changes saved in the UI survive a restart.
if not os.environ.get("TESTING"):
    load_dotenv()
    load_dotenv(os.path.join(DATA_DIR, ".env"), override=True)

app = Flask(__name__)

# Only trust X-Forwarded-* when running behind a known number of reverse proxies;
# otherwise any client could spoof its IP and bypass the login lockout.
TRUST_PROXY_HOPS = int(os.environ.get("TRUST_PROXY_HOPS", "0"))
if TRUST_PROXY_HOPS > 0:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=TRUST_PROXY_HOPS, x_proto=TRUST_PROXY_HOPS, x_host=TRUST_PROXY_HOPS)

# Diagnostic endpoints (/debug_transcript) are off unless explicitly enabled
DEBUG_ENDPOINTS_ENABLED = os.environ.get("ENABLE_DEBUG_ENDPOINTS", "false").lower() == "true"

# Upper bound on text sent to text-to-speech in one request (cost/abuse guard)
MAX_TTS_CHARS = int(os.environ.get("MAX_TTS_CHARS", "50000"))

# Process-wide default socket timeout. Some network calls (notably the YouTube
# transcript fetch) expose no timeout parameter; this keeps them from hanging
# forever. Clients that set their own timeouts (OpenAI, httplib2) are unaffected.
socket.setdefaulttimeout(int(os.environ.get("NETWORK_TIMEOUT", "60")))

# --- WEBSHARE PROXY CONFIGURATION ---
WEBSHARE_PROXY_ENABLED = os.environ.get("WEBSHARE_PROXY_ENABLED", "false").lower() == "true"
WEBSHARE_PROXY_HOST = os.environ.get("WEBSHARE_PROXY_HOST")
WEBSHARE_PROXY_PORT = os.environ.get("WEBSHARE_PROXY_PORT")
WEBSHARE_PROXY_USERNAME = os.environ.get("WEBSHARE_PROXY_USERNAME")
WEBSHARE_PROXY_PASSWORD = os.environ.get("WEBSHARE_PROXY_PASSWORD")


def get_proxy_config():
    """Get proxy configuration if webshare proxy is enabled and properly configured"""
    if not WEBSHARE_PROXY_ENABLED:
        return None

    if not all(
        [
            WEBSHARE_PROXY_HOST,
            WEBSHARE_PROXY_PORT,
            WEBSHARE_PROXY_USERNAME,
            WEBSHARE_PROXY_PASSWORD,
        ]
    ):
        print(
            "⚠️ Webshare proxy is enabled but missing required configuration. "
            "Required: WEBSHARE_PROXY_HOST, WEBSHARE_PROXY_PORT, WEBSHARE_PROXY_USERNAME, WEBSHARE_PROXY_PASSWORD"
        )
        return None

    proxy_url = (
        f"http://{WEBSHARE_PROXY_USERNAME}:{WEBSHARE_PROXY_PASSWORD}" f"@{WEBSHARE_PROXY_HOST}:{WEBSHARE_PROXY_PORT}"
    )
    proxies = {"http": proxy_url, "https": proxy_url}
    print(f"✅ Using webshare proxy: {WEBSHARE_PROXY_USERNAME}@{WEBSHARE_PROXY_HOST}:{WEBSHARE_PROXY_PORT}")
    return proxies


# Inject proxy config function into youtube_helpers now that it is defined
youtube_helpers.set_proxy_config_func(get_proxy_config)


# --- CACHE CONFIGURATION ---
SUMMARY_CACHE_FILE = os.path.join(DATA_DIR, "summary_cache.json")
LOGIN_ATTEMPTS_FILE = os.path.join(DATA_DIR, "login_attempts.json")
AUDIO_CACHE_DIR = os.path.join(DATA_DIR, "audio_cache")

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
print(f"✅ Audio cache directory is set to: '{AUDIO_CACHE_DIR}/'")


summary_cache = load_summary_cache(SUMMARY_CACHE_FILE)
print(f"✅ Loaded {len(summary_cache)} summaries from cache.")


# --- ENVIRONMENT VARIABLE PERSISTENCE ---
def save_env_to_file(env_vars, filename=".env"):
    """Save environment variables to a .env file for persistence"""
    try:
        env_file_path = os.path.join(DATA_DIR, filename)

        # Read existing .env file if it exists
        existing_vars = {}
        if os.path.exists(env_file_path):
            with open(env_file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        existing_vars[key] = value

        # Update with new variables
        existing_vars.update(env_vars)

        # Write back to file
        with open(env_file_path, "w") as f:
            f.write("# YouTube Summarizer Environment Variables\n")
            f.write(f"# Updated: {datetime.now().isoformat()}\n\n")

            for key, value in sorted(existing_vars.items()):
                # Properly escape quotes and backslashes in values
                value = value.replace("\\", "\\\\").replace('"', '\\"')
                f.write(f'{key}="{value}"\n')

        print(f"✅ Environment variables saved to {env_file_path}")
        return True

    except Exception as e:
        print(f"❌ Failed to save environment variables: {e}")
        return False


# --- LOGIN CONFIGURATION ---
LOGIN_ENABLED = os.environ.get("LOGIN_ENABLED", "false").lower() == "true"
LOGIN_CODE = os.environ.get("LOGIN_CODE", "")
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "")
MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
LOCKOUT_DURATION = int(os.environ.get("LOCKOUT_DURATION", "15"))  # minutes

# --- TTS CONFIGURATION ---
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-Chirp3-HD-Zephyr")


def load_or_create_secret_key(data_dir):
    """Return a session secret that is stable across restarts.

    Used when SESSION_SECRET_KEY is not configured: a random key is generated
    once and stored in DATA_DIR/.secret_key (mode 0600). A per-boot random key
    would log everyone out on every restart.
    """
    key_path = os.path.join(data_dir, ".secret_key")
    try:
        with open(key_path, "r") as f:
            key = f.read().strip()
            if key:
                return key
    except FileNotFoundError:
        pass
    key = os.urandom(32).hex()
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key)
    return key


# Configure Flask session
if LOGIN_ENABLED and not LOGIN_CODE:
    print("Warning: LOGIN_CODE not set. Login functionality will not work properly.")

if SESSION_SECRET_KEY:
    app.secret_key = SESSION_SECRET_KEY
elif os.environ.get("TESTING"):
    app.secret_key = os.urandom(24)
else:
    app.secret_key = load_or_create_secret_key(DATA_DIR)

print(f"✅ Login system {'enabled' if LOGIN_ENABLED else 'disabled'}")
if LOGIN_ENABLED:
    print(f"✅ Max login attempts: {MAX_LOGIN_ATTEMPTS}")
    print(f"✅ Lockout duration: {LOCKOUT_DURATION} minutes")

# Initialise the auth module with the current config values
configure_auth(
    login_attempts_file=LOGIN_ATTEMPTS_FILE,
    max_login_attempts=MAX_LOGIN_ATTEMPTS,
    lockout_duration=LOCKOUT_DURATION,
    login_enabled=LOGIN_ENABLED,
)


# --- AI MODEL CONFIGURATION ---
def create_youtube_client_with_timeout(api_key, timeout=30):
    """Create a YouTube API client with custom timeout settings"""
    # Create an httplib2 instance with timeout
    http = httplib2.Http(timeout=timeout)

    # Build the YouTube client with the configured http instance
    return build("youtube", "v3", developerKey=api_key, http=http)


# --- API CLIENT INITIALIZATION ---
google_api_key = os.environ.get("GOOGLE_API_KEY")
openai_api_key = os.environ.get("OPENAI_API_KEY")
tts_client = None
youtube = None
gemini_client = None
openai_client = None


def init_google_clients(api_key):
    """(Re)create the Google TTS, YouTube and Gemini clients and inject them into helper modules."""
    global tts_client, youtube, gemini_client
    try:
        tts_client = texttospeech.TextToSpeechClient(client_options=ClientOptions(api_key=api_key))
        youtube = create_youtube_client_with_timeout(api_key, timeout=30)
        gemini_client = ai_models.create_gemini_client(api_key)
    except Exception as e:
        print(f"Warning: Could not configure Google APIs. Error: {e}")
        return False
    youtube_helpers.set_youtube_client(youtube)
    ai_models.set_clients(gemini=gemini_client)
    print("✅ Google APIs initialized successfully")
    return True


def init_openai_client(api_key):
    """(Re)create the OpenAI client and inject it into ai_models."""
    global openai_client
    try:
        openai_client = openai.OpenAI(api_key=api_key)
    except Exception as e:
        print(f"Warning: Could not configure OpenAI API. Error: {e}")
        return False
    ai_models.set_clients(openai_cli=openai_client)
    print("✅ OpenAI API initialized successfully")
    return True


if google_api_key and not os.environ.get("TESTING"):
    init_google_clients(google_api_key)
elif not google_api_key and not os.environ.get("TESTING"):
    print("Warning: GOOGLE_API_KEY environment variable is not set. Google services will be unavailable.")

if openai_api_key and not os.environ.get("TESTING"):
    init_openai_client(openai_api_key)
elif not openai_api_key and not os.environ.get("TESTING"):
    print("Warning: OPENAI_API_KEY environment variable is not set. OpenAI models will be unavailable.")

# For testing, create clients even without API keys
if os.environ.get("TESTING"):
    try:
        if not gemini_client:
            gemini_client = ai_models.create_gemini_client("test-key")
        if not openai_client:
            openai_client = openai.OpenAI(api_key="test-key")
    except Exception:
        pass
    ai_models.set_clients(gemini=gemini_client, openai_cli=openai_client)


# --- HELPER FUNCTIONS ---
def get_client_ip():
    """Return the client IP address.

    X-Forwarded-For is honoured only via ProxyFix when TRUST_PROXY_HOPS is set,
    so clients cannot spoof their address by sending the header themselves.
    """
    return request.remote_addr or "127.0.0.1"


def prepare_tts_text(text):
    """Normalise text exactly as /speak does before synthesis and cache-keying."""
    return clean_text_for_tts(html.escape(text))


def speech_cache_path(voice_id, prepared_text, prefix=""):
    """Path of the cached MP3 for a voice + prepared text."""
    return os.path.join(AUDIO_CACHE_DIR, f"{prefix}{get_optimized_cache_key(voice_id, prepared_text)}.mp3")


SECRET_SETTINGS = {
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "LOGIN_CODE",
    "SESSION_SECRET_KEY",
    "WEBSHARE_PROXY_PASSWORD",
}


# --- API ENDPOINTS ---


@app.before_request
def ensure_session_id():
    """Assign a stable per-session id used to target SSE events.

    Set on every request (the short-circuit means only the first one writes)
    so the cookie is in place before the browser opens the /events stream.
    Without this, SSE connections register with session_id=None and progress
    events get broadcast to every connected client instead of just the user
    who started the job.
    """
    if not session.get("session_id"):
        session["session_id"] = str(uuid.uuid4())


@app.route("/health")
def health_check():
    """Lightweight, unauthenticated liveness endpoint for container health checks."""
    return jsonify({"status": "ok", "sse_connections": sse.connection_count()}), 200


@app.route("/")
@require_auth
def home():
    return render_template("index.html")


@app.route("/login")
def login_page():
    """Serve the login page"""
    if not LOGIN_ENABLED:
        return redirect(url_for("home"))

    # If already authenticated, redirect to home
    if session.get("authenticated", False):
        return redirect(url_for("home"))

    return render_template("login.html")


# --- AUTHENTICATION ENDPOINTS ---
@app.route("/login", methods=["POST"])
def login():
    """Authenticate user with passcode"""
    if not LOGIN_ENABLED:
        return jsonify({"error": "Login system is disabled"}), 404

    # Get client IP address
    client_ip = get_client_ip()

    # Check if IP is locked out
    is_locked, remaining_minutes = is_ip_locked_out(client_ip)
    if is_locked:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Too many failed attempts. Please try again in {remaining_minutes} minutes.",
                    "locked_until_minutes": remaining_minutes,
                }
            ),
            429,
        )  # Too Many Requests

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON in request body"}), 400

        passcode = data.get("passcode", "").strip()
        if not passcode:
            return jsonify({"error": "Passcode is required"}), 400

        # Constant-time comparison to avoid leaking the passcode via timing.
        # (The passcode is never reflected back, so there's no XSS reason to
        # html.escape it here — and escaping broke codes containing & < > " '.)
        if hmac.compare_digest(passcode.encode("utf-8"), (LOGIN_CODE or "").encode("utf-8")):
            # Reset failed attempts on successful login
            reset_failed_attempts(client_ip)
            session["authenticated"] = True
            return jsonify({"success": True, "message": "Successfully logged in"})
        else:
            # Record failed attempt
            was_locked_out = record_failed_attempt(client_ip)

            if was_locked_out:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": f"Too many failed attempts. Account locked for {LOCKOUT_DURATION} minutes.",
                            "locked_until_minutes": LOCKOUT_DURATION,
                        }
                    ),
                    429,
                )  # Too Many Requests
            else:
                # Get current attempt count for feedback
                attempts_data = load_login_attempts()
                current_count = attempts_data.get(client_ip, {}).get("count", 0)
                remaining_attempts = MAX_LOGIN_ATTEMPTS - current_count

                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Invalid passcode",
                            "remaining_attempts": remaining_attempts,
                        }
                    ),
                    401,
                )

    except Exception as e:
        return jsonify({"error": f"Login failed: {str(e)}"}), 500


@app.route("/logout", methods=["POST"])
def logout():
    """Clear session and logout"""
    if not LOGIN_ENABLED:
        return jsonify({"error": "Login system is disabled"}), 404

    session.pop("authenticated", None)
    return jsonify({"success": True, "message": "Successfully logged out"})


@app.route("/login_status", methods=["GET"])
def login_status():
    """Check current authentication status"""
    if not LOGIN_ENABLED:
        return jsonify(
            {
                "login_enabled": False,
                "authenticated": True,  # Always authenticated when login is disabled
                "message": "Login system is disabled",
            }
        )

    is_authenticated = session.get("authenticated", False)
    return jsonify({"login_enabled": True, "authenticated": is_authenticated})


# --- SSE ENDPOINTS ---


@app.route("/events")
@require_auth
def sse_events():
    """Server-Sent Events stream of summary progress for the current session."""
    subscriptions = {sub.strip() for sub in request.args.get("subscribe", "").split(",") if sub.strip()}
    connection = sse.register(session.get("session_id"), get_client_ip(), subscriptions or None)
    if connection is None:
        return jsonify({"error": "Too many open event streams"}), 503
    return Response(sse.stream(connection), mimetype="text/event-stream", headers=sse.STREAM_HEADERS)


@app.route("/get_cached_summaries", methods=["GET"])
@require_auth
def get_cached_summaries():
    # Get parameters from query string
    page = request.args.get("page", type=int)
    per_page = request.args.get("per_page", type=int)
    limit = request.args.get("limit", type=int)  # Backward compatibility

    # Determine if this is a pagination request or legacy request
    is_pagination_request = page is not None or per_page is not None

    if not summary_cache:
        if is_pagination_request:
            return jsonify(
                {
                    "summaries": [],
                    "total": 0,
                    "page": page or 1,
                    "per_page": per_page or 10,
                    "total_pages": 0,
                }
            )
        else:
            return jsonify([])

    # Set defaults for pagination parameters
    if page is None:
        page = 1
    if per_page is None:
        per_page = 10

    # Validate pagination parameters
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 10
    elif per_page > 100:  # Cap at 100 to prevent performance issues
        per_page = 100

    cached_list = [
        {
            "type": "video",
            "video_id": video_id,
            "title": d["title"],
            "thumbnail_url": d["thumbnail_url"],
            "summary": d["summary"],
            "summarized_at": d.get("summarized_at"),
            "video_url": d.get("video_url"),
            "error": None,
        }
        for video_id, d in summary_cache.items()
    ]
    cached_list.sort(key=lambda x: x.get("summarized_at", "1970-01-01T00:00:00.000000"), reverse=True)

    total = len(cached_list)

    # Handle backward compatibility with limit parameter
    if limit is not None:
        if limit == 0:
            cached_list = []
        elif limit > 0:
            cached_list = cached_list[:limit]
        # Return old format for backward compatibility
        return jsonify(cached_list)

    # If no pagination parameters were provided, return old format for backward compatibility
    if not is_pagination_request:
        return jsonify(cached_list)

    # Calculate pagination
    total_pages = (total + per_page - 1) // per_page if total > 0 else 0
    start_index = (page - 1) * per_page
    end_index = start_index + per_page

    paginated_list = cached_list[start_index:end_index]

    return jsonify(
        {
            "summaries": paginated_list,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }
    )


@app.route("/search_summaries", methods=["GET"])
@require_auth
def search_summaries():
    query = request.args.get("q", "").strip()
    if not query:
        return (
            jsonify({"error": "Query parameter 'q' is required and cannot be empty"}),
            400,
        )

    # Sanitize search query to prevent XSS
    query = html.escape(query)

    if not summary_cache:
        return jsonify([])

    # Perform case-insensitive search in both title and summary
    results = []
    for video_id, data in summary_cache.items():
        title = data.get("title", "").lower()
        summary = data.get("summary", "").lower()
        query_lower = query.lower()

        if query_lower in title or query_lower in summary:
            results.append(
                {
                    "video_id": video_id,
                    "title": data["title"],
                    "thumbnail_url": data["thumbnail_url"],
                    "summary": data["summary"],
                    "summarized_at": data.get("summarized_at"),
                    "video_url": data.get("video_url"),
                }
            )

    # Sort by date (most recent first)
    results.sort(key=lambda x: x.get("summarized_at", "1970-01-01T00:00:00.000000"), reverse=True)

    return jsonify(results)


@app.route("/api_status", methods=["GET"])
def api_status():
    """Return the status of various API components"""
    status = {
        "google_api_key_set": bool(google_api_key),
        "openai_api_key_set": bool(openai_api_key),
        "youtube_client_initialized": youtube is not None,
        "tts_client_initialized": tts_client is not None,
        "gemini_model_initialized": gemini_client is not None,
        "openai_client_initialized": openai_client is not None,
        "available_models": list(AVAILABLE_MODELS.keys()),
        "testing_mode": bool(os.environ.get("TESTING")),
    }
    return jsonify(status)


@app.route("/debug_transcript", methods=["GET"])
@require_auth
def debug_transcript():
    """Debug endpoint to check transcript retrieval for a specific video"""
    if not DEBUG_ENDPOINTS_ENABLED:
        return jsonify({"error": "Endpoint not found"}), 404

    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL parameter is required"}), 400

    # Sanitize URL input to prevent XSS
    url = html.escape(url)

    video_id = get_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400

    # Get video details
    details = get_video_details([video_id]).get(video_id, {})
    video_title = details.get("title", "Unknown Title")

    # Try to get transcript
    transcript, error = get_transcript(video_id)

    result = {
        "video_id": video_id,
        "video_title": video_title,
        "transcript_success": transcript is not None,
        "transcript_length": len(transcript) if transcript else 0,
        "error": error,
    }

    if transcript:
        result["transcript_preview"] = transcript[:200] + "..." if len(transcript) > 200 else transcript

    return jsonify(result)


def _notify_progress(session_id, data):
    """Send a summary_progress SSE notification."""
    sse.broadcast(
        "summary_progress", data,
        session_filter=session_id,
        subscription_filter="summary_progress",
    )


def _notify_complete(session_id, data):
    """Send a summary_complete SSE notification."""
    sse.broadcast(
        "summary_complete", data,
        session_filter=session_id,
        subscription_filter="summary_complete",
    )


def _summarize_and_cache(vid_id, vid_title, thumbnail_url, model_key):
    """Fetch transcript, generate summary, and cache the result.

    Returns:
        Tuple of (summary_text_or_None, error_string_or_None).
    """
    transcript, err = get_transcript(vid_id)
    summary, err = (None, err) if err else generate_summary(transcript, vid_title, model_key)

    if summary and not err:
        summary_cache[vid_id] = build_cache_entry(vid_title, summary, thumbnail_url, vid_id, model_key)
        save_summary_cache(summary_cache, SUMMARY_CACHE_FILE)

    return summary, err


def _process_playlist_url(url, playlist_id, model_key, session_id, processed_count):
    """Process a playlist URL and return (result_dict, videos_processed_count)."""
    if not youtube:
        return {"type": "error", "url": url, "error": "YouTube API client not initialized"}, 0

    pl_meta_request = youtube.playlists().list(part="snippet", id=playlist_id)
    pl_meta_response = pl_meta_request.execute()
    if not pl_meta_response.get("items"):
        return {"type": "error", "url": url, "error": "Could not find this playlist."}, 0

    playlist_title = pl_meta_response["items"][0]["snippet"]["title"]
    playlist_items, error = get_videos_from_playlist(playlist_id)
    if error:
        return {"type": "playlist", "title": playlist_title, "error": error, "summaries": []}, 0

    total_videos = len(playlist_items)
    _notify_progress(session_id, {
        "status": "processing",
        "message": f"Processing playlist with {total_videos} videos",
        "progress": processed_count,
        "total": processed_count + total_videos,
        "current_playlist": playlist_title,
    })

    playlist_summaries = []
    for index, item in enumerate(playlist_items):
        snippet = item.get("snippet", {})
        vid_id = snippet.get("resourceId", {}).get("videoId")
        vid_title = snippet.get("title", "Unknown Title")
        thumbnail_url = snippet.get("thumbnails", {}).get("medium", {}).get("url")

        _notify_progress(session_id, {
            "status": "processing",
            "message": f"Processing: {vid_title[:50]}{'...' if len(vid_title) > 50 else ''}",
            "progress": processed_count + index + 1,
            "total": processed_count + total_videos,
            "current_video": {"id": vid_id, "title": vid_title, "playlist": playlist_title},
        })

        if vid_title in ["Private video", "Deleted video"]:
            playlist_summaries.append({
                "video_id": vid_id, "title": vid_title, "thumbnail_url": thumbnail_url,
                "summary": None, "error": "Video is private or deleted.",
            })
            continue

        if vid_id in summary_cache:
            cached_item = summary_cache[vid_id]
            playlist_summaries.append({
                "video_id": vid_id, "title": cached_item["title"],
                "thumbnail_url": cached_item["thumbnail_url"],
                "summary": cached_item["summary"],
                "video_url": cached_item.get("video_url", f"https://www.youtube.com/watch?v={vid_id}"),
                "error": None,
            })
            _notify_complete(session_id, {
                "video_id": vid_id, "title": vid_title, "source": "cache", "playlist": playlist_title,
            })
            continue

        summary, err = _summarize_and_cache(vid_id, vid_title, thumbnail_url, model_key)
        if summary and not err:
            _notify_complete(session_id, {
                "video_id": vid_id, "title": vid_title, "source": "generated",
                "model_used": model_key, "playlist": playlist_title,
            })

        playlist_summaries.append({
            "video_id": vid_id, "title": vid_title, "thumbnail_url": thumbnail_url,
            "summary": summary, "video_url": f"https://www.youtube.com/watch?v={vid_id}",
            "error": err,
        })

    return {"type": "playlist", "title": playlist_title, "summaries": playlist_summaries}, total_videos


def _process_video_url(video_id, model_key, session_id, processed_count, total_urls):
    """Process a single video URL and return a result dict."""
    details = get_video_details([video_id]).get(video_id, {})
    title = details.get("title", "Unknown Video")

    _notify_progress(session_id, {
        "status": "processing",
        "message": f"Processing: {title[:50]}{'...' if len(title) > 50 else ''}",
        "progress": processed_count,
        "total": total_urls,
        "current_video": {"id": video_id, "title": title},
    })

    if video_id in summary_cache:
        cached_item = summary_cache[video_id]
        _notify_complete(session_id, {
            "video_id": video_id, "title": cached_item["title"], "source": "cache",
        })
        return {
            "type": "video", "video_id": video_id, "title": cached_item["title"],
            "thumbnail_url": cached_item["thumbnail_url"], "summary": cached_item["summary"],
            "video_url": cached_item.get("video_url", f"https://www.youtube.com/watch?v={video_id}"),
            "error": None,
        }

    thumbnail_url = details.get("thumbnail_url")
    summary, err = _summarize_and_cache(video_id, title, thumbnail_url, model_key)
    if summary and not err:
        _notify_complete(session_id, {
            "video_id": video_id, "title": title, "source": "generated", "model_used": model_key,
        })

    return {
        "type": "video", "video_id": video_id, "title": title,
        "thumbnail_url": thumbnail_url, "summary": summary,
        "video_url": f"https://www.youtube.com/watch?v={video_id}", "error": err,
    }


@app.route("/summarize", methods=["POST"])
@require_auth
def summarize_links():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON in request body"}), 400
        urls = data.get("urls", [])
        if not urls:
            return jsonify({"error": "No URLs provided"}), 400

        model_key = data.get("model", DEFAULT_MODEL)
        if model_key not in AVAILABLE_MODELS:
            available_models = list(AVAILABLE_MODELS.keys())
            return jsonify({"error": f"Unsupported model: {model_key}. Available models: {available_models}"}), 400

        session_id = session.get("session_id")

        # Send initial progress notification
        has_playlists = any(get_playlist_id(url) for url in urls)
        if has_playlists:
            _notify_progress(session_id, {
                "status": "starting", "message": "Analyzing URLs and counting videos...",
                "progress": 0, "total": None,
            })
        else:
            total_items = sum(1 for url in urls if get_video_id(url))
            _notify_progress(session_id, {
                "status": "starting", "message": f"Starting to process {total_items} videos",
                "progress": 0, "total": total_items,
            })

        results = []
        processed_count = 0
        for url in urls:
            playlist_id, video_id = get_playlist_id(url), get_video_id(url)

            if playlist_id:
                try:
                    result, count = _process_playlist_url(url, playlist_id, model_key, session_id, processed_count)
                    results.append(result)
                    processed_count += count
                except Exception as e:
                    results.append({
                        "type": "playlist", "title": "Unknown Playlist",
                        "error": f"An unexpected error occurred: {e}", "summaries": [],
                    })

            elif video_id:
                processed_count += 1
                try:
                    result = _process_video_url(video_id, model_key, session_id, processed_count, len(urls))
                    results.append(result)
                except Exception as e:
                    results.append({
                        "type": "video", "video_id": video_id,
                        "title": "Unknown Video", "error": f"Failed to process video: {e}",
                    })
            else:
                results.append({"type": "error", "url": url, "error": "Invalid or unsupported YouTube URL."})

        _notify_progress(session_id, {
            "status": "completed", "message": "All summaries completed!",
            "progress": processed_count, "total": processed_count, "results_count": len(results),
        })

        return jsonify(results)
    except Exception as e:
        app.logger.error(f"Unhandled exception in /summarize: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": "An unexpected error occurred while processing your request"}), 500


@app.route("/speak", methods=["POST"])
@require_auth
def speak():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON in request body"}), 400
        text_to_speak = data.get("text")
        if not text_to_speak:
            return jsonify({"error": "No text provided"}), 400
        if len(text_to_speak) > MAX_TTS_CHARS:
            return jsonify({"error": f"Text too long (max {MAX_TTS_CHARS} characters)"}), 413

        text_to_speak = prepare_tts_text(text_to_speak)
    except Exception as e:
        return jsonify({"error": f"Failed to parse request: {str(e)}"}), 400

    # Get voice selection from request data (default to configured voice).
    # voice_id becomes the leading component of the cache filename, so reject
    # anything not in the known-voice allowlist to prevent path traversal
    # (e.g. "../../etc/x") into the audio cache write/read.
    voice_id = data.get("voice_id", TTS_VOICE)
    if not validate_voice_name(voice_id):
        return jsonify({"error": "Invalid voice selection"}), 400

    # Check if cache cleanup is needed (do this before generating cache key)
    if should_cleanup_cache(AUDIO_CACHE_DIR):
        cleanup_result = cleanup_audio_cache(AUDIO_CACHE_DIR)
        size_mb = cleanup_result["size_freed"] / 1024 / 1024
        print(f"Cache cleanup: removed {cleanup_result['cleaned']} files, freed {size_mb:.1f}MB")

    filepath = speech_cache_path(voice_id, text_to_speak)
    filename = os.path.basename(filepath)

    if os.path.exists(filepath):
        print(f"AUDIO CACHE HIT for file: {filename}")
        with open(filepath, "rb") as f:
            audio_content = f.read()
        return Response(audio_content, mimetype="audio/mpeg")

    print(f"AUDIO CACHE MISS for file: {filename}. Generating...")

    # Check if TTS client is available
    if not tts_client:
        return Response(
            "Text-to-speech service not available. Please set the GOOGLE_API_KEY environment variable.",
            status=503,
        )

    try:
        audio_content = synthesize_audio(tts_client, voice_id, text_to_speak, filepath)
        print(f"Saved new audio file to cache: {filepath} using voice: {voice_id}")
        return Response(audio_content, mimetype="audio/mpeg")

    except Exception as e:
        print(f"Error in TTS endpoint: {e}")
        return Response(f"Failed to generate audio: {e}", status=500)


@app.route("/api/voices", methods=["GET"])
@require_auth
def get_voices():
    """Get available voices organized by tier"""
    try:
        return jsonify(
            {
                "voices": AVAILABLE_VOICES,
                "tiers": get_voices_by_tier(),
                "current_voice": TTS_VOICE,
                "default_voice": DEFAULT_VOICE,
            }
        )
    except Exception as e:
        return jsonify({"error": f"Failed to get voices: {str(e)}"}), 500


@app.route("/api/cache/status", methods=["GET"])
@require_auth
def get_cache_status():
    """Get audio cache status and statistics"""
    try:
        import os
        from pathlib import Path

        if not os.path.exists(AUDIO_CACHE_DIR):
            return jsonify(
                {
                    "total_files": 0,
                    "total_size_mb": 0,
                    "cache_utilization": 0,
                    "needs_cleanup": False,
                }
            )

        total_size = 0
        file_count = 0
        preview_count = 0

        for file_path in Path(AUDIO_CACHE_DIR).glob("*.mp3"):
            total_size += file_path.stat().st_size
            file_count += 1
            if file_path.name.startswith("preview_"):
                preview_count += 1

        max_size_bytes = CACHE_CONFIG["max_size_mb"] * 1024 * 1024
        utilization = (total_size / max_size_bytes) * 100 if max_size_bytes > 0 else 0

        return jsonify(
            {
                "total_files": file_count,
                "preview_files": preview_count,
                "total_size_mb": round(total_size / 1024 / 1024, 2),
                "max_size_mb": CACHE_CONFIG["max_size_mb"],
                "cache_utilization": round(utilization, 1),
                "needs_cleanup": should_cleanup_cache(AUDIO_CACHE_DIR),
                "config": CACHE_CONFIG,
            }
        )
    except Exception as e:
        return jsonify({"error": f"Failed to get cache status: {str(e)}"}), 500


@app.route("/api/cache/cleanup", methods=["POST"])
@require_auth
def manual_cache_cleanup():
    """Manually trigger cache cleanup"""
    try:
        cleanup_result = cleanup_audio_cache(AUDIO_CACHE_DIR)
        return jsonify(
            {
                "success": True,
                "cleaned_files": cleanup_result["cleaned"],
                "size_freed_mb": round(cleanup_result["size_freed"] / 1024 / 1024, 2),
                "remaining_files": cleanup_result["remaining_files"],
                "remaining_size_mb": round(cleanup_result["remaining_size"] / 1024 / 1024, 2),
            }
        )
    except Exception as e:
        return jsonify({"error": f"Failed to cleanup cache: {str(e)}"}), 500


@app.route("/preview-voice", methods=["POST"])
@require_auth
def preview_voice():
    """Preview a voice with custom text"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON in request body"}), 400

        voice_id = data.get("voice_id")
        text_to_speak = data.get("text")

        if not voice_id:
            return jsonify({"error": "No voice_id provided"}), 400
        if not text_to_speak:
            return jsonify({"error": "No text provided"}), 400

        # voice_id is part of the cache filename: allowlist it (path traversal)
        if not validate_voice_name(voice_id):
            return jsonify({"error": "Invalid voice selection"}), 400

        text_to_speak = prepare_tts_text(text_to_speak)

        # Limit text length for previews to prevent abuse
        if len(text_to_speak) > 500:
            text_to_speak = text_to_speak[:500] + "..."

    except Exception as e:
        return jsonify({"error": f"Failed to parse request: {str(e)}"}), 400

    # Use optimized cache key for previews
    filepath = speech_cache_path(voice_id, text_to_speak, prefix="preview_")
    filename = os.path.basename(filepath)

    # Check cache first
    if os.path.exists(filepath):
        print(f"VOICE PREVIEW CACHE HIT for file: {filename}")
        with open(filepath, "rb") as f:
            audio_content = f.read()
        return Response(audio_content, mimetype="audio/mpeg")

    print(f"VOICE PREVIEW CACHE MISS for file: {filename}. Generating...")

    # Check if TTS client is available
    if not tts_client:
        return Response(
            "Text-to-speech service not available. Please set the GOOGLE_API_KEY environment variable.",
            status=503,
        )

    try:
        audio_content = synthesize_audio(tts_client, voice_id, text_to_speak, filepath)
        print(f"Saved new voice preview to cache: {filepath}")
        return Response(audio_content, mimetype="audio/mpeg")

    except Exception as e:
        print(f"Error in voice preview endpoint with voice {voice_id}: {e}")

        # Try fallback voice if the selected voice failed
        try:
            fallback_voice_id = get_fallback_voice(voice_id)
            print(f"Trying fallback voice for preview: {fallback_voice_id}")
            audio_content = synthesize_audio(tts_client, fallback_voice_id, text_to_speak, filepath)
            print(f"Saved voice preview using fallback voice: {fallback_voice_id}")
            return Response(audio_content, mimetype="audio/mpeg")

        except Exception as fallback_error:
            print(f"Fallback voice preview also failed: {fallback_error}")
            return Response(f"Failed to generate voice preview: {e}", status=500)


@app.route("/delete_summary", methods=["DELETE"])
@require_auth
def delete_summary():
    """Delete a summary from the cache by video_id"""
    try:
        # Try to get JSON data
        try:
            data = request.get_json(force=True)
        except Exception:
            return jsonify({"error": "Invalid JSON in request body"}), 400

        if data is None:
            return jsonify({"error": "Invalid JSON in request body"}), 400

        video_id = data.get("video_id")
        if not video_id:
            return jsonify({"error": "video_id is required"}), 400

        # Sanitize video_id input to prevent XSS
        video_id = html.escape(video_id)

        if video_id not in summary_cache:
            return jsonify({"error": "Summary not found"}), 404

        cached_item = summary_cache[video_id]

        # Audio generated by /speak is keyed on voice + prepared text, so check
        # every known voice. Also honour the legacy audio_filename field.
        audio_paths = set()
        if cached_item.get("summary"):
            prepared = prepare_tts_text(cached_item["summary"])
            for voice in set(AVAILABLE_VOICES) | {TTS_VOICE}:
                audio_paths.add(speech_cache_path(voice, prepared))
        if cached_item.get("audio_filename"):
            audio_paths.add(os.path.join(AUDIO_CACHE_DIR, os.path.basename(cached_item["audio_filename"])))

        # Remove from cache
        del summary_cache[video_id]

        # Save the updated cache
        save_summary_cache(summary_cache, SUMMARY_CACHE_FILE)

        # Delete any associated audio files
        for audio_filepath in audio_paths:
            if os.path.exists(audio_filepath):
                try:
                    os.remove(audio_filepath)
                    print(f"Deleted audio file: {audio_filepath}")
                except Exception as e:
                    print(f"Warning: Could not delete audio file {audio_filepath}: {e}")

        return jsonify(
            {
                "success": True,
                "message": f"Summary for video {video_id} deleted successfully",
            }
        )

    except Exception as e:
        print(f"Error in delete_summary endpoint: {e}")
        return jsonify({"error": "Failed to delete summary", "message": str(e)}), 500


@app.route("/settings")
@require_auth
def settings_page():
    """Display the settings page.

    Secret values are never rendered; the template only learns whether each
    one is set (True/False) so the page source cannot leak credentials.
    """
    env_vars = {
        "GOOGLE_API_KEY": bool(os.environ.get("GOOGLE_API_KEY")),
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
        "LOGIN_ENABLED": os.environ.get("LOGIN_ENABLED", "false"),
        "LOGIN_CODE": bool(os.environ.get("LOGIN_CODE")),
        "SESSION_SECRET_KEY": bool(os.environ.get("SESSION_SECRET_KEY")),
        "MAX_LOGIN_ATTEMPTS": os.environ.get("MAX_LOGIN_ATTEMPTS", "5"),
        "LOCKOUT_DURATION": os.environ.get("LOCKOUT_DURATION", "15"),
        "WEBSHARE_PROXY_ENABLED": os.environ.get("WEBSHARE_PROXY_ENABLED", "false"),
        "WEBSHARE_PROXY_HOST": os.environ.get("WEBSHARE_PROXY_HOST", ""),
        "WEBSHARE_PROXY_PORT": os.environ.get("WEBSHARE_PROXY_PORT", ""),
        "WEBSHARE_PROXY_USERNAME": os.environ.get("WEBSHARE_PROXY_USERNAME", ""),
        "WEBSHARE_PROXY_PASSWORD": bool(os.environ.get("WEBSHARE_PROXY_PASSWORD")),
        "DATA_DIR": os.environ.get("DATA_DIR", ""),
        "FLASK_DEBUG": os.environ.get("FLASK_DEBUG", "false"),
        "TTS_VOICE": os.environ.get("TTS_VOICE", "en-US-Chirp3-HD-Zephyr"),
    }

    return render_template("settings.html", env_vars=env_vars)


@app.route("/settings", methods=["POST"])
@require_auth
def update_settings():
    """Update environment variables from settings form"""
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "Invalid JSON in request body"}), 400
    except Exception as e:
        return (
            jsonify({"error": "Invalid JSON in request body", "message": str(e)}),
            400,
        )

    try:
        # Define which environment variables we allow to be updated
        allowed_vars = {
            "google_api_key": "GOOGLE_API_KEY",
            "openai_api_key": "OPENAI_API_KEY",
            "login_enabled": "LOGIN_ENABLED",
            "login_code": "LOGIN_CODE",
            "session_secret_key": "SESSION_SECRET_KEY",
            "max_login_attempts": "MAX_LOGIN_ATTEMPTS",
            "lockout_duration": "LOCKOUT_DURATION",
            "webshare_proxy_enabled": "WEBSHARE_PROXY_ENABLED",
            "webshare_proxy_host": "WEBSHARE_PROXY_HOST",
            "webshare_proxy_port": "WEBSHARE_PROXY_PORT",
            "webshare_proxy_username": "WEBSHARE_PROXY_USERNAME",
            "webshare_proxy_password": "WEBSHARE_PROXY_PASSWORD",
            "flask_debug": "FLASK_DEBUG",
            "tts_voice": "TTS_VOICE",
        }

        # Validate and update environment variables
        updated_vars = {}
        for form_key, env_key in allowed_vars.items():
            if form_key in data:
                value = data[form_key].strip() if isinstance(data[form_key], str) else str(data[form_key])

                # Secret fields are rendered blank; blank means "keep current value"
                if env_key in SECRET_SETTINGS and not value:
                    continue

                # Special validation for numeric fields
                if form_key in [
                    "max_login_attempts",
                    "lockout_duration",
                    "webshare_proxy_port",
                ]:
                    if value and not value.isdigit():
                        return (
                            jsonify({"error": f"Invalid value for {form_key}: must be a number"}),
                            400,
                        )

                # Update environment variable
                os.environ[env_key] = value
                updated_vars[env_key] = value

        # Update global variables that depend on environment variables
        global LOGIN_ENABLED, LOGIN_CODE, SESSION_SECRET_KEY, MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION
        global WEBSHARE_PROXY_ENABLED, WEBSHARE_PROXY_HOST, WEBSHARE_PROXY_PORT
        global WEBSHARE_PROXY_USERNAME, WEBSHARE_PROXY_PASSWORD, TTS_VOICE
        global google_api_key, openai_api_key

        LOGIN_ENABLED = os.environ.get("LOGIN_ENABLED", "false").lower() == "true"
        LOGIN_CODE = os.environ.get("LOGIN_CODE", "")
        SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "")
        MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
        LOCKOUT_DURATION = int(os.environ.get("LOCKOUT_DURATION", "15"))

        # Keep auth module in sync with the updated config
        configure_auth(
            login_attempts_file=LOGIN_ATTEMPTS_FILE,
            max_login_attempts=MAX_LOGIN_ATTEMPTS,
            lockout_duration=LOCKOUT_DURATION,
            login_enabled=LOGIN_ENABLED,
        )

        WEBSHARE_PROXY_ENABLED = os.environ.get("WEBSHARE_PROXY_ENABLED", "false").lower() == "true"
        WEBSHARE_PROXY_HOST = os.environ.get("WEBSHARE_PROXY_HOST")
        WEBSHARE_PROXY_PORT = os.environ.get("WEBSHARE_PROXY_PORT")
        WEBSHARE_PROXY_USERNAME = os.environ.get("WEBSHARE_PROXY_USERNAME")
        WEBSHARE_PROXY_PASSWORD = os.environ.get("WEBSHARE_PROXY_PASSWORD")

        TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-Chirp3-HD-Zephyr")

        # Update Flask secret key if SESSION_SECRET_KEY changed
        if SESSION_SECRET_KEY:
            app.secret_key = SESSION_SECRET_KEY

        # Reinitialize API clients if API keys were updated
        if "GOOGLE_API_KEY" in updated_vars or "OPENAI_API_KEY" in updated_vars:
            google_api_key = os.environ.get("GOOGLE_API_KEY")
            openai_api_key = os.environ.get("OPENAI_API_KEY")

            if "GOOGLE_API_KEY" in updated_vars and google_api_key:
                init_google_clients(google_api_key)
            if "OPENAI_API_KEY" in updated_vars and openai_api_key:
                init_openai_client(openai_api_key)

        # Save environment variables to .env file for persistence
        save_success = save_env_to_file(updated_vars)

        return jsonify(
            {
                "success": True,
                "message": f"Settings updated successfully! {len(updated_vars)} variables updated."
                + (" Saved to .env file." if save_success else " Warning: Could not save to .env file."),
                "updated_variables": list(updated_vars.keys()),
                "env_file_saved": save_success,
            }
        )

    except Exception as e:
        print(f"Error updating settings: {e}")
        return jsonify({"error": "Failed to update settings", "message": str(e)}), 500


# Route prefixes that should receive JSON error responses
API_ROUTE_PREFIXES = [
    "/summarize",
    "/speak",
    "/get_cached_summaries",
    "/search_summaries",
    "/debug_transcript",
    "/api_status",
    "/login",
    "/logout",
    "/login_status",
    "/delete_summary",
    "/settings",
    "/events",
]


# Error handlers to ensure JSON responses for API endpoints.
# Details are logged server-side only; responses never include stack traces.
def _is_api_request():
    return any(request.path.startswith(path) for path in API_ROUTE_PREFIXES)


@app.errorhandler(400)
def bad_request(e):
    if _is_api_request():
        return jsonify({"error": "Bad request", "message": getattr(e, "description", "")}), 400
    return e


@app.errorhandler(404)
def not_found(e):
    if _is_api_request():
        return jsonify({"error": "Endpoint not found", "path": request.path}), 404
    return e


@app.errorhandler(500)
def server_error(e):
    if _is_api_request():
        return jsonify({"error": "Internal server error"}), 500
    return e


@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        # Let Flask render 4xx/405 etc. (the specific handlers above cover API routes)
        return e
    app.logger.error(f"Unhandled exception: {str(e)}\n{traceback.format_exc()}")
    if _is_api_request():
        return jsonify({"error": "An unexpected error occurred"}), 500
    return "Internal Server Error", 500


if __name__ == "__main__":
    # Debug mode is OFF by default; opt in with FLASK_DEBUG=true for local dev only.
    # The Werkzeug debugger allows remote code execution, so it must never
    # default on for a deployed instance.
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    print(f"🚀 Starting YouTube Summarizer on port 5001 (debug={debug_mode})")
    app.run(debug=debug_mode, port=5001, threaded=True)
