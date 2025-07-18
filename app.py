import hashlib  # For generating filenames
import json
import os
import re
import traceback
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import google.generativeai as genai
from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from google.api_core.client_options import ClientOptions
from google.cloud import texttospeech
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

# --- CONFIGURATION ---
app = Flask(__name__)

# --- CACHE CONFIGURATION ---
# Use data directory if running in Docker/Podman, otherwise use current directory
DATA_DIR = os.environ.get("DATA_DIR", "data" if os.path.exists("/.dockerenv") else ".")
os.makedirs(DATA_DIR, exist_ok=True)
SUMMARY_CACHE_FILE = os.path.join(DATA_DIR, "summary_cache.json")
LOGIN_ATTEMPTS_FILE = os.path.join(DATA_DIR, "login_attempts.json")
AUDIO_CACHE_DIR = os.path.join(DATA_DIR, "audio_cache")

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
print(f"✅ Audio cache directory is set to: '{AUDIO_CACHE_DIR}/'")


def load_summary_cache():
    if os.path.exists(SUMMARY_CACHE_FILE):
        with open(SUMMARY_CACHE_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_summary_cache(cache_data):
    with open(SUMMARY_CACHE_FILE, "w") as f:
        json.dump(cache_data, f, indent=4)


def load_login_attempts():
    """Load login attempt tracking data"""
    if os.path.exists(LOGIN_ATTEMPTS_FILE):
        with open(LOGIN_ATTEMPTS_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_login_attempts(attempts_data):
    """Save login attempt tracking data"""
    with open(LOGIN_ATTEMPTS_FILE, "w") as f:
        json.dump(attempts_data, f, indent=4)


def clean_expired_attempts(attempts_data):
    """Remove expired lockout entries"""
    current_time = datetime.now(timezone.utc)
    cleaned_data = {}

    for ip, data in attempts_data.items():
        if "locked_until" in data:
            locked_until = datetime.fromisoformat(data["locked_until"])
            if current_time < locked_until:
                # Still locked
                cleaned_data[ip] = data
            # If expired, don't include it (removes the lockout)
        else:
            # Not locked, keep the attempt count
            cleaned_data[ip] = data

    return cleaned_data


def is_ip_locked_out(ip_address):
    """Check if an IP address is currently locked out"""
    if not LOGIN_ENABLED or os.environ.get("TESTING"):
        return False, None

    attempts_data = load_login_attempts()
    attempts_data = clean_expired_attempts(attempts_data)

    if ip_address in attempts_data and "locked_until" in attempts_data[ip_address]:
        locked_until = datetime.fromisoformat(attempts_data[ip_address]["locked_until"])
        current_time = datetime.now(timezone.utc)

        if current_time < locked_until:
            remaining_minutes = int((locked_until - current_time).total_seconds() / 60)
            return True, remaining_minutes

    return False, None


def record_failed_attempt(ip_address):
    """Record a failed login attempt and apply lockout if necessary"""
    if not LOGIN_ENABLED or os.environ.get("TESTING"):
        return False

    attempts_data = load_login_attempts()
    attempts_data = clean_expired_attempts(attempts_data)

    if ip_address not in attempts_data:
        attempts_data[ip_address] = {"count": 0, "first_attempt": datetime.now(timezone.utc).isoformat()}

    attempts_data[ip_address]["count"] += 1
    attempts_data[ip_address]["last_attempt"] = datetime.now(timezone.utc).isoformat()

    # Check if we should lock out this IP
    if attempts_data[ip_address]["count"] >= MAX_LOGIN_ATTEMPTS:
        lockout_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION)
        attempts_data[ip_address]["locked_until"] = lockout_until.isoformat()
        attempts_data[ip_address]["count"] = 0  # Reset counter

        save_login_attempts(attempts_data)
        return True  # Locked out

    save_login_attempts(attempts_data)
    return False  # Not locked out yet


def reset_failed_attempts(ip_address):
    """Clear failed attempt count for an IP after successful login"""
    if not LOGIN_ENABLED or os.environ.get("TESTING"):
        return

    attempts_data = load_login_attempts()
    if ip_address in attempts_data:
        # Remove the IP's record entirely on successful login
        del attempts_data[ip_address]
        save_login_attempts(attempts_data)


summary_cache = load_summary_cache()
print(f"✅ Loaded {len(summary_cache)} summaries from cache.")


# --- LOGIN CONFIGURATION ---
LOGIN_ENABLED = os.environ.get("LOGIN_ENABLED", "false").lower() == "true"
LOGIN_CODE = os.environ.get("LOGIN_CODE", "")
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "")
MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
LOCKOUT_DURATION = int(os.environ.get("LOCKOUT_DURATION", "15"))  # minutes

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


# --- API CLIENT INITIALIZATION ---
api_key = os.environ.get("GOOGLE_API_KEY")
tts_client = None
youtube = None
model = None

# Only initialize API clients if API key is available and we're not in test mode
if api_key and not os.environ.get("TESTING"):
    try:
        tts_client = texttospeech.TextToSpeechClient(client_options=ClientOptions(api_key=api_key))
        genai.configure(api_key=api_key)
        youtube = build("youtube", "v3", developerKey=api_key)
        model = genai.GenerativeModel(model_name="gemini-2.5-flash-preview-05-20")
    except Exception as e:
        print(f"Warning: Could not configure APIs. Error: {e}")
elif not api_key and not os.environ.get("TESTING"):
    print("Warning: GOOGLE_API_KEY environment variable is not set. Some features will be unavailable.")

# For testing, create the model even without API key
if os.environ.get("TESTING") and not model:
    try:
        model = genai.GenerativeModel(model_name="gemini-2.5-flash-preview-05-20")
    except Exception:
        pass


# --- HELPER FUNCTIONS (No changes) ---
def clean_youtube_url(url):
    if not isinstance(url, str) or not url.strip():
        return ""
    # First remove &list=WL from the URL
    url = url.replace("&list=WL", "")
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    # Only keep 'v' and 'list' parameters, but exclude 'list' if it's 'WL'
    allowed_params = {}
    for k in ["v", "list"]:
        if k in query_params:
            if k == "list" and query_params[k][0] == "WL":
                continue  # Skip watch later list
            allowed_params[k] = query_params[k]
    return urlunparse(parsed_url._replace(query=urlencode(allowed_params, doseq=True)))


def get_playlist_id(url):
    url = url.replace("&list=WL", "")
    match = re.search(r"list=([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


def get_video_id(url):
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11}).*",
    ]
    for pattern in patterns:
        if match := re.search(pattern, url):
            return match.group(1)
    return None


def get_video_details(video_ids):
    details = {}
    if not youtube:
        print("YouTube API client not initialized")
        return {}
    try:
        request = youtube.videos().list(part="snippet", id=",".join(video_ids))
        response = request.execute()
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            details[item["id"]] = {
                "title": snippet.get("title", "Unknown Title"),
                "thumbnail_url": snippet.get("thumbnails", {}).get("medium", {}).get("url"),
            }
        return details
    except HttpError as e:
        print(f"Error fetching video details: {e}")
        return {}


def get_videos_from_playlist(playlist_id):
    if not youtube:
        return None, "YouTube API client not initialized"
    video_items = []
    next_page_token = None
    while True:
        try:
            pl_request = youtube.playlistItems().list(
                part="contentDetails,snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token,
            )
            pl_response = pl_request.execute()
            video_items.extend(pl_response.get("items", []))
            next_page_token = pl_response.get("nextPageToken")
            if not next_page_token:
                break
        except HttpError as e:
            return None, f"Could not fetch playlist. Is it public? Error: {e}"
    return video_items, None


def get_transcript(video_id):
    if not video_id:
        return None, "No video ID provided"
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US"])
        transcript_text = " ".join([d["text"] for d in transcript_list])
        return (transcript_text, None) if transcript_text.strip() else (None, "Transcript was found but it is empty.")
    except NoTranscriptFound:
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id).find_transcript(["en"]).fetch()
            transcript_text = " ".join([d["text"] for d in transcript_list])
            return (
                (transcript_text, None)
                if transcript_text.strip()
                else (None, "A transcript was found, but it is empty.")
            )
        except (NoTranscriptFound, TranscriptsDisabled):
            return None, "No transcripts are available for this video."
        except Exception as e:
            return (
                None,
                f"An unexpected error occurred while fetching the fallback transcript: {e}",
            )
    except TranscriptsDisabled:
        return None, "Transcripts are disabled for this video."
    except Exception as e:
        return (
            None,
            f"An unexpected error occurred. This can happen if YouTube is temporarily blocking requests. (Error: {e})",
        )


def generate_summary(transcript, title):
    if not transcript:
        return None, "Cannot generate summary from empty transcript."
    prompt_update = f"""
    **Your Role:** You are an expert content summarizer, specializing in transforming detailed video transcripts
    into a single, cohesive, and engaging audio-friendly summary. Your goal is to create a narrative that is not
    only informative but also easy for a listener to understand and retain when read aloud.

    **Your Task:** I will provide you with a transcript from a YouTube video. Your task is to synthesize this
    transcript into one continuous, audio-friendly summary.

    Within this summary, you must identify the 3-10 most critical points or actionable insights and seamlessly
    weave them into the narrative. You should introduce these key points using natural, conversational phrases
    that draw the listener's attention to their importance.

    **Key Constraints for the Summary:**

    * **No Markdown or Special Characters:** Do not use any text formatting like asterisks, bolding, or italics
    in your output. All emphasis must come from the words you choose and the structure of your sentences, not
    from formatting.
    * **Integrated Takeaways:** Do not create a separate bulleted list. Instead, highlight the main takeaways
    within the summary itself. Use clear signposting phrases like:
        * "The first key idea is..."
        * "This brings us to a really important point..."
        * "A critical takeaway here is that..."
        * "And this is the main thing to remember:"
    * **Clarity and Simplicity:** Use simple, everyday language. Avoid jargon and complex vocabulary. If you
    must use an acronym, state the full term first.
    * **Conversational Tone:** Write as if you were enthusiastically explaining the video to an interested
    friend. The tone should be engaging, clear, and natural.
    * **Short, Scannable Sentences:** Construct short, direct sentences. This makes the information easier
    for a listener to process and helps the audio flow better.
    * **Logical Flow & Pacing:** Ensure the summary moves logically from one idea to the next. Use short
    paragraphs to create natural pauses, giving the listener a moment to digest the information.
    * **Engaging Introduction and Conclusion:** Start with a hook that grabs the listener's interest and end
    with a concise wrap-up that reinforces the video's central message.

    **Example of Desired Output Structure:**

    (Start with a brief, engaging introduction that hooks the listener and states the video's main topic.)

    (In the next paragraph, begin explaining the video's concepts. When you reach the first main insight,
    introduce it naturally. For example: The video starts by explaining the basics of the topic. But the
    first key idea to really focus on is that you need to master the fundamentals before moving on. The
    creator emphasizes this because...)

    (Continue the summary, weaving in the other key takeaways with similar conversational signposts. Each
    point should flow smoothly into the next.)

    (Conclude with a short, memorable wrap-up that summarizes the core message and leaves the listener with
    a clear understanding of the video's value.)

    ---

    **{transcript}**"""
    try:
        response = model.generate_content(prompt_update)
        return response.text, None
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return None, f"Error calling Gemini API: {e}"


# --- AUTHENTICATION DECORATOR ---
def require_auth(f):
    """Decorator to require authentication for routes when login is enabled"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip authentication if login is disabled or in testing mode
        if not LOGIN_ENABLED or os.environ.get("TESTING"):
            return f(*args, **kwargs)

        # Check if user is authenticated
        if not session.get("authenticated", False):
            # For API endpoints, return JSON error
            # Check for JSON content-type OR specific API endpoints
            api_endpoints = [
                "/summarize",
                "/speak",
                "/get_cached_summaries",
                "/search_summaries",
                "/debug_transcript",
                "/login_status",
                "/api_status",
            ]

            is_api_request = (
                request.content_type == "application/json"
                or any(request.path.startswith(endpoint) for endpoint in api_endpoints)
                or request.headers.get("Accept", "").startswith("application/json")
            )

            if is_api_request:
                return (
                    jsonify({"error": "Authentication required", "message": "Please login to access this resource"}),
                    401,
                )

            # For web pages, redirect to login
            return redirect(url_for("login_page"))

        return f(*args, **kwargs)

    return decorated_function


# --- API ENDPOINTS ---


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
    client_ip = request.environ.get("HTTP_X_FORWARDED_FOR", request.environ.get("REMOTE_ADDR", "127.0.0.1"))
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

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
                    jsonify({"success": False, "error": "Invalid passcode", "remaining_attempts": remaining_attempts}),
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


@app.route("/get_cached_summaries", methods=["GET"])
@require_auth
def get_cached_summaries():
    if not summary_cache:
        return jsonify([])

    # Get limit parameter from query string, default to None (no limit)
    limit = request.args.get("limit", type=int)

    cached_list = [
        {
            "type": "video",
            "title": d["title"],
            "thumbnail_url": d["thumbnail_url"],
            "summary": d["summary"],
            "summarized_at": d.get("summarized_at"),
            "video_url": d.get("video_url"),
            "error": None,
        }
        for d in summary_cache.values()
    ]
    cached_list.sort(key=lambda x: x.get("summarized_at", "1970-01-01T00:00:00.000000"), reverse=True)

    # Apply limit if specified
    if limit is not None:
        if limit == 0:
            cached_list = []
        elif limit > 0:
            cached_list = cached_list[:limit]
        # If limit < 0 or invalid, ignore it and return all results

    return jsonify(cached_list)


@app.route("/search_summaries", methods=["GET"])
@require_auth
def search_summaries():
    query = request.args.get("q", "").strip()
    if not query:
        return (
            jsonify({"error": "Query parameter 'q' is required and cannot be empty"}),
            400,
        )

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
        "google_api_key_set": bool(api_key),
        "youtube_client_initialized": youtube is not None,
        "tts_client_initialized": tts_client is not None,
        "ai_model_initialized": model is not None,
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


@app.route("/summarize", methods=["POST"])
@require_auth
def summarize_links():
    try:
        # Parse request data
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON in request body"}), 400
        urls = data.get("urls", [])
        if not urls:
            return jsonify({"error": "No URLs provided"}), 400

        results = []
        for url in urls:
            playlist_id, video_id = get_playlist_id(url), get_video_id(url)

            if playlist_id:
                try:
                    if not youtube:
                        results.append(
                            {
                                "type": "error",
                                "url": url,
                                "error": "YouTube API client not initialized",
                            }
                        )
                        continue
                    pl_meta_request = youtube.playlists().list(part="snippet", id=playlist_id)
                    pl_meta_response = pl_meta_request.execute()
                    if not pl_meta_response.get("items"):
                        results.append(
                            {
                                "type": "error",
                                "url": url,
                                "error": "Could not find this playlist.",
                            }
                        )
                        continue
                    playlist_title = pl_meta_response["items"][0]["snippet"]["title"]
                    playlist_items, error = get_videos_from_playlist(playlist_id)
                    if error:
                        results.append(
                            {
                                "type": "playlist",
                                "title": playlist_title,
                                "error": error,
                                "summaries": [],
                            }
                        )
                        continue

                    playlist_summaries = []
                    for item in playlist_items:
                        snippet = item.get("snippet", {})
                        vid_id = snippet.get("resourceId", {}).get("videoId")
                        vid_title, thumbnail_url = snippet.get("title", "Unknown Title"), snippet.get(
                            "thumbnails", {}
                        ).get("medium", {}).get("url")

                        if vid_title in ["Private video", "Deleted video"]:
                            playlist_summaries.append(
                                {
                                    "video_id": vid_id,
                                    "title": vid_title,
                                    "thumbnail_url": thumbnail_url,
                                    "summary": None,
                                    "error": "Video is private or deleted.",
                                }
                            )
                            continue

                        if vid_id in summary_cache:
                            cached_item = summary_cache[vid_id]
                            playlist_summaries.append(
                                {
                                    "video_id": vid_id,
                                    "title": cached_item["title"],
                                    "thumbnail_url": cached_item["thumbnail_url"],
                                    "summary": cached_item["summary"],
                                    "video_url": cached_item.get(
                                        "video_url",
                                        f"https://www.youtube.com/watch?v={vid_id}",
                                    ),
                                    "error": None,
                                }
                            )
                            continue

                        transcript, err = get_transcript(vid_id)
                        summary, err = (None, err) if err else generate_summary(transcript, vid_title)

                        if summary and not err:
                            audio_filename = f"{hashlib.sha256(summary.encode('utf-8')).hexdigest()}.mp3"
                            # --- MODIFICATION START ---
                            video_url = f"https://www.youtube.com/watch?v={vid_id}"
                            summary_cache[vid_id] = {
                                "title": vid_title,
                                "summary": summary,
                                "thumbnail_url": thumbnail_url,
                                "summarized_at": datetime.now(timezone.utc).isoformat(),
                                "audio_filename": audio_filename,
                                "video_url": video_url,  # Storing the canonical video URL
                            }
                            # --- MODIFICATION END ---
                            save_summary_cache(summary_cache)
                        playlist_summaries.append(
                            {
                                "video_id": vid_id,
                                "title": vid_title,
                                "thumbnail_url": thumbnail_url,
                                "summary": summary,
                                "video_url": f"https://www.youtube.com/watch?v={vid_id}",
                                "error": err,
                            }
                        )
                    results.append(
                        {
                            "type": "playlist",
                            "title": playlist_title,
                            "summaries": playlist_summaries,
                        }
                    )
                except Exception as e:
                    results.append(
                        {
                            "type": "playlist",
                            "title": "Unknown Playlist",
                            "error": f"An unexpected error occurred: {e}",
                            "summaries": [],
                        }
                    )

            elif video_id:
                if video_id in summary_cache:
                    cached_item = summary_cache[video_id]
                    results.append(
                        {
                            "type": "video",
                            "video_id": video_id,
                            "title": cached_item["title"],
                            "thumbnail_url": cached_item["thumbnail_url"],
                            "summary": cached_item["summary"],
                            "video_url": cached_item.get("video_url", f"https://www.youtube.com/watch?v={video_id}"),
                            "error": None,
                        }
                    )
                    continue

                try:
                    details = get_video_details([video_id]).get(video_id, {})
                    title, thumbnail_url = details.get("title", "Unknown Video"), details.get("thumbnail_url")
                    transcript, err = get_transcript(video_id)
                    summary, err = (None, err) if err else generate_summary(transcript, title)

                    if summary and not err:
                        audio_filename = f"{hashlib.sha256(summary.encode('utf-8')).hexdigest()}.mp3"
                        # --- MODIFICATION START ---
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        summary_cache[video_id] = {
                            "title": title,
                            "summary": summary,
                            "thumbnail_url": thumbnail_url,
                            "summarized_at": datetime.now(timezone.utc).isoformat(),
                            "audio_filename": audio_filename,
                            "video_url": video_url,  # Storing the canonical video URL
                        }
                        # --- MODIFICATION END ---
                        save_summary_cache(summary_cache)
                    results.append(
                        {
                            "type": "video",
                            "video_id": video_id,
                            "title": title,
                            "thumbnail_url": thumbnail_url,
                            "summary": summary,
                            "video_url": f"https://www.youtube.com/watch?v={video_id}",
                            "error": err,
                        }
                    )
                except Exception as e:
                    results.append(
                        {
                            "type": "video",
                            "video_id": video_id,
                            "title": "Unknown Video",
                            "error": f"Failed to process video: {e}",
                        }
                    )
            else:
                results.append(
                    {
                        "type": "error",
                        "url": url,
                        "error": "Invalid or unsupported YouTube URL.",
                    }
                )
        return jsonify(results)
    except Exception as e:
        # Catch-all exception handler for the entire endpoint
        app.logger.error(f"Unhandled exception in /summarize: {str(e)}\n{traceback.format_exc()}")
        return (
            jsonify(
                {
                    "error": "An unexpected error occurred while processing your request",
                    "message": str(e),
                    "type": type(e).__name__,
                    "stacktrace": traceback.format_exc(),
                }
            ),
            500,
        )


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
    except Exception as e:
        return jsonify({"error": f"Failed to parse request: {str(e)}"}), 400

    filename = f"{hashlib.sha256(text_to_speak.encode('utf-8')).hexdigest()}.mp3"
    filepath = os.path.join(AUDIO_CACHE_DIR, filename)

    if os.path.exists(filepath):
        print(f"AUDIO CACHE HIT for file: {filename}")
        with open(filepath, "rb") as f:
            audio_content = f.read()
        return Response(audio_content, mimetype="audio/mpeg")

    print(f"AUDIO CACHE MISS for file: {filename}. Generating...")
    try:
        synthesis_input = texttospeech.SynthesisInput(text=text_to_speak)
        voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Studio-O")
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

        response = tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)

        with open(filepath, "wb") as f:
            f.write(response.audio_content)
        print(f"Saved new audio file to cache: {filepath}")

        return Response(response.audio_content, mimetype="audio/mpeg")

    except Exception as e:
        print(f"Error in TTS endpoint: {e}")
        return Response(f"Failed to generate audio: {e}", status=500)


# Error handlers to ensure JSON responses for API endpoints
@app.errorhandler(400)
def bad_request(e):
    api_paths = [
        "/summarize",
        "/speak",
        "/get_cached_summaries",
        "/search_summaries",
        "/debug_transcript",
        "/api_status",
        "/login",
        "/logout",
        "/login_status",
    ]
    if any(request.path.startswith(path) for path in api_paths):
        return jsonify({"error": "Bad request", "message": str(e), "stacktrace": traceback.format_exc()}), 400
    return e


@app.errorhandler(404)
def not_found(e):
    api_paths = [
        "/summarize",
        "/speak",
        "/get_cached_summaries",
        "/search_summaries",
        "/debug_transcript",
        "/api_status",
        "/login",
        "/logout",
        "/login_status",
    ]
    if any(request.path.startswith(path) for path in api_paths):
        return jsonify({"error": "Endpoint not found", "message": str(e), "path": request.path}), 404
    return e


@app.errorhandler(500)
def server_error(e):
    api_paths = [
        "/summarize",
        "/speak",
        "/get_cached_summaries",
        "/search_summaries",
        "/debug_transcript",
        "/api_status",
        "/login",
        "/logout",
        "/login_status",
    ]
    if any(request.path.startswith(path) for path in api_paths):
        return jsonify({"error": "Internal server error", "message": str(e), "stacktrace": traceback.format_exc()}), 500
    return e


@app.errorhandler(Exception)
def handle_exception(e):
    # Log the error with full traceback
    app.logger.error(f"Unhandled exception: {str(e)}\n{traceback.format_exc()}")
    api_paths = [
        "/summarize",
        "/speak",
        "/get_cached_summaries",
        "/search_summaries",
        "/debug_transcript",
        "/api_status",
        "/login",
        "/logout",
        "/login_status",
    ]
    if any(request.path.startswith(path) for path in api_paths):
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


if __name__ == "__main__":
    # Enable debug mode only in development (configurable via environment variable)
    debug_mode = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(debug=debug_mode, port=5001)
