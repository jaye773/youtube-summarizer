import hashlib  # For generating filenames
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request
from google.api_core.client_options import ClientOptions
from google.cloud import texttospeech
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

# Load environment variables from .env file
load_dotenv()

# --- CONFIGURATION ---
app = Flask(__name__)

# --- CACHE CONFIGURATION ---
# Use data directory if running in Docker/Podman, otherwise use current directory
DATA_DIR = os.environ.get("DATA_DIR", "data" if os.path.exists("/.dockerenv") else ".")
os.makedirs(DATA_DIR, exist_ok=True)
SUMMARY_CACHE_FILE = os.path.join(DATA_DIR, "summary_cache.json")
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


summary_cache = load_summary_cache()
print(f"✅ Loaded {len(summary_cache)} summaries from cache.")


# --- API CLIENT INITIALIZATION ---
api_key = os.environ.get("GOOGLE_API_KEY")
tts_client = None
youtube = None
model = None

# Only initialize API clients if API key is available and we're not in test mode
if api_key and not os.environ.get("TESTING"):
    try:
        print("🔑 Initializing Google APIs...")
        tts_client = texttospeech.TextToSpeechClient(client_options=ClientOptions(api_key=api_key))
        genai.configure(api_key=api_key)
        youtube = build("youtube", "v3", developerKey=api_key)
        model = genai.GenerativeModel(model_name="gemini-2.5-flash-preview-05-20")
        print("✅ Google APIs initialized successfully!")
    except Exception as e:
        print(f"❌ Error: Could not initialize Google APIs. Error: {e}")
        print("🔧 Please check your GOOGLE_API_KEY and ensure it has the required permissions.")
        print("📋 Required APIs: YouTube Data API v3, Generative AI API, Text-to-Speech API")
elif not api_key and not os.environ.get("TESTING"):
    print("❌ Error: GOOGLE_API_KEY environment variable is not set!")
    print("🔧 To fix this:")
    print("   1. Create a .env file in the project root with: GOOGLE_API_KEY=your_api_key_here")
    print("   2. Or export the variable: export GOOGLE_API_KEY=your_api_key_here")
    print("   3. Get your API key from: https://console.cloud.google.com/")
    print("📋 Required APIs: YouTube Data API v3, Generative AI API, Text-to-Speech API")
    print("⚠️  Some features will be unavailable until this is fixed.")

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
    patterns = [r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", r"(?:youtu\.be\/)([0-9A-Za-z_-]{11}).*"]
    for pattern in patterns:
        if match := re.search(pattern, url):
            return match.group(1)
    return None


def get_video_details(video_ids):
    details = {}
    if not youtube:
        print("❌ YouTube API client not initialized - check your GOOGLE_API_KEY configuration")
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
        return None, "YouTube API client not initialized. Please check your GOOGLE_API_KEY configuration."
    video_items = []
    next_page_token = None
    while True:
        try:
            pl_request = youtube.playlistItems().list(
                part="contentDetails,snippet", playlistId=playlist_id, maxResults=50, pageToken=next_page_token
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

    # First, try to get transcript in preferred languages
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US"])
        transcript_text = " ".join([d["text"] for d in transcript_list])
        return (transcript_text, None) if transcript_text.strip() else (None, "Transcript was found but it is empty.")
    except NoTranscriptFound:
        # Try fallback approach with any available English transcript
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
            error_msg = str(e).lower()
            if "no element found" in error_msg or "xml" in error_msg:
                return (
                    None,
                    "YouTube transcript service returned invalid data. The video may have unusual "
                    "transcript formatting or YouTube may be temporarily blocking requests.",
                )
            return None, f"An unexpected error occurred while fetching the fallback transcript: {e}"
    except TranscriptsDisabled:
        return None, "Transcripts are disabled for this video."
    except Exception as e:
        error_msg = str(e).lower()
        if "no element found" in error_msg or "xml" in error_msg:
            return (
                None,
                "YouTube transcript service returned invalid data. This can happen if YouTube is "
                "temporarily blocking requests or if the video has unusual transcript formatting. "
                "Please try again in a few minutes.",
            )
        elif "rate limit" in error_msg or "quota" in error_msg:
            return None, "YouTube API rate limit exceeded. Please try again later."
        elif "timeout" in error_msg or "connection" in error_msg:
            return None, "Network connection issue. Please check your internet connection and try again."
        else:
            return (
                None,
                f"An unexpected error occurred: {e}. This can happen if YouTube is temporarily blocking requests.",
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


# --- API ENDPOINTS ---


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/get_cached_summaries", methods=["GET"])
def get_cached_summaries():
    if not summary_cache:
        return jsonify([])
    cached_list = [
        {
            "type": "video",
            "title": d["title"],
            "thumbnail_url": d["thumbnail_url"],
            "summary": d["summary"],
            "summarized_at": d.get("summarized_at"),
            "error": None,
        }
        for d in summary_cache.values()
    ]
    cached_list.sort(key=lambda x: x.get("summarized_at", "1970-01-01T00:00:00.000000"), reverse=True)
    return jsonify(cached_list)


@app.route("/search_summaries", methods=["GET"])
def search_summaries():
    """Search through cached summaries by title and content"""
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify({"error": "No search query provided"}), 400

    if not summary_cache:
        return jsonify([])

    # Search through cached summaries
    matching_summaries = []
    for video_id, data in summary_cache.items():
        title = data.get("title", "").lower()
        summary = data.get("summary", "").lower()

        # Check if query matches title or summary content
        if query in title or query in summary:
            matching_summaries.append(
                {
                    "type": "video",
                    "video_id": video_id,
                    "title": data["title"],
                    "thumbnail_url": data["thumbnail_url"],
                    "summary": data["summary"],
                    "summarized_at": data.get("summarized_at"),
                    "video_url": data.get("video_url"),
                    "error": None,
                }
            )

    # Sort by summarized_at (most recent first)
    matching_summaries.sort(key=lambda x: x.get("summarized_at", "1970-01-01T00:00:00.000000"), reverse=True)
    return jsonify(matching_summaries)


@app.route("/api_status", methods=["GET"])
def api_status():
    """Check the status of API configurations"""
    status = {
        "google_api_key_set": bool(os.environ.get("GOOGLE_API_KEY")),
        "youtube_client_initialized": youtube is not None,
        "tts_client_initialized": tts_client is not None,
        "ai_model_initialized": model is not None,
        "testing_mode": bool(os.environ.get("TESTING")),
    }

    if not status["google_api_key_set"]:
        status["error"] = "GOOGLE_API_KEY environment variable is not set"
        status["fix_instructions"] = [
            "Create a .env file with: GOOGLE_API_KEY=your_api_key_here",
            "Or export the variable: export GOOGLE_API_KEY=your_api_key_here",
            "Get your API key from: https://console.cloud.google.com/",
            "Enable: YouTube Data API v3, Generative AI API, Text-to-Speech API",
        ]
    elif not any(
        [status["youtube_client_initialized"], status["tts_client_initialized"], status["ai_model_initialized"]]
    ):
        status["error"] = "API clients failed to initialize - check your API key permissions"
        status["fix_instructions"] = [
            "Verify your API key is valid",
            "Check that required APIs are enabled in Google Cloud Console",
            "Ensure your API key has the necessary permissions",
        ]
    else:
        status["message"] = "API configuration looks good!"

    return jsonify(status)


@app.route("/debug_transcript", methods=["GET"])
def debug_transcript():
    """Debug endpoint to test transcript fetching for a specific video"""
    video_url = request.args.get("url", "").strip()
    if not video_url:
        return jsonify({"error": "No video URL provided. Use ?url=youtube_video_url"}), 400

    video_id = get_video_id(video_url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL or could not extract video ID"}), 400

    # Get video details
    video_details = get_video_details([video_id]).get(video_id, {})

    # Try to get transcript
    transcript, error = get_transcript(video_id)

    debug_info = {
        "video_id": video_id,
        "video_url": video_url,
        "video_title": video_details.get("title", "Unknown"),
        "thumbnail_url": video_details.get("thumbnail_url"),
        "transcript_success": transcript is not None,
        "transcript_length": len(transcript) if transcript else 0,
        "error": error,
        "youtube_api_working": youtube is not None,
    }

    if transcript:
        # Only include first 500 characters of transcript for debugging
        debug_info["transcript_preview"] = transcript[:500] + "..." if len(transcript) > 500 else transcript

    return jsonify(debug_info)


@app.route("/summarize", methods=["POST"])
def summarize_links():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON in request body"}), 400
        urls = data.get("urls", [])
        if not urls:
            return jsonify({"error": "No URLs provided"}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to parse request: {str(e)}"}), 400

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
                            "error": (
                                "YouTube API client not initialized. Please check your GOOGLE_API_KEY "
                                "configuration and ensure YouTube Data API v3 is enabled."
                            ),
                        }
                    )
                    continue
                pl_meta_request = youtube.playlists().list(part="snippet", id=playlist_id)
                pl_meta_response = pl_meta_request.execute()
                if not pl_meta_response.get("items"):
                    results.append({"type": "error", "url": url, "error": "Could not find this playlist."})
                    continue
                playlist_title = pl_meta_response["items"][0]["snippet"]["title"]
                playlist_items, error = get_videos_from_playlist(playlist_id)
                if error:
                    results.append({"type": "playlist", "title": playlist_title, "error": error, "summaries": []})
                    continue

                playlist_summaries = []
                for item in playlist_items:
                    snippet = item.get("snippet", {})
                    vid_id = snippet.get("resourceId", {}).get("videoId")
                    vid_title, thumbnail_url = snippet.get("title", "Unknown Title"), snippet.get("thumbnails", {}).get(
                        "medium", {}
                    ).get("url")

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
                            "error": err,
                        }
                    )
                results.append({"type": "playlist", "title": playlist_title, "summaries": playlist_summaries})
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
            results.append({"type": "error", "url": url, "error": "Invalid or unsupported YouTube URL."})
    return jsonify(results)


@app.route("/speak", methods=["POST"])
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
        "/api_status",
        "/debug_transcript",
    ]
    if any(request.path.startswith(path) for path in api_paths):
        return jsonify({"error": "Bad request: " + str(e)}), 400
    return e


@app.errorhandler(404)
def not_found(e):
    api_paths = [
        "/summarize",
        "/speak",
        "/get_cached_summaries",
        "/search_summaries",
        "/api_status",
        "/debug_transcript",
    ]
    if any(request.path.startswith(path) for path in api_paths):
        return jsonify({"error": "Endpoint not found"}), 404
    return e


@app.errorhandler(500)
def server_error(e):
    api_paths = [
        "/summarize",
        "/speak",
        "/get_cached_summaries",
        "/search_summaries",
        "/api_status",
        "/debug_transcript",
    ]
    if any(request.path.startswith(path) for path in api_paths):
        return jsonify({"error": "Internal server error: " + str(e)}), 500
    return e


@app.errorhandler(Exception)
def handle_exception(e):
    # Log the error
    app.logger.error(f"Unhandled exception: {str(e)}")
    api_paths = [
        "/summarize",
        "/speak",
        "/get_cached_summaries",
        "/search_summaries",
        "/api_status",
        "/debug_transcript",
    ]
    if any(request.path.startswith(path) for path in api_paths):
        return jsonify({"error": "An unexpected error occurred: " + str(e)}), 500
    # For non-API routes, let Flask handle it normally
    return e


if __name__ == "__main__":
    app.run(debug=True, port=5001)
