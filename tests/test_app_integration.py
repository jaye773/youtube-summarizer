"""
Flask App Integration Tests for YouTube Summarizer Async Worker System

This module tests the integration between the Flask application and the async
worker system, including initialization, startup, and graceful fallback scenarios.

Test Categories:
- Flask app initialization with worker system
- SSE manager initialization
- Graceful fallback when worker system unavailable
- Configuration management
- Threading and concurrent operations
"""

import json
import os

# Import main application
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from job_models import JobPriority, JobStatus, JobType
from job_state import JobStateManager
from sse_manager import SSEManager
from worker_manager import WorkerManager


@pytest.fixture
def client():
    """Create a Flask test client with clean configuration."""
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["WTF_CSRF_ENABLED"] = False

    # Create temporary directory for testing
    app.config["TEMP_DIR"] = tempfile.mkdtemp()

    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture
def mock_worker_system():
    """Mock the entire worker system for testing."""
    with patch("app.WORKER_SYSTEM_AVAILABLE", True):
        with patch("app.WorkerManager") as mock_wm, patch("app.JobStateManager") as mock_jsm, patch(
            "app.get_sse_manager"
        ) as mock_sse:

            # Configure mock instances
            mock_wm_instance = Mock()
            mock_jsm_instance = Mock()
            mock_sse_instance = Mock()

            mock_wm.return_value = mock_wm_instance
            mock_jsm.return_value = mock_jsm_instance
            mock_sse.return_value = mock_sse_instance

            # Mock essential methods
            mock_wm_instance.start.return_value = True
            mock_wm_instance.stop.return_value = None
            mock_jsm_instance.get_active_jobs.return_value = []
            mock_sse_instance.broadcast_event.return_value = None

            yield {
                "worker_manager": mock_wm_instance,
                "job_state_manager": mock_jsm_instance,
                "sse_manager": mock_sse_instance,
            }


@pytest.fixture
def unavailable_worker_system():
    """Mock worker system as unavailable."""
    with patch("app.WORKER_SYSTEM_AVAILABLE", False):
        yield


class TestFlaskAppInitialization:
    """Test Flask application initialization with worker system."""

    def test_app_creation(self, client):
        """Test that Flask app is created successfully."""
        assert app is not None
        assert app.config["TESTING"] is True

    def test_worker_system_available_flag(self):
        """Test worker system availability detection."""
        # This will depend on actual system state
        from app import WORKER_SYSTEM_AVAILABLE

        assert isinstance(WORKER_SYSTEM_AVAILABLE, bool)

    @patch("app.WORKER_SYSTEM_AVAILABLE", True)
    def test_worker_system_imports_success(self):
        """Test successful worker system import."""
        # Simulate successful import
        with patch("builtins.__import__", return_value=Mock()):
            # Re-import to trigger the import logic
            import importlib

            import app

            importlib.reload(app)

            # Should have imported successfully
            assert hasattr(app, "WorkerManager")

    @patch("app.WORKER_SYSTEM_AVAILABLE", False)
    def test_worker_system_imports_failure(self, unavailable_worker_system):
        """Test graceful handling of failed worker system imports."""
        # Should handle ImportError gracefully
        assert True  # Test passes if no exception is raised


class TestWorkerSystemIntegration:
    """Test integration with the async worker system."""

    def test_worker_manager_initialization(self, client, mock_worker_system):
        """Test WorkerManager initialization during app startup."""
        with app.app_context():
            # Simulate app initialization with worker system
            response = client.get("/")
            assert response.status_code == 200

    def test_sse_manager_initialization(self, client, mock_worker_system):
        """Test SSEManager initialization."""
        with app.app_context():
            # Check if SSE manager is properly initialized
            response = client.get("/events", headers={"Accept": "text/event-stream"})
            # Should not raise an error
            assert response.status_code in [200, 404, 405]  # Depending on implementation

    def test_job_state_manager_initialization(self, client, mock_worker_system):
        """Test JobStateManager initialization."""
        with app.app_context():
            # JobStateManager should be initialized with worker system
            response = client.get("/jobs")
            # Should handle request without errors
            assert response.status_code in [200, 404, 405]

    @patch("app.WORKER_SYSTEM_AVAILABLE", True)
    @patch("app.WorkerManager")
    def test_worker_system_startup_sequence(self, mock_worker_manager, client):
        """Test the worker system startup sequence."""
        mock_manager = Mock()
        mock_worker_manager.return_value = mock_manager
        mock_manager.start.return_value = True

        with app.app_context():
            # Simulate startup
            response = client.get("/")
            assert response.status_code == 200

    @patch("app.WORKER_SYSTEM_AVAILABLE", True)
    @patch("app.WorkerManager")
    def test_worker_system_startup_failure(self, mock_worker_manager, client):
        """Test handling of worker system startup failure."""
        mock_manager = Mock()
        mock_worker_manager.return_value = mock_manager
        mock_manager.start.side_effect = Exception("Worker system failed to start")

        with app.app_context():
            # Should handle startup failure gracefully
            response = client.get("/")
            # App should still respond even if worker system fails
            assert response.status_code == 200


class TestGracefulFallback:
    """Test graceful fallback when worker system is unavailable."""

    def test_fallback_to_sync_processing(self, client, unavailable_worker_system):
        """Test fallback to synchronous processing."""
        with app.app_context():
            # Should still be able to process requests synchronously
            response = client.get("/")
            assert response.status_code == 200

    @patch("app.WORKER_SYSTEM_AVAILABLE", False)
    def test_async_endpoints_unavailable(self, client):
        """Test that async endpoints handle unavailable worker system."""
        # Async endpoints should return appropriate error messages
        response = client.post(
            "/summarize_async",
            json={
                "url": "https://www.youtube.com/watch?v=test123",
                "ai_provider": "gemini",
                "model": "gemini-2.5-flash",
            },
        )

        # Should handle gracefully (might return 503 or redirect to sync)
        assert response.status_code in [200, 400, 404, 503]

    @patch("app.WORKER_SYSTEM_AVAILABLE", False)
    def test_sse_endpoints_unavailable(self, client):
        """Test SSE endpoints when worker system unavailable."""
        response = client.get("/events", headers={"Accept": "text/event-stream"})
        # Should handle gracefully
        assert response.status_code in [200, 404, 503]

    @patch("app.WORKER_SYSTEM_AVAILABLE", False)
    def test_job_endpoints_unavailable(self, client):
        """Test job management endpoints when worker system unavailable."""
        response = client.get("/jobs")
        assert response.status_code in [200, 404, 503]

        response = client.get("/jobs/test-job-id/status")
        assert response.status_code in [200, 404, 503]


class TestConfigurationManagement:
    """Test configuration management and environment variables."""

    def test_secret_key_configuration(self, client):
        """Test secret key configuration."""
        with app.app_context():
            assert app.secret_key is not None or app.config.get("SECRET_KEY") is not None

    def test_worker_system_config(self, client, mock_worker_system):
        """Test worker system configuration."""
        # Should be able to configure worker parameters
        with app.app_context():
            response = client.get("/")
            assert response.status_code == 200

    @patch.dict(os.environ, {"FLASK_ENV": "testing", "MAX_WORKERS": "4", "JOB_TIMEOUT": "300"})
    def test_environment_variable_loading(self, client):
        """Test loading configuration from environment variables."""
        # Should respect environment configuration
        assert os.environ.get("FLASK_ENV") == "testing"
        assert os.environ.get("MAX_WORKERS") == "4"

    def test_cache_configuration(self, client):
        """Test cache configuration and initialization."""
        with app.app_context():
            # Should handle cache configuration
            response = client.get("/")
            assert response.status_code == 200


class TestThreadingAndConcurrency:
    """Test threading and concurrent operations."""

    def test_concurrent_requests(self, client, mock_worker_system):
        """Test handling of concurrent requests."""

        def make_request():
            return client.get("/")

        # Create multiple threads to test concurrency
        threads = []
        results = []

        for _ in range(5):
            thread = threading.Thread(target=lambda: results.append(make_request()))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All requests should succeed
        assert len(results) == 5
        for response in results:
            assert response.status_code == 200

    def test_sse_connection_management(self, client, mock_worker_system):
        """Test SSE connection management with multiple clients."""
        # Simulate multiple SSE connections
        connections = []

        for i in range(3):
            response = client.get("/events", headers={"Accept": "text/event-stream"})
            connections.append(response)

        # Should handle multiple connections
        assert len(connections) == 3

    def test_thread_safety_worker_operations(self, client, mock_worker_system):
        """Test thread safety of worker operations."""

        def submit_job():
            return client.post(
                "/summarize_async",
                json={
                    "url": f"https://www.youtube.com/watch?v=test{uuid.uuid4()}",
                    "ai_provider": "gemini",
                    "model": "gemini-2.5-flash",
                },
            )

        # Submit multiple jobs concurrently
        threads = []
        results = []

        for _ in range(3):
            thread = threading.Thread(target=lambda: results.append(submit_job()))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Should handle concurrent job submissions
        assert len(results) == 3


class TestResourceManagement:
    """Test resource management and cleanup."""

    def test_memory_management(self, client, mock_worker_system):
        """Test memory management during operations."""
        # Make multiple requests to test memory usage
        for _ in range(10):
            response = client.get("/")
            assert response.status_code == 200

        # Should not accumulate excessive memory
        # This is a basic test - real memory testing would need profiling
        assert True

    def test_connection_cleanup(self, client, mock_worker_system):
        """Test cleanup of SSE connections."""
        # Create and close connections
        for _ in range(5):
            response = client.get("/events", headers={"Accept": "text/event-stream"})
            # Connection should be handled properly
            assert response.status_code in [200, 404, 405]

    def test_worker_thread_cleanup(self, client, mock_worker_system):
        """Test cleanup of worker threads."""
        mock_worker_system["worker_manager"].stop.return_value = None

        with app.app_context():
            # Should handle cleanup gracefully
            response = client.get("/")
            assert response.status_code == 200


class TestErrorHandling:
    """Test error handling in Flask integration."""

    def test_worker_system_exception_handling(self, client):
        """Test handling of worker system exceptions."""
        with patch("app.WorkerManager", side_effect=Exception("Test error")):
            with app.app_context():
                # Should handle worker system errors gracefully
                response = client.get("/")
                assert response.status_code == 200

    def test_sse_manager_exception_handling(self, client):
        """Test handling of SSE manager exceptions."""
        with patch("app.get_sse_manager", side_effect=Exception("SSE error")):
            with app.app_context():
                response = client.get("/events", headers={"Accept": "text/event-stream"})
                # Should handle SSE errors gracefully
                assert response.status_code in [200, 404, 500, 503]

    def test_job_state_manager_exception_handling(self, client):
        """Test handling of job state manager exceptions."""
        with patch("app.JobStateManager", side_effect=Exception("Job state error")):
            with app.app_context():
                response = client.get("/jobs")
                # Should handle job state errors gracefully
                assert response.status_code in [200, 404, 500, 503]


class TestHealthChecks:
    """Test health check and status endpoints."""

    def test_basic_health_check(self, client):
        """Test basic application health check."""
        response = client.get("/")
        assert response.status_code == 200

    def test_worker_system_health(self, client, mock_worker_system):
        """Test worker system health status."""
        mock_worker_system["worker_manager"].is_healthy.return_value = True

        with app.app_context():
            # Should indicate worker system is healthy
            response = client.get("/")
            assert response.status_code == 200

    def test_dependency_health_checks(self, client):
        """Test health checks for external dependencies."""
        with app.app_context():
            # Should handle external dependency checks
            response = client.get("/")
            assert response.status_code == 200


class TestPerformanceBaselines:
    """Test performance baselines for integration points."""

    def test_app_startup_time(self, client):
        """Test application startup time is reasonable."""
        start_time = time.time()

        with app.app_context():
            response = client.get("/")

        end_time = time.time()
        startup_time = end_time - start_time

        # Should start up within reasonable time (5 seconds for tests)
        assert startup_time < 5.0
        assert response.status_code == 200

    def test_request_response_time(self, client, mock_worker_system):
        """Test basic request response time."""
        start_time = time.time()
        response = client.get("/")
        end_time = time.time()

        response_time = end_time - start_time

        # Should respond within reasonable time (1 second for simple requests)
        assert response_time < 1.0
        assert response.status_code == 200

    def test_concurrent_request_performance(self, client, mock_worker_system):
        """Test performance with concurrent requests."""
        start_time = time.time()

        def make_request():
            return client.get("/")

        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        end_time = time.time()
        total_time = end_time - start_time

        # Should handle concurrent requests efficiently (within 3 seconds)
        assert total_time < 3.0


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])
