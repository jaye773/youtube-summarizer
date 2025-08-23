#!/usr/bin/env python3
"""
Run focused SSE Manager tests with coverage reporting.

This script runs a curated set of SSE tests to verify core functionality
without running the performance tests that may take a long time.
"""

import subprocess
import sys

def run_tests():
    """Run the focused test suite."""
    print("Running SSE Manager Tests...")
    print("=" * 50)

    # Test categories to run
    test_categories = [
        "tests/test_sse_manager.py::TestSSEConnection",
        "tests/test_sse_manager.py::TestSSEManager",
        "tests/test_sse_manager.py::TestEventFormatting",
        "tests/test_sse_manager.py::TestSSEManagerSingleton",
        "tests/test_sse_manager.py::TestFlaskIntegration",
    ]

    # Run each category
    for category in test_categories:
        print(f"\n🔍 Running {category.split('::')[-1]}...")
        result = subprocess.run([
            sys.executable, "-m", "pytest", category, "-v", "--tb=short"
        ], capture_output=False)

        if result.returncode != 0:
            print(f"❌ {category} failed!")
            return False
        else:
            print(f"✅ {category} passed!")

    print("\n" + "=" * 50)
    print("🎉 All core SSE tests passed!")

    # Run coverage report for core functionality
    print("\n📊 Getting coverage report...")
    subprocess.run([
        sys.executable, "-m", "pytest",
        "tests/test_sse_manager.py::TestSSEConnection",
        "tests/test_sse_manager.py::TestSSEManager::test_manager_initialization",
        "tests/test_sse_manager.py::TestSSEManager::test_add_connection_success",
        "tests/test_sse_manager.py::TestSSEManager::test_broadcast_event_all_connections",
        "tests/test_sse_manager.py::TestEventFormatting",
        "--cov=sse_manager", "--cov-report=term-missing"
    ], capture_output=False)

    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
