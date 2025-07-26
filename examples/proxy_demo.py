#!/usr/bin/env python3
"""
YouTube Summarizer - Webshare Proxy Demonstration
================================================

This script demonstrates how to configure and use webshare proxy support
for fetching YouTube transcripts when running into IP restrictions or rate limiting.

Prerequisites:
- Active webshare.io account with proxy credentials
- Environment variables configured (see below)

Usage:
    python3 examples/proxy_demo.py
"""

import os
import sys

# Add the parent directory to the path so we can import the app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app


def demonstrate_proxy_configuration():
    """Demonstrate webshare proxy configuration"""
    print("=" * 60)
    print("YouTube Summarizer - Webshare Proxy Demo")
    print("=" * 60)
    print()

    # Check current proxy configuration
    print("Current proxy configuration:")
    print(f"  WEBSHARE_PROXY_ENABLED: {app.WEBSHARE_PROXY_ENABLED}")
    print(f"  WEBSHARE_PROXY_HOST: {app.WEBSHARE_PROXY_HOST or 'Not set'}")
    print(f"  WEBSHARE_PROXY_PORT: {app.WEBSHARE_PROXY_PORT or 'Not set'}")
    print(f"  WEBSHARE_PROXY_USERNAME: {app.WEBSHARE_PROXY_USERNAME or 'Not set'}")
    print(
        f"  WEBSHARE_PROXY_PASSWORD: {'*' * len(app.WEBSHARE_PROXY_PASSWORD) if app.WEBSHARE_PROXY_PASSWORD else 'Not set'}"
    )
    print()

    # Test proxy configuration
    proxy_config = app.get_proxy_config()
    if proxy_config:
        print("✅ Proxy configuration is valid!")
        print(f"   Using proxy: {app.WEBSHARE_PROXY_USERNAME}@{app.WEBSHARE_PROXY_HOST}:{app.WEBSHARE_PROXY_PORT}")
        print(f"   Proxy URLs: {proxy_config}")
    else:
        print("❌ Proxy configuration is disabled or invalid")
        if app.WEBSHARE_PROXY_ENABLED:
            print("   Make sure all required environment variables are set:")
            print("   - WEBSHARE_PROXY_HOST")
            print("   - WEBSHARE_PROXY_PORT")
            print("   - WEBSHARE_PROXY_USERNAME")
            print("   - WEBSHARE_PROXY_PASSWORD")
        else:
            print("   Set WEBSHARE_PROXY_ENABLED=true to enable proxy support")
    print()


def test_transcript_fetching():
    """Test transcript fetching with current configuration"""
    print("Testing transcript fetching...")
    print("-" * 40)

    # Test with a well-known video that should have transcripts
    test_video_id = "dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up

    print(f"Attempting to fetch transcript for video: {test_video_id}")

    try:
        transcript, error = app.get_transcript(test_video_id)

        if transcript:
            print("✅ Transcript fetched successfully!")
            print(f"   Length: {len(transcript)} characters")
            print(f"   Preview: {transcript[:100]}...")
        else:
            print("❌ Failed to fetch transcript")
            print(f"   Error: {error}")

    except Exception as e:
        print("❌ Exception occurred while fetching transcript")
        print(f"   Error: {e}")

    print()


def show_configuration_examples():
    """Show configuration examples"""
    print("Configuration Examples:")
    print("-" * 40)
    print()

    print("1. Environment Variables (.env file):")
    print("   WEBSHARE_PROXY_ENABLED=true")
    print("   WEBSHARE_PROXY_HOST=proxy.webshare.io")
    print("   WEBSHARE_PROXY_PORT=8080")
    print("   WEBSHARE_PROXY_USERNAME=your_username")
    print("   WEBSHARE_PROXY_PASSWORD=your_password")
    print()

    print("2. Command Line Export:")
    print("   export WEBSHARE_PROXY_ENABLED=true")
    print("   export WEBSHARE_PROXY_HOST=proxy.webshare.io")
    print("   export WEBSHARE_PROXY_PORT=8080")
    print("   export WEBSHARE_PROXY_USERNAME=your_username")
    print("   export WEBSHARE_PROXY_PASSWORD=your_password")
    print()

    print("3. Docker Compose (.env file):")
    print("   GOOGLE_API_KEY=your_google_api_key")
    print("   WEBSHARE_PROXY_ENABLED=true")
    print("   WEBSHARE_PROXY_HOST=proxy.webshare.io")
    print("   WEBSHARE_PROXY_PORT=8080")
    print("   WEBSHARE_PROXY_USERNAME=your_username")
    print("   WEBSHARE_PROXY_PASSWORD=your_password")
    print()


def main():
    """Main demonstration function"""
    demonstrate_proxy_configuration()
    test_transcript_fetching()
    show_configuration_examples()

    print("For more information, see the README.md file:")
    print("https://github.com/your-repo/youtube-summarizer#webshare-proxy-support")


if __name__ == "__main__":
    main()
