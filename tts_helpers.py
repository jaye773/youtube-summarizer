"""
TTS (Text-to-Speech) helper functions for the YouTube Summarizer application.

This module contains:
- clean_text_for_tts: Preprocesses text to avoid ASCII pronunciation issues
- synthesize_audio: Encapsulates the Google Cloud TTS synthesis pattern
"""

import re

from google.cloud import texttospeech

from voice_config import get_voice_with_fallback


def clean_text_for_tts(text):
    """
    Clean and preprocess text for text-to-speech to avoid ASCII pronunciation issues.
    Removes or replaces special characters that cause TTS to spell out ASCII codes.
    """
    if not text:
        return text

    # Dictionary of common problematic characters and their replacements
    replacements = {
        # HTML entities (from html.escape)
        "&quot;": "",  # HTML escaped double quotes
        "&#x27;": "",  # HTML escaped single quotes
        "&amp;": " and ",  # HTML escaped ampersand
        "&lt;": " less than ",  # HTML escaped less than
        "&gt;": " greater than ",  # HTML escaped greater than
        # Quotes and apostrophes
        '"': "",  # Remove double quotes
        "'": "",  # Remove single quotes
        "\u2019": "",  # Remove smart apostrophe
        "\u2018": "",  # Remove smart apostrophe
        "\u201d": "",  # Remove smart quote
        "\u201c": "",  # Remove smart quote
        # Dashes and hyphens
        "\u2014": " ",  # Em dash to space
        "\u2013": " ",  # En dash to space
        # Brackets and parentheses (keep content, remove brackets)
        "[": " ",
        "]": " ",
        "{": " ",
        "}": " ",
        # Other punctuation that can cause issues
        "`": "",  # Backtick
        "~": "",  # Tilde
        "^": "",  # Caret
        "*": "",  # Asterisk
        "_": " ",  # Underscore to space
        "|": " ",  # Pipe to space
        "\\": " ",  # Backslash to space
        "/": " ",  # Forward slash to space (except in URLs, handled separately)
        # Mathematical symbols
        "\u00b1": " plus or minus ",  # ±
        "\u00d7": " times ",  # ×
        "\u00f7": " divided by ",  # ÷
        "=": " equals ",
        "+": " plus ",
        "<": " less than ",
        ">": " greater than ",
        # Currency symbols (keep common ones)
        "$": " dollars ",
        "\u20ac": " euros ",  # €
        "\u00a3": " pounds ",  # £
        "\u00a5": " yen ",  # ¥
        # Other symbols
        "@": " at ",
        "#": " number ",
        "%": " percent ",
        "&": " and ",
        # Special characters that often cause issues
        "\u00a7": " section ",  # §
        "\u00a9": " copyright ",  # ©
        "\u00ae": " registered ",  # ®
        "\u2122": " trademark ",  # ™
    }

    cleaned_text = text

    # Handle URLs specially - replace with "link"
    url_pattern = r"https?://[^\s]+"
    cleaned_text = re.sub(url_pattern, " link ", cleaned_text)

    # Handle email addresses
    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    cleaned_text = re.sub(email_pattern, " email address ", cleaned_text)

    # Apply character replacements AFTER URL/email handling
    for char, replacement in replacements.items():
        cleaned_text = cleaned_text.replace(char, replacement)

    # Handle numbers with special formatting
    # Convert things like "1,000,000" to "1000000" to avoid comma pronunciation issues
    # Use a loop to handle any number of commas in numbers
    while re.search(r"(\d+),(\d+)", cleaned_text):
        cleaned_text = re.sub(r"(\d+),(\d+)", r"\1\2", cleaned_text)

    # Clean up multiple spaces and normalize whitespace
    cleaned_text = re.sub(r"\s+", " ", cleaned_text)
    cleaned_text = cleaned_text.strip()

    return cleaned_text


def synthesize_audio(tts_client, voice_id, text, filepath):
    """
    Synthesize speech via Google Cloud TTS and write the result to a file.

    Gets the voice configuration via get_voice_with_fallback, builds the TTS
    request objects, calls synthesize_speech, writes the audio bytes to
    filepath, and returns the raw audio content.

    Args:
        tts_client: An initialized google.cloud.texttospeech.TextToSpeechClient.
        voice_id: The voice identifier string (e.g. "en-US-Wavenet-D").
        text: The text to synthesize.
        filepath: Absolute path where the MP3 audio file should be written.

    Returns:
        bytes: The raw MP3 audio content returned by the TTS API.

    Raises:
        ValueError: If no valid voice configuration is found for voice_id.
        google.api_core.exceptions.GoogleAPIError: On TTS API failures.
        OSError: If writing to filepath fails.
    """
    voice_config = get_voice_with_fallback(voice_id)
    if not voice_config:
        raise ValueError(f"No valid voice configuration found for voice_id: {voice_id!r}")

    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code=voice_config["language_code"],
        name=voice_config["name"],
    )
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

    response = tts_client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )

    with open(filepath, "wb") as f:
        f.write(response.audio_content)

    return response.audio_content
