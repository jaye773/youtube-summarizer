#!/usr/bin/env python3
"""
Integration Test Runner for YouTube Summarizer Async Worker System

This script provides different test suite configurations for comprehensive testing
of the async worker system integration points.

Usage:
    python run_integration_tests.py [suite] [options]

Test Suites:
    all       - Run all integration tests (default)
    app       - Flask app integration tests only
    endpoints - Async API endpoint tests only
    e2e       - End-to-end workflow tests only
    fallback  - Fallback and error handling tests only
    quick     - Quick smoke test suite
    performance - Performance and load tests only
    concurrent  - Concurrent operation tests only

Options:
    --verbose     - Detailed output
    --coverage    - Run with coverage reporting
    --parallel    - Run tests in parallel (faster)
    --no-slow     - Skip slow tests
    --fail-fast   - Stop on first failure
    --html-report - Generate HTML test report
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle output."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 60)

    start_time = time.time()
    result = subprocess.run(cmd, capture_output=False)
    end_time = time.time()

    duration = end_time - start_time
    print(f"\nCompleted in {duration:.2f} seconds")

    if result.returncode != 0:
        print(f"❌ {description} failed with exit code {result.returncode}")
        return False
    else:
        print(f"✅ {description} passed")
        return True


def get_base_pytest_cmd():
    """Get base pytest command with common options."""
    return ["python", "-m", "pytest"]


def main():
    parser = argparse.ArgumentParser(description="Run integration tests for YouTube Summarizer async worker system")

    parser.add_argument(
        "suite",
        nargs="?",
        default="all",
        choices=["all", "app", "endpoints", "e2e", "fallback", "quick", "performance", "concurrent"],
        help="Test suite to run",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    parser.add_argument("--coverage", action="store_true", help="Run with coverage reporting")

    parser.add_argument("--parallel", "-n", type=int, default=1, help="Number of parallel test processes")

    parser.add_argument("--no-slow", action="store_true", help="Skip slow tests")

    parser.add_argument("--fail-fast", action="store_true", help="Stop on first failure")

    parser.add_argument("--html-report", action="store_true", help="Generate HTML test report")

    args = parser.parse_args()

    # Change to project directory
    project_root = Path(__file__).parent
    os.chdir(project_root)

    # Build pytest command
    cmd = get_base_pytest_cmd()

    # Add verbosity
    if args.verbose:
        cmd.extend(["-vvv"])

    # Add coverage
    if args.coverage:
        cmd.extend(
            [
                "--cov=app",
                "--cov=worker_manager",
                "--cov=job_state",
                "--cov=sse_manager",
                "--cov=job_models",
                "--cov-report=html",
                "--cov-report=term",
            ]
        )

    # Add parallel execution
    if args.parallel > 1:
        cmd.extend(["-n", str(args.parallel)])

    # Add fail fast
    if args.fail_fast:
        cmd.extend(["-x"])

    # Add HTML report
    if args.html_report:
        cmd.extend(["--html=reports/integration_test_report.html", "--self-contained-html"])
        # Create reports directory if it doesn't exist
        Path("reports").mkdir(exist_ok=True)

    # Add slow test filtering
    if args.no_slow:
        cmd.extend(["-m", "not slow"])

    # Test suite selection
    suite_configs = {
        "all": {
            "files": [
                "tests/test_app_integration.py",
                "tests/test_async_endpoints.py",
                "tests/test_end_to_end.py",
                "tests/test_fallback_scenarios.py",
            ],
            "description": "All integration tests",
        },
        "app": {"files": ["tests/test_app_integration.py"], "description": "Flask app integration tests"},
        "endpoints": {"files": ["tests/test_async_endpoints.py"], "description": "Async API endpoint tests"},
        "e2e": {"files": ["tests/test_end_to_end.py"], "description": "End-to-end workflow tests"},
        "fallback": {"files": ["tests/test_fallback_scenarios.py"], "description": "Fallback and error handling tests"},
        "quick": {
            "files": [
                "tests/test_app_integration.py::TestFlaskAppInitialization",
                "tests/test_async_endpoints.py::TestAsyncJobSubmission::test_submit_video_job_success",
                "tests/test_end_to_end.py::TestCompleteVideoWorkflow::test_video_processing_success_workflow",
                "tests/test_fallback_scenarios.py::TestWorkerSystemUnavailable::test_app_starts_without_worker_system",
            ],
            "description": "Quick smoke tests",
        },
        "performance": {"markers": ["performance"], "description": "Performance and load tests"},
        "concurrent": {"markers": ["concurrent"], "description": "Concurrent operation tests"},
    }

    config = suite_configs[args.suite]

    # Add test selection
    if "files" in config:
        cmd.extend(config["files"])
    elif "markers" in config:
        cmd.extend(["-m", " and ".join(config["markers"])])

    # Print test plan
    print("🧪 YouTube Summarizer Integration Test Runner")
    print("=" * 60)
    print(f"Suite: {args.suite} - {config['description']}")
    print(f"Coverage: {'Yes' if args.coverage else 'No'}")
    print(f"Parallel: {'Yes' if args.parallel > 1 else 'No'} ({args.parallel} processes)")
    print(f"HTML Report: {'Yes' if args.html_report else 'No'}")
    print(f"Skip Slow: {'Yes' if args.no_slow else 'No'}")

    # Run tests
    success = run_command(cmd, f"Integration Tests - {config['description']}")

    # Summary
    print(f"\n{'='*60}")
    if success:
        print("🎉 All tests passed!")
        if args.coverage:
            print("📊 Coverage report generated in htmlcov/")
        if args.html_report:
            print("📄 HTML test report generated in reports/")
    else:
        print("❌ Some tests failed!")
        sys.exit(1)

    print("=" * 60)

    return success


if __name__ == "__main__":
    main()
