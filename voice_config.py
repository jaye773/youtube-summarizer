# Voice Configuration for YouTube Summarizer
# Google Cloud Text-to-Speech HD Voice Options

AVAILABLE_VOICES = {
    # Tier 1: Chirp3-HD (Premium AI Voices)
    "en-US-Chirp3-HD-Zephyr": {
        "name": "en-US-Chirp3-HD-Zephyr",
        "display_name": "Zephyr (Premium Female)",
        "language_code": "en-US",
        "gender": "female",
        "accent": "US",
        "style": "narrative",
        "tier": "chirp3-hd",
        "description": "Premium AI voice, excellent for narration and storytelling",
        "quality": "premium",
    },
    "en-US-Chirp3-HD-Charon": {
        "name": "en-US-Chirp3-HD-Charon",
        "display_name": "Charon (Premium Male)",
        "language_code": "en-US",
        "gender": "male",
        "accent": "US",
        "style": "authoritative",
        "tier": "chirp3-hd",
        "description": "Premium AI voice with authoritative tone for professional content",
        "quality": "premium",
    },
    "en-US-Chirp3-HD-Leda": {
        "name": "en-US-Chirp3-HD-Leda",
        "display_name": "Leda (Premium Female)",
        "language_code": "en-US",
        "gender": "female",
        "accent": "US",
        "style": "versatile",
        "tier": "chirp3-hd",
        "description": "Premium AI voice, versatile and perfect for diverse content",
        "quality": "premium",
    },
    "en-US-Chirp3-HD-Aoede": {
        "name": "en-US-Chirp3-HD-Aoede",
        "display_name": "Aoede (Premium Female)",
        "language_code": "en-US",
        "gender": "female",
        "accent": "US",
        "style": "smooth",
        "tier": "chirp3-hd",
        "description": "Premium AI voice with smooth delivery for educational content",
        "quality": "premium",
    },
    # Tier 2: Neural2 (High Quality)
    "en-US-Neural2-C": {
        "name": "en-US-Neural2-C",
        "display_name": "Neural2-C (Female)",
        "language_code": "en-US",
        "gender": "female",
        "accent": "US",
        "style": "storytelling",
        "tier": "neural2",
        "description": "Natural storytelling voice with warm delivery",
        "quality": "high",
    },
    "en-US-Neural2-J": {
        "name": "en-US-Neural2-J",
        "display_name": "Neural2-J (Male)",
        "language_code": "en-US",
        "gender": "male",
        "accent": "US",
        "style": "professional",
        "tier": "neural2",
        "description": "Professional business tone, clear and confident",
        "quality": "high",
    },
    "en-US-Neural2-F": {
        "name": "en-US-Neural2-F",
        "display_name": "Neural2-F (Female)",
        "language_code": "en-US",
        "gender": "female",
        "accent": "US",
        "style": "warm",
        "tier": "neural2",
        "description": "Warm, engaging delivery perfect for educational content",
        "quality": "high",
    },
    # Tier 3: Studio & WaveNet (Standard Quality)
    "en-US-Studio-O": {
        "name": "en-US-Studio-O",
        "display_name": "Studio-O (Female)",
        "language_code": "en-US",
        "gender": "female",
        "accent": "US",
        "style": "professional",
        "tier": "studio",
        "description": "Professional narrator with clear articulation",
        "quality": "standard",
    },
    "en-US-Wavenet-H": {
        "name": "en-US-Wavenet-H",
        "display_name": "Wavenet-H (Female)",
        "language_code": "en-US",
        "gender": "female",
        "accent": "US",
        "style": "human-like",
        "tier": "wavenet",
        "description": "Human-like inflection with natural speech patterns",
        "quality": "standard",
    },
    "en-US-Wavenet-D": {
        "name": "en-US-Wavenet-D",
        "display_name": "Wavenet-D (Male)",
        "language_code": "en-US",
        "gender": "male",
        "accent": "US",
        "style": "technical",
        "tier": "wavenet",
        "description": "Clear technical delivery, ideal for instructional content",
        "quality": "standard",
    },
    "en-GB-Neural2-A": {
        "name": "en-GB-Neural2-A",
        "display_name": "Neural2-A (British Female)",
        "language_code": "en-GB",
        "gender": "female",
        "accent": "UK",
        "style": "professional",
        "tier": "neural2",
        "description": "British accent with professional tone",
        "quality": "high",
    },
}

# Default voice selection
DEFAULT_VOICE = "en-US-Chirp3-HD-Zephyr"

# Cache configuration
CACHE_CONFIG = {
    "max_size_mb": 50,  # Maximum cache size in MB
    "max_files": 100,  # Maximum number of cached files
    "ttl_hours": 72,  # Time to live in hours
    "cleanup_threshold": 0.8,  # Cleanup when cache reaches 80% of max size
}

# Fallback chain for voice selection
FALLBACK_VOICES = [
    "en-US-Chirp3-HD-Zephyr",  # Premium default
    "en-US-Neural2-C",  # High quality female
    "en-US-Neural2-J",  # High quality male
    "en-US-Studio-O",  # Standard female
    "en-US-Wavenet-D",  # Standard male fallback
]


def get_voice_config(voice_name):
    """Get voice configuration for a given voice name."""
    return AVAILABLE_VOICES.get(voice_name)


def get_voice_with_fallback(preferred_voice):
    """Get voice configuration with fallback logic."""
    # Try preferred voice first
    if preferred_voice and preferred_voice in AVAILABLE_VOICES:
        return AVAILABLE_VOICES[preferred_voice]

    # Try fallback chain
    for fallback_voice in FALLBACK_VOICES:
        if fallback_voice in AVAILABLE_VOICES:
            return AVAILABLE_VOICES[fallback_voice]

    # Final fallback - return first available voice
    if AVAILABLE_VOICES:
        return list(AVAILABLE_VOICES.values())[0]

    return None


def get_voices_by_tier():
    """Get voices organized by quality tier."""
    tiers = {"chirp3-hd": [], "neural2": [], "studio": [], "wavenet": []}

    for voice in AVAILABLE_VOICES.values():
        tier = voice.get("tier", "other")
        if tier in tiers:
            tiers[tier].append(voice)

    return tiers


def validate_voice_name(voice_name):
    """Validate if a voice name is supported."""
    return voice_name in AVAILABLE_VOICES


def get_fallback_voice(failed_voice_id):
    """Get fallback voice when primary voice fails."""
    # Skip the failed voice and try next in fallback chain
    fallback_index = 0
    try:
        if failed_voice_id in FALLBACK_VOICES:
            fallback_index = FALLBACK_VOICES.index(failed_voice_id) + 1
    except ValueError:
        fallback_index = 0

    # Return next available voice in chain
    for i in range(fallback_index, len(FALLBACK_VOICES)):
        if FALLBACK_VOICES[i] in AVAILABLE_VOICES:
            return FALLBACK_VOICES[i]

    # Last resort - return first available voice
    return list(AVAILABLE_VOICES.keys())[0] if AVAILABLE_VOICES else None


def get_optimized_cache_key(voice_id, text):
    """Generate optimized cache key using fast hash algorithm."""
    import hashlib

    # Use blake2b for faster hashing than SHA256
    text_hash = hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()
    return f"{voice_id}_{text_hash}"


def cleanup_audio_cache(cache_dir, config=None):
    """Clean up audio cache based on size and age limits."""
    import os
    import time
    from pathlib import Path

    if config is None:
        config = CACHE_CONFIG

    if not os.path.exists(cache_dir):
        return {"cleaned": 0, "size_freed": 0}

    max_size_bytes = config["max_size_mb"] * 1024 * 1024
    max_age_seconds = config["ttl_hours"] * 3600
    max_files = config["max_files"]
    current_time = time.time()

    # Get all cache files with metadata
    cache_files = []
    total_size = 0

    for file_path in Path(cache_dir).glob("*.mp3"):
        stat = file_path.stat()
        age = current_time - stat.st_mtime

        cache_files.append({"path": file_path, "size": stat.st_size, "age": age, "mtime": stat.st_mtime})
        total_size += stat.st_size

    files_to_delete = []

    # Remove files older than TTL
    for file_info in cache_files:
        if file_info["age"] > max_age_seconds:
            files_to_delete.append(file_info)

    # Remove excess files if over limit (oldest first)
    remaining_files = [f for f in cache_files if f not in files_to_delete]
    if len(remaining_files) > max_files:
        remaining_files.sort(key=lambda x: x["mtime"])
        files_to_delete.extend(remaining_files[max_files:])

    # Remove files if cache size exceeds limit (oldest first)
    remaining_files = [f for f in cache_files if f not in files_to_delete]
    remaining_size = sum(f["size"] for f in remaining_files)

    if remaining_size > max_size_bytes:
        remaining_files.sort(key=lambda x: x["mtime"])
        for file_info in remaining_files:
            if remaining_size <= max_size_bytes:
                break
            files_to_delete.append(file_info)
            remaining_size -= file_info["size"]

    # Delete files and track results
    cleaned_files = 0
    size_freed = 0

    for file_info in files_to_delete:
        try:
            file_info["path"].unlink()
            cleaned_files += 1
            size_freed += file_info["size"]
        except OSError as e:
            print(f"Warning: Could not delete {file_info['path']}: {e}")

    return {
        "cleaned": cleaned_files,
        "size_freed": size_freed,
        "total_files": len(cache_files),
        "remaining_files": len(cache_files) - cleaned_files,
        "remaining_size": total_size - size_freed,
    }


def should_cleanup_cache(cache_dir, config=None):
    """Check if cache cleanup is needed."""
    import os
    from pathlib import Path

    if config is None:
        config = CACHE_CONFIG

    if not os.path.exists(cache_dir):
        return False

    max_size_bytes = config["max_size_mb"] * 1024 * 1024
    cleanup_threshold = config["cleanup_threshold"]
    max_files = config["max_files"]

    total_size = 0
    file_count = 0

    for file_path in Path(cache_dir).glob("*.mp3"):
        total_size += file_path.stat().st_size
        file_count += 1

    size_ratio = total_size / max_size_bytes
    file_ratio = file_count / max_files

    return size_ratio > cleanup_threshold or file_ratio > cleanup_threshold


def get_sample_text():
    """Get sample text for voice preview."""
    return "Welcome to YouTube Summarizer! This tool helps you quickly understand video content by generating AI-powered summaries. You can choose from multiple AI models and customize your experience with different voice options for audio playback."
