import atexit
import hashlib  # For generating filenames
import html  # For HTML escaping user inputs
import json
import os
import re
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from queue import Empty, Queue

# Import new worker system modules
try:
    from job_models import create_playlist_job, create_video_job
    from job_state import JobStateManager
    from sse_manager import get_sse_manager
    from worker_manager import WorkerManager

    WORKER_SYSTEM_AVAILABLE = True
    print("✅ Worker system modules imported successfully")
except ImportError as e:
    WORKER_SYSTEM_AVAILABLE = False
    print(f"⚠️ Worker system not available: {e}")
    print("   Falling back to synchronous processing only")

import socket

import google.generativeai as genai
import httplib2
import openai
from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from google.api_core.client_options import ClientOptions
from google.cloud import texttospeech
from googleapiclient.discovery import build

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
from ai_models import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    generate_summary,
    generate_summary_gemini,
    generate_summary_openai,
    get_summary_prompt,
)

# --- CONFIGURATION ---
app = Flask(__name__)

# --- SSE CONFIGURATION ---
# Store active SSE connections and their associated queues
sse_connections = {}
sse_connection_lock = threading.Lock()


class SSEConnection:
    """Manages individual SSE connection state"""

    def __init__(self, connection_id, session_id=None, user_ip=None):
        self.connection_id = connection_id
        self.session_id = session_id
        self.user_ip = user_ip
        self.message_queue = Queue()
        self.created_at = datetime.now(timezone.utc)
        self.last_activity = self.created_at
        self.is_active = True
        self.subscriptions = set()  # Track what types of events this connection wants

    def send_message(self, event_type, data, event_id=None, retry=None):
        """Add message to connection's queue"""
        if not self.is_active:
            return False

        try:
            message = {
                "event": event_type,
                "data": data,
                "id": event_id or str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "retry": retry,
            }
            self.message_queue.put(message, timeout=1)
            self.last_activity = datetime.now(timezone.utc)
            return True
        except Exception:
            self.is_active = False
            return False

    def get_messages(self, timeout=30):
        """Generator that yields messages from queue"""
        while self.is_active:
            try:
                message = self.message_queue.get(timeout=timeout)
                if message is None:  # Poison pill to stop connection
                    break
                yield message
                self.last_activity = datetime.now(timezone.utc)
            except Empty:
                # Send keep-alive ping
                yield {
                    "event": "ping",
                    "data": "keep-alive",
                    "id": str(uuid.uuid4()),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

    def close(self):
        """Close the connection gracefully"""
        self.is_active = False
        self.message_queue.put(None)  # Poison pill


def cleanup_stale_connections():
    """Remove connections that haven't been active for more than 5 minutes"""
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    with sse_connection_lock:
        stale_connections = [
            conn_id
            for conn_id, conn in sse_connections.items()
            if conn.last_activity < cutoff_time or not conn.is_active
        ]

        for conn_id in stale_connections:
            connection = sse_connections.pop(conn_id, None)
            if connection:
                connection.close()
                print(f"Cleaned up stale SSE connection: {conn_id}")


def broadcast_to_connections(event_type, data, session_filter=None, subscription_filter=None):
    """Broadcast message to all matching connections"""
    cleanup_stale_connections()

    with sse_connection_lock:
        for conn_id, connection in list(sse_connections.items()):
            # Filter by session if specified
            if session_filter and connection.session_id != session_filter:
                continue

            # Filter by subscription if specified
            if subscription_filter and subscription_filter not in connection.subscriptions:
                continue

            if not connection.send_message(event_type, data):
                # Connection is dead, remove it
                sse_connections.pop(conn_id, None)


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
# Use data directory if running in Docker/Podman, otherwise use current directory
DATA_DIR = os.environ.get("DATA_DIR", "data" if os.path.exists("/.dockerenv") else ".")
os.makedirs(DATA_DIR, exist_ok=True)
SUMMARY_CACHE_FILE = os.path.join(DATA_DIR, "summary_cache.json")
LOGIN_ATTEMPTS_FILE = os.path.join(DATA_DIR, "login_attempts.json")
AUDIO_CACHE_DIR = os.path.join(DATA_DIR, "audio_cache")

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
print(f"✅ Audio cache directory is set to: '{AUDIO_CACHE_DIR}/'")


summary_cache = load_summary_cache(SUMMARY_CACHE_FILE)
print(f"✅ Loaded {len(summary_cache)} summaries from cache.")

# Initialize worker system (will be called after API initialization)
worker_manager = None
job_state_manager = None
new_sse_manager = None


def init_worker_system():
    """Initialize the async worker system"""
    global worker_manager, job_state_manager, new_sse_manager

    if not WORKER_SYSTEM_AVAILABLE:
        print("⚠️ Worker system not available - running in synchronous mode only")
        return False

    try:
        if worker_manager is None:
            print("🚀 Initializing async worker system...")

            # Initialize managers
            job_state_manager = JobStateManager()
            new_sse_manager = get_sse_manager()

            # Initialize worker manager
            max_workers = int(os.environ.get("WORKER_THREADS", "3"))
            worker_manager = WorkerManager(
                num_workers=max_workers,
                max_queue_size=int(os.environ.get("WORKER_MAX_QUEUE_SIZE", "100")),
                rate_limit_per_minute=int(os.environ.get("WORKER_RATE_LIMIT", "60")),
            )

            # Set up app context functions in the worker manager
            # (These will be passed to worker threads to avoid circular imports)
            worker_manager.set_app_functions(
                {
                    "summary_cache": summary_cache,
                    "youtube": youtube,
                    "tts_client": tts_client,
                    "gemini_model": gemini_model,
                    "openai_client": openai_client,
                    "clean_youtube_url": clean_youtube_url,
                    "get_transcript": get_transcript,
                    "generate_summary": generate_summary,
                    "get_video_details": get_video_details,
                    "save_summary_cache": lambda cache: save_summary_cache(cache, SUMMARY_CACHE_FILE),
                    "extract_video_id": get_video_id,
                    "extract_playlist_id": get_playlist_id,
                    "get_videos_from_playlist": get_videos_from_playlist,
                    "sse_manager": new_sse_manager,
                }
            )

            # Start the worker system
            worker_manager.start()

            print(f"✅ Worker system initialized with {worker_manager.max_workers} worker threads")
            return True

    except Exception as e:
        print(f"❌ Failed to initialize worker system: {e}")
        print("   Falling back to synchronous processing only")
        worker_manager = None
        job_state_manager = None
        new_sse_manager = None
        return False


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

# Configure Flask session
if LOGIN_ENABLED:
    if not SESSION_SECRET_KEY:
        print("Warning: SESSION_SECRET_KEY not set. Using auto-generated key (not recommended for production)")
        SESSION_SECRET_KEY = os.urandom(24).hex()
    if not LOGIN_CODE:
        print("Warning: LOGIN_CODE not set. Login functionality will not work properly.")

app.secret_key = SESSION_SECRET_KEY if SESSION_SECRET_KEY else os.urandom(24)

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

    # Set socket timeout as well for extra safety
    socket.setdefaulttimeout(timeout)

    # Build the YouTube client with the configured http instance
    return build("youtube", "v3", developerKey=api_key, http=http)


# --- API CLIENT INITIALIZATION ---
google_api_key = os.environ.get("GOOGLE_API_KEY")
openai_api_key = os.environ.get("OPENAI_API_KEY")
tts_client = None
youtube = None
gemini_model = None
openai_client = None

# Initialize Google APIs
if google_api_key and not os.environ.get("TESTING"):
    try:
        tts_client = texttospeech.TextToSpeechClient(client_options=ClientOptions(api_key=google_api_key))
        genai.configure(api_key=google_api_key)
        youtube = create_youtube_client_with_timeout(google_api_key, timeout=30)
        gemini_model = genai.GenerativeModel(model_name="gemini-2.5-flash-preview-05-20")
        print("✅ Google APIs initialized successfully")
    except Exception as e:
        print(f"Warning: Could not configure Google APIs. Error: {e}")
elif not google_api_key and not os.environ.get("TESTING"):
    print("Warning: GOOGLE_API_KEY environment variable is not set. Google services will be unavailable.")

# Initialize OpenAI API
if openai_api_key and not os.environ.get("TESTING"):
    try:
        openai_client = openai.OpenAI(api_key=openai_api_key)
        print("✅ OpenAI API initialized successfully")
    except Exception as e:
        print(f"Warning: Could not configure OpenAI API. Error: {e}")
elif not openai_api_key and not os.environ.get("TESTING"):
    print("Warning: OPENAI_API_KEY environment variable is not set. OpenAI models will be unavailable.")

# For testing, create clients even without API keys
if os.environ.get("TESTING"):
    try:
        if not gemini_model:
            gemini_model = genai.GenerativeModel(model_name="gemini-2.5-flash-preview-05-20")
        if not openai_client:
            openai_client = openai.OpenAI(api_key="test-key")
    except Exception:
        pass

# Backward compatibility - keep 'model' variable for existing code
model = gemini_model

# Inject clients into extracted modules
youtube_helpers.set_youtube_client(youtube)
ai_models.set_clients(gemini=gemini_model, openai_cli=openai_client)

# Worker system will be initialized after all functions are defined


# --- HELPER FUNCTIONS ---
def get_client_ip():
    """Extract the real client IP address from the request, handling proxies."""
    client_ip = request.environ.get("HTTP_X_FORWARDED_FOR", request.environ.get("REMOTE_ADDR", "127.0.0.1"))
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    return client_ip




# --- INITIALIZE WORKER SYSTEM ---
# Initialize worker system now that all functions are defined
init_worker_system()


# --- API ENDPOINTS ---


@app.route("/health")
@app.route("/sse/health")
def health_check():
    """Lightweight, unauthenticated health endpoint for container/orchestration
    health checks (referenced by the Docker/compose configs). Reports liveness
    plus a quick view of the worker subsystem."""
    worker_running = bool(
        WORKER_SYSTEM_AVAILABLE and worker_manager is not None and getattr(worker_manager, "is_running", False)
    )
    return (
        jsonify(
            {
                "status": "ok",
                "worker_system_available": WORKER_SYSTEM_AVAILABLE,
                "worker_running": worker_running,
                "sse_connections": len(sse_connections),
            }
        ),
        200,
    )


@app.route("/")
@require_auth
def home():
    return render_template("index.html")


@app.route("/sse-test")
@require_auth
def sse_test():
    """SSE testing and demonstration page"""
    return render_template("sse_test.html")


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

        # Sanitize passcode input to prevent XSS
        passcode = html.escape(passcode)

        # Simple authentication check
        if passcode == LOGIN_CODE:
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
    """Server-Sent Events endpoint for real-time notifications"""
    # Generate unique connection ID
    connection_id = str(uuid.uuid4())

    # Get client information for security and tracking
    session_id = session.get("session_id") or session.sid if hasattr(session, "sid") else None
    client_ip = get_client_ip()

    # Get subscription preferences from query parameters
    subscriptions = request.args.get("subscribe", "").split(",")
    subscriptions = {sub.strip() for sub in subscriptions if sub.strip()}
    if not subscriptions:
        subscriptions = {
            "summary_complete",
            "summary_progress",
            "system",
        }  # Default subscriptions

    # Create and register the connection
    connection = SSEConnection(connection_id, session_id, client_ip)
    connection.subscriptions = subscriptions

    with sse_connection_lock:
        sse_connections[connection_id] = connection

    print(f"New SSE connection established: {connection_id} from {client_ip} (Session: {session_id})")

    def generate():
        """Generator function for SSE stream"""
        try:
            # Send initial connection event
            yield format_sse_message(
                "connected",
                {
                    "connection_id": connection_id,
                    "message": "Connected to notification stream",
                    "subscriptions": list(subscriptions),
                },
                event_id=connection_id,
            )

            # Stream messages from the connection's queue
            for message in connection.get_messages():
                if not connection.is_active:
                    break
                yield format_sse_message(
                    message["event"],
                    message["data"],
                    message["id"],
                    message.get("retry"),
                )

        except GeneratorExit:
            # Client disconnected
            print(f"SSE connection closed by client: {connection_id}")
        except Exception as e:
            print(f"Error in SSE stream {connection_id}: {e}")
        finally:
            # Clean up connection
            with sse_connection_lock:
                sse_connections.pop(connection_id, None)
            connection.close()
            print(f"SSE connection cleaned up: {connection_id}")

    # Return SSE response with proper headers
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",  # Nginx directive to disable buffering
            "Connection": "keep-alive",
        },
    )


@app.route("/events/status")
@require_auth
def sse_status():
    """Get information about active SSE connections"""
    cleanup_stale_connections()

    with sse_connection_lock:
        connection_info = []
        for conn_id, conn in sse_connections.items():
            connection_info.append(
                {
                    "connection_id": conn_id,
                    "session_id": conn.session_id,
                    "user_ip": conn.user_ip,
                    "created_at": conn.created_at.isoformat(),
                    "last_activity": conn.last_activity.isoformat(),
                    "is_active": conn.is_active,
                    "subscriptions": list(conn.subscriptions),
                    "queue_size": conn.message_queue.qsize(),
                }
            )

    return jsonify({"total_connections": len(sse_connections), "connections": connection_info})


@app.route("/events/broadcast", methods=["POST"])
@require_auth
def sse_broadcast():
    """Manual broadcast endpoint for testing (admin/debug use)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON in request body"}), 400

        event_type = data.get("event_type", "test")
        message_data = data.get("data", {})
        session_filter = data.get("session_filter")
        subscription_filter = data.get("subscription_filter")

        # Validate event type
        allowed_events = [
            "test",
            "system",
            "summary_complete",
            "summary_progress",
            "admin",
        ]
        if event_type not in allowed_events:
            return (
                jsonify({"error": f"Invalid event type. Allowed: {allowed_events}"}),
                400,
            )

        broadcast_to_connections(
            event_type,
            message_data,
            session_filter=session_filter,
            subscription_filter=subscription_filter,
        )

        return jsonify(
            {
                "success": True,
                "message": f"Broadcasted {event_type} event",
                "total_connections": len(sse_connections),
            }
        )

    except Exception as e:
        return jsonify({"error": f"Broadcast failed: {str(e)}"}), 500


def format_sse_message(event_type, data, event_id=None, retry=None):
    """Format data as Server-Sent Events message"""
    lines = []

    if event_id:
        lines.append(f"id: {event_id}")

    if retry:
        lines.append(f"retry: {retry}")

    lines.append(f"event: {event_type}")

    # Handle data formatting
    if isinstance(data, (dict, list)):
        data_str = json.dumps(data)
    else:
        data_str = str(data)

    # Split multi-line data properly
    for line in data_str.split("\n"):
        lines.append(f"data: {line}")

    lines.append("")  # Empty line to end the message
    return "\n".join(lines) + "\n"


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
        "gemini_model_initialized": gemini_model is not None,
        "openai_client_initialized": openai_client is not None,
        "available_models": list(AVAILABLE_MODELS.keys()),
        "testing_mode": bool(os.environ.get("TESTING")),
    }
    return jsonify(status)


@app.route("/debug_transcript", methods=["GET"])
@require_auth
def debug_transcript():
    """Debug endpoint to check transcript retrieval for a specific video"""
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


@app.route("/debug_model", methods=["GET"])
@require_auth
def debug_model():
    """Debug endpoint to test model functionality"""
    model_key = request.args.get("model", "gpt-5")

    try:
        # Test with a simple transcript
        test_transcript = "This is a test transcript about artificial intelligence and machine learning technologies."
        test_title = "Test Video About AI"

        print(f"🔍 Debug endpoint testing model: {model_key}")

        # Test the model
        summary, error = generate_summary(test_transcript, test_title, model_key)

        result = {
            "model_key": model_key,
            "model_config": AVAILABLE_MODELS.get(model_key, {}),
            "openai_client_available": openai_client is not None,
            "summary_success": summary is not None,
            "summary_length": len(summary) if summary else 0,
            "error": error,
        }

        if summary:
            result["summary_preview"] = summary[:200] + "..." if len(summary) > 200 else summary

        return jsonify(result)

    except Exception as e:
        import traceback

        return (
            jsonify(
                {
                    "error": "Exception in debug_model",
                    "message": str(e),
                    "type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                }
            ),
            500,
        )


def _notify_progress(session_id, data):
    """Send a summary_progress SSE notification."""
    broadcast_to_connections(
        "summary_progress", data,
        session_filter=session_id,
        subscription_filter="summary_progress",
    )


def _notify_complete(session_id, data):
    """Send a summary_complete SSE notification."""
    broadcast_to_connections(
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
        audio_filename = f"{hashlib.sha256(summary.encode('utf-8')).hexdigest()}.mp3"
        summary_cache[vid_id] = build_cache_entry(
            vid_title, summary, thumbnail_url, vid_id, model_key, audio_filename
        )
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

        session_id = session.get("session_id") or session.sid if hasattr(session, "sid") else None

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
        return jsonify({
            "error": "An unexpected error occurred while processing your request",
            "message": str(e), "type": type(e).__name__, "stacktrace": traceback.format_exc(),
        }), 500


# New async endpoints for worker system
@app.route("/summarize_async", methods=["POST"])
@require_auth
def summarize_async():
    """Async version of summarize - submits jobs to worker queue"""
    if not WORKER_SYSTEM_AVAILABLE or worker_manager is None:
        # Fall back to synchronous processing
        return redirect(url_for("summarize_links"))

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON in request body"}), 400

        urls_input = data.get("urls", "").strip()
        model_key = data.get("model", "gemini-2.5-flash")

        if not urls_input:
            return jsonify({"error": "No URLs provided"}), 400

        # Parse URLs
        urls = [url.strip() for url in urls_input.replace("\n", " ").split() if url.strip()]

        if not urls:
            return jsonify({"error": "No valid URLs provided"}), 400

        # Submit jobs to worker queue
        job_ids = []
        session_id = session.get("session_id", str(uuid.uuid4()))
        session["session_id"] = session_id

        for url in urls:
            video_id = get_video_id(url)
            playlist_id = get_playlist_id(url)

            if video_id:
                # Single video job
                job = create_video_job(url=url, model_key=model_key, session_id=session_id)

                if worker_manager.submit_job(job):
                    job_ids.append(job.job_id)

            elif playlist_id:
                # Playlist job - video IDs are fetched by the worker during processing
                job = create_playlist_job(url=url, video_ids=[], model_key=model_key, session_id=session_id)

                if worker_manager.submit_job(job):
                    job_ids.append(job.job_id)

        if not job_ids:
            return jsonify({"error": "Failed to submit any jobs"}), 500

        return jsonify(
            {
                "success": True,
                "message": f"Submitted {len(job_ids)} jobs for processing",
                "job_ids": job_ids,
                "session_id": session_id,
            }
        )

    except Exception as e:
        app.logger.error(f"Error in summarize_async: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/jobs/<job_id>/status", methods=["GET"])
@require_auth
def get_job_status(job_id):
    """Get job status and progress"""
    if not WORKER_SYSTEM_AVAILABLE or job_state_manager is None:
        return jsonify({"error": "Worker system not available"}), 503

    try:
        status = job_state_manager.get_job_status(job_id)
        if status is None:
            return jsonify({"error": "Job not found"}), 404

        return jsonify(status)

    except Exception as e:
        app.logger.error(f"Error getting job status: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/jobs", methods=["GET"])
@require_auth
def list_jobs():
    """List all jobs with optional filtering"""
    if not WORKER_SYSTEM_AVAILABLE or job_state_manager is None:
        return jsonify({"jobs": []})

    try:
        status_filter = request.args.get("status")
        jobs = job_state_manager.get_all_jobs(status_filter=status_filter)

        return jsonify({"jobs": jobs})

    except Exception as e:
        app.logger.error(f"Error listing jobs: {e}")
        return jsonify({"error": str(e)}), 500


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

        # Sanitize text input to prevent XSS (though this goes to TTS, not display)
        text_to_speak = html.escape(text_to_speak)

        # Clean text for TTS to avoid ASCII pronunciation issues
        text_to_speak = clean_text_for_tts(text_to_speak)
    except Exception as e:
        return jsonify({"error": f"Failed to parse request: {str(e)}"}), 400

    # Get voice selection from request data (default to configured voice)
    voice_id = data.get("voice_id", TTS_VOICE)

    # Check if cache cleanup is needed (do this before generating cache key)
    if should_cleanup_cache(AUDIO_CACHE_DIR):
        cleanup_result = cleanup_audio_cache(AUDIO_CACHE_DIR)
        size_mb = cleanup_result["size_freed"] / 1024 / 1024
        print(f"Cache cleanup: removed {cleanup_result['cleaned']} files, freed {size_mb:.1f}MB")

    # Use optimized cache key generation
    cache_key = get_optimized_cache_key(voice_id, text_to_speak)
    filename = f"{cache_key}.mp3"
    filepath = os.path.join(AUDIO_CACHE_DIR, filename)

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

        # Sanitize text input
        text_to_speak = html.escape(text_to_speak)
        # Clean text for TTS to avoid ASCII pronunciation issues
        text_to_speak = clean_text_for_tts(text_to_speak)

        # Limit text length for previews to prevent abuse
        if len(text_to_speak) > 500:
            text_to_speak = text_to_speak[:500] + "..."

    except Exception as e:
        return jsonify({"error": f"Failed to parse request: {str(e)}"}), 400

    # Use optimized cache key for previews
    preview_key = f"preview_{get_optimized_cache_key(voice_id, text_to_speak)}"
    filename = f"{preview_key}.mp3"
    filepath = os.path.join(AUDIO_CACHE_DIR, filename)

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

        # Get the audio filename before deleting from cache
        cached_item = summary_cache[video_id]
        audio_filename = cached_item.get("audio_filename")

        # Remove from cache
        del summary_cache[video_id]

        # Save the updated cache
        save_summary_cache(summary_cache, SUMMARY_CACHE_FILE)

        # Try to delete the associated audio file if it exists
        if audio_filename:
            audio_filepath = os.path.join(AUDIO_CACHE_DIR, audio_filename)
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
    """Display the settings page with current environment variables"""
    # Collect current environment variables
    env_vars = {
        "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY", ""),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
        "LOGIN_ENABLED": os.environ.get("LOGIN_ENABLED", "false"),
        "LOGIN_CODE": os.environ.get("LOGIN_CODE", ""),
        "SESSION_SECRET_KEY": os.environ.get("SESSION_SECRET_KEY", ""),
        "MAX_LOGIN_ATTEMPTS": os.environ.get("MAX_LOGIN_ATTEMPTS", "5"),
        "LOCKOUT_DURATION": os.environ.get("LOCKOUT_DURATION", "15"),
        "WEBSHARE_PROXY_ENABLED": os.environ.get("WEBSHARE_PROXY_ENABLED", "false"),
        "WEBSHARE_PROXY_HOST": os.environ.get("WEBSHARE_PROXY_HOST", ""),
        "WEBSHARE_PROXY_PORT": os.environ.get("WEBSHARE_PROXY_PORT", ""),
        "WEBSHARE_PROXY_USERNAME": os.environ.get("WEBSHARE_PROXY_USERNAME", ""),
        "WEBSHARE_PROXY_PASSWORD": os.environ.get("WEBSHARE_PROXY_PASSWORD", ""),
        "DATA_DIR": os.environ.get("DATA_DIR", ""),
        "FLASK_DEBUG": os.environ.get("FLASK_DEBUG", "true"),
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
            "data_dir": "DATA_DIR",
            "flask_debug": "FLASK_DEBUG",
            "tts_voice": "TTS_VOICE",
        }

        # Validate and update environment variables
        updated_vars = {}
        for form_key, env_key in allowed_vars.items():
            if form_key in data:
                value = data[form_key].strip() if isinstance(data[form_key], str) else str(data[form_key])

                # Sanitize settings input to prevent XSS
                value = html.escape(value)

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
        global WEBSHARE_PROXY_USERNAME, WEBSHARE_PROXY_PASSWORD, DATA_DIR, TTS_VOICE
        global google_api_key, openai_api_key, gemini_model, openai_client, tts_client, youtube

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

        DATA_DIR = os.environ.get("DATA_DIR", "data" if os.path.exists("/.dockerenv") else ".")
        TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-Chirp3-HD-Zephyr")

        # Update Flask secret key if SESSION_SECRET_KEY changed
        if SESSION_SECRET_KEY:
            app.secret_key = SESSION_SECRET_KEY

        # Reinitialize API clients if API keys were updated
        if "GOOGLE_API_KEY" in updated_vars or "OPENAI_API_KEY" in updated_vars:
            google_api_key = os.environ.get("GOOGLE_API_KEY")
            openai_api_key = os.environ.get("OPENAI_API_KEY")

            # Reinitialize Google APIs if key was updated
            if "GOOGLE_API_KEY" in updated_vars and google_api_key:
                try:
                    tts_client = texttospeech.TextToSpeechClient(client_options=ClientOptions(api_key=google_api_key))
                    genai.configure(api_key=google_api_key)
                    youtube = create_youtube_client_with_timeout(google_api_key, timeout=30)
                    gemini_model = genai.GenerativeModel(model_name="gemini-2.5-flash-preview-05-20")
                    youtube_helpers.set_youtube_client(youtube)
                    ai_models.set_clients(gemini=gemini_model)
                    print("✅ Google APIs reinitialized successfully")
                except Exception as e:
                    print(f"Warning: Could not reinitialize Google APIs. Error: {e}")

            # Reinitialize OpenAI API if key was updated
            if "OPENAI_API_KEY" in updated_vars and openai_api_key:
                try:
                    openai_client = openai.OpenAI(api_key=openai_api_key)
                    ai_models.set_clients(openai_cli=openai_client)
                    print("✅ OpenAI API reinitialized successfully")
                except Exception as e:
                    print(f"Warning: Could not reinitialize OpenAI API. Error: {e}")

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


# Error handlers to ensure JSON responses for API endpoints
@app.errorhandler(400)
def bad_request(e):
    if any(request.path.startswith(path) for path in API_ROUTE_PREFIXES):
        return (
            jsonify(
                {
                    "error": "Bad request",
                    "message": str(e),
                    "stacktrace": traceback.format_exc(),
                }
            ),
            400,
        )
    return e


@app.errorhandler(404)
def not_found(e):
    if any(request.path.startswith(path) for path in API_ROUTE_PREFIXES):
        return (
            jsonify({"error": "Endpoint not found", "message": str(e), "path": request.path}),
            404,
        )
    return e


@app.errorhandler(500)
def server_error(e):
    if any(request.path.startswith(path) for path in API_ROUTE_PREFIXES):
        return (
            jsonify(
                {
                    "error": "Internal server error",
                    "message": str(e),
                    "stacktrace": traceback.format_exc(),
                }
            ),
            500,
        )
    return e


@app.errorhandler(Exception)
def handle_exception(e):
    # Log the error with full traceback
    app.logger.error(f"Unhandled exception: {str(e)}\n{traceback.format_exc()}")
    if any(request.path.startswith(path) for path in API_ROUTE_PREFIXES):
        return (
            jsonify(
                {
                    "error": "An unexpected error occurred",
                    "message": str(e),
                    "type": type(e).__name__,
                    "stacktrace": traceback.format_exc(),
                }
            ),
            500,
        )
    # For non-API routes, let Flask handle it normally
    return e


# Graceful shutdown handler
def cleanup_worker_system():
    """Cleanup function for application shutdown"""
    if worker_manager:
        print("🔄 Shutting down worker system gracefully...")
        worker_manager.stop()
        print("✅ Worker system shutdown complete")

    if new_sse_manager:
        print("🔄 Shutting down SSE manager...")
        new_sse_manager.shutdown()
        print("✅ SSE manager shutdown complete")


# Register cleanup function
atexit.register(cleanup_worker_system)


if __name__ == "__main__":
    try:
        # Enable debug mode only in development (configurable via environment variable)
        debug_mode = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
        print(f"🚀 Starting YouTube Summarizer on port 5001 (debug={debug_mode})")
        app.run(debug=debug_mode, port=5001)
    except KeyboardInterrupt:
        print("\n🔄 Received shutdown signal, cleaning up...")
        cleanup_worker_system()
        print("👋 Shutdown complete")
