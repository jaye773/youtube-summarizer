import json
import os
from datetime import datetime, timezone


def load_summary_cache(cache_file):
    """Load the summary cache from disk.

    Args:
        cache_file: Path to the JSON cache file.

    Returns:
        dict: The loaded cache, or an empty dict if the file does not exist or
              contains invalid JSON.
    """
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_summary_cache(cache, cache_file):
    """Persist the summary cache to disk.

    Args:
        cache: dict mapping video_id to cache entry dicts.
        cache_file: Path to the JSON cache file.
    """
    with open(cache_file, "w") as f:
        json.dump(cache, f, indent=4)


def build_cache_entry(title, summary, thumbnail_url, video_id, model_key, audio_filename=None):
    """Construct a standardised cache entry dict for a summarised video.

    Args:
        title: Human-readable video title.
        summary: Generated summary text.
        thumbnail_url: URL of the video thumbnail image.
        video_id: YouTube video ID (used to build the canonical video URL).
        model_key: Identifier of the AI model used to generate the summary.
        audio_filename: Optional filename of the pre-generated audio file.

    Returns:
        dict: A cache entry ready to be stored under summary_cache[video_id].
    """
    return {
        "title": title,
        "summary": summary,
        "thumbnail_url": thumbnail_url,
        "summarized_at": datetime.now(timezone.utc).isoformat(),
        "audio_filename": audio_filename,
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "model_used": model_key,
    }
