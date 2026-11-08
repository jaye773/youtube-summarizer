"""
YouTube Helpers Module

Utility functions for interacting with the YouTube Data API and
YouTube Transcript API. The youtube API client and proxy config
function are injected at startup to avoid circular imports.
"""

import re
import socket
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from googleapiclient.errors import HttpError
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

# --- Injected dependencies ---
# Set via set_youtube_client() after the API client is created in app.py
youtube = None

# Set via set_proxy_config_func() after get_proxy_config is defined in app.py
_get_proxy_config = None


def set_youtube_client(client):
    """Inject the YouTube API client built in app.py."""
    global youtube
    youtube = client


def set_proxy_config_func(func):
    """Inject the get_proxy_config callable from app.py."""
    global _get_proxy_config
    _get_proxy_config = func


# --- URL helpers ---

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


# --- YouTube Data API helpers ---

def get_video_details(video_ids, max_retries=3):
    """
    Get video details from YouTube API with retry logic for timeout errors.

    Args:
        video_ids: List of video IDs to fetch details for
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        Dictionary of video details or empty dict on failure
    """
    details = {}
    if not youtube:
        print("YouTube API client not initialized")
        return {}

    retry_count = 0
    base_delay = 1  # Start with 1 second delay

    while retry_count <= max_retries:
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

        except (socket.timeout, TimeoutError, OSError) as e:
            retry_count += 1
            if retry_count > max_retries:
                print(f"Max retries ({max_retries}) exceeded for video details. Error: {e}")
                return {}

            # Exponential backoff with jitter
            delay = base_delay * (2 ** (retry_count - 1)) + (0.1 * retry_count)
            print(
                f"Timeout error fetching video details (attempt {retry_count}/{max_retries}). "
                f"Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)

        except HttpError as e:
            # For HTTP errors, check if it's a temporary issue
            if e.resp.status in [500, 502, 503, 504]:  # Server errors
                retry_count += 1
                if retry_count > max_retries:
                    print(f"Max retries ({max_retries}) exceeded for video details. HTTP Error: {e}")
                    return {}

                delay = base_delay * (2 ** (retry_count - 1))
                print(f"HTTP {e.resp.status} error (attempt {retry_count}/{max_retries}). Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                # For other HTTP errors, don't retry
                print(f"Error fetching video details: {e}")
                return {}

        except Exception as e:
            print(f"Unexpected error fetching video details: {e}")
            return {}

    return {}


def get_videos_from_playlist(playlist_id, max_retries=3):
    """
    Get videos from a YouTube playlist with retry logic for timeout errors.

    Args:
        playlist_id: YouTube playlist ID
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        Tuple of (video_items list, error message)
    """
    if not youtube:
        return None, "YouTube API client not initialized"

    video_items = []
    next_page_token = None

    while True:
        retry_count = 0
        base_delay = 1

        while retry_count <= max_retries:
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
                break  # Success, exit retry loop

            except (socket.timeout, TimeoutError, OSError) as e:
                retry_count += 1
                if retry_count > max_retries:
                    return (
                        None,
                        f"Timeout error fetching playlist after {max_retries} retries: {e}",
                    )

                # Exponential backoff with jitter
                delay = base_delay * (2 ** (retry_count - 1)) + (0.1 * retry_count)
                print(
                    f"Timeout error fetching playlist (attempt {retry_count}/{max_retries}). "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)

            except HttpError as e:
                # For HTTP errors, check if it's a temporary issue
                if e.resp.status in [500, 502, 503, 504]:  # Server errors
                    retry_count += 1
                    if retry_count > max_retries:
                        return (
                            None,
                            f"Server error fetching playlist after {max_retries} retries: {e}",
                        )

                    delay = base_delay * (2 ** (retry_count - 1))
                    print(
                        f"HTTP {e.resp.status} error (attempt {retry_count}/{max_retries}). Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    # For other HTTP errors (like 403, 404), don't retry
                    return None, f"Could not fetch playlist. Is it public? Error: {e}"

            except Exception as e:
                return None, f"Unexpected error fetching playlist: {e}"

        if not next_page_token:
            break

    return video_items, None


# --- Transcript helper ---

def get_transcript(video_id):
    if not video_id:
        return None, "No video ID provided"

    # Get proxy configuration if available
    proxies = _get_proxy_config() if _get_proxy_config is not None else None

    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US"], proxies=proxies)
        transcript_text = " ".join([d["text"] for d in transcript_list])
        return (transcript_text, None) if transcript_text.strip() else (None, "Transcript was found but it is empty.")
    except NoTranscriptFound:
        try:
            fetched = (
                YouTubeTranscriptApi.list_transcripts(video_id, proxies=proxies).find_transcript(["en"]).fetch()
            )
            # youtube-transcript-api 1.x returns a FetchedTranscript of snippet
            # objects; 0.x returned a list of dicts. Normalize both to text.
            if hasattr(fetched, "to_raw_data"):
                fetched = fetched.to_raw_data()
            transcript_text = " ".join([seg["text"] if isinstance(seg, dict) else seg.text for seg in fetched])
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
