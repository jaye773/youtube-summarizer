#!/usr/bin/env python3
"""
Test script for voice configuration functionality
Run this to validate the voice model selection feature
"""

import json
import os
import sys

from voice_config import (
    AVAILABLE_VOICES,
    DEFAULT_VOICE,
    get_sample_text,
    get_voice_config,
    get_voice_with_fallback,
    get_voices_by_tier,
    validate_voice_name,
)


def test_voice_configuration():
    """Test voice configuration loading and structure"""
    print("Testing Voice Configuration...")

    # Test that voices are loaded
    assert len(AVAILABLE_VOICES) == 10, f"Expected 10 voices, got {len(AVAILABLE_VOICES)}"
    print(f"✅ Loaded {len(AVAILABLE_VOICES)} voices")

    # Test default voice
    assert DEFAULT_VOICE == "en-US-Chirp3-HD-Zephyr", f"Unexpected default voice: {DEFAULT_VOICE}"
    print(f"✅ Default voice: {DEFAULT_VOICE}")

    # Test voice structure
    for voice_id, voice_data in AVAILABLE_VOICES.items():
        required_fields = [
            "name",
            "display_name",
            "language_code",
            "gender",
            "accent",
            "style",
            "tier",
            "description",
            "quality",
        ]
        for field in required_fields:
            assert field in voice_data, f"Voice {voice_id} missing field: {field}"
    print("✅ All voices have required fields")

    return True


def test_voice_functions():
    """Test voice utility functions"""
    print("\nTesting Voice Functions...")

    # Test get_voice_config
    voice = get_voice_config("en-US-Chirp3-HD-Zephyr")
    assert voice is not None, "Failed to get valid voice config"
    assert voice["name"] == "en-US-Chirp3-HD-Zephyr"
    print("✅ get_voice_config works")

    # Test invalid voice
    invalid_voice = get_voice_config("invalid-voice-id")
    assert invalid_voice is None, "Should return None for invalid voice"
    print("✅ Invalid voice returns None")

    # Test fallback
    fallback = get_voice_with_fallback("invalid-voice")
    assert fallback is not None, "Fallback should return a valid voice"
    assert fallback["name"] == "en-US-Chirp3-HD-Zephyr", "Should fallback to default"
    print("✅ Fallback mechanism works")

    # Test get_voices_by_tier
    tiers = get_voices_by_tier()
    assert "chirp3-hd" in tiers, "Missing chirp3-hd tier"
    assert "neural2" in tiers, "Missing neural2 tier"
    assert len(tiers["chirp3-hd"]) == 3, "Expected 3 Chirp3-HD voices"
    print(f"✅ Voices organized by tier: {', '.join([f'{k}({len(v)})' for k,v in tiers.items()])}")

    # Test validate_voice_name
    assert validate_voice_name("en-US-Chirp3-HD-Zephyr") == True
    assert validate_voice_name("invalid-voice") == False
    print("✅ Voice validation works")

    # Test sample text
    sample = get_sample_text()
    assert len(sample) > 0, "Sample text should not be empty"
    print(f"✅ Sample text available ({len(sample)} chars)")

    return True


def test_voice_quality_tiers():
    """Test voice quality tier organization"""
    print("\nTesting Voice Quality Tiers...")

    premium_count = sum(1 for v in AVAILABLE_VOICES.values() if v["quality"] == "premium")
    high_count = sum(1 for v in AVAILABLE_VOICES.values() if v["quality"] == "high")
    standard_count = sum(1 for v in AVAILABLE_VOICES.values() if v["quality"] == "standard")

    print(f"✅ Premium voices: {premium_count}")
    print(f"✅ High quality voices: {high_count}")
    print(f"✅ Standard voices: {standard_count}")

    assert premium_count == 3, "Expected 3 premium voices"
    assert high_count == 4, "Expected 4 high quality voices"
    assert standard_count == 3, "Expected 3 standard voices"

    return True


def test_voice_characteristics():
    """Test voice characteristics distribution"""
    print("\nTesting Voice Characteristics...")

    # Count genders
    male_voices = sum(1 for v in AVAILABLE_VOICES.values() if v["gender"] == "male")
    female_voices = sum(1 for v in AVAILABLE_VOICES.values() if v["gender"] == "female")

    print(f"✅ Male voices: {male_voices}")
    print(f"✅ Female voices: {female_voices}")

    # Count accents
    accents = {}
    for voice in AVAILABLE_VOICES.values():
        accent = voice["accent"]
        accents[accent] = accents.get(accent, 0) + 1

    print(f"✅ Accents: {', '.join([f'{k}({v})' for k,v in accents.items()])}")

    # Count styles
    styles = {}
    for voice in AVAILABLE_VOICES.values():
        style = voice["style"]
        styles[style] = styles.get(style, 0) + 1

    print(f"✅ Styles: {', '.join([f'{k}({v})' for k,v in styles.items()])}")

    return True


def main():
    """Run all tests"""
    print("=" * 50)
    print("VOICE CONFIGURATION TEST SUITE")
    print("=" * 50)

    try:
        # Run all tests
        test_voice_configuration()
        test_voice_functions()
        test_voice_quality_tiers()
        test_voice_characteristics()

        print("\n" + "=" * 50)
        print("✅ ALL TESTS PASSED!")
        print("=" * 50)

        print("\nVoice Model Selection Feature Summary:")
        print(f"- Total voices available: {len(AVAILABLE_VOICES)}")
        print(f"- Default voice: {DEFAULT_VOICE}")
        print(f"- Quality tiers: Premium (3), High (4), Standard (3)")
        print("- Ready for production use!")

        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
