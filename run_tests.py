#!/usr/bin/env python3
"""
Test runner script for YouTube Summarizer
"""
import os
import subprocess
import sys


def run_tests():
    """Run all tests with coverage"""
    print("Running YouTube Summarizer Tests...")
    print("=" * 50)

    # Set environment variables for testing
    os.environ["GOOGLE_API_KEY"] = "test_api_key"
    os.environ["TESTING"] = "1"

    # Run pytest with coverage
    cmd = [sys.executable, "-m", "pytest", "--cov=app", "--cov-report=term-missing", "--cov-report=html", "-v"]

    result = subprocess.run(cmd)

    print("\n" + "=" * 50)
    if result.returncode == 0:
        print("✅ All tests passed!")
        print("📊 Coverage report generated in htmlcov/index.html")
    else:
        print("❌ Some tests failed!")

    return result.returncode


if __name__ == "__main__":
    sys.exit(run_tests())
