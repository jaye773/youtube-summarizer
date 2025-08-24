"""
Comprehensive tests for the enhanced SSE implementation.

Tests all enhancements including:
- Connection pool limits and IP restrictions
- Heartbeat mechanism
- Message compression
- Health monitoring
- Integration between components
"""

import gzip
import json
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from sse_manager_enhanced import (
    CompressionLevel,
    ConnectionMetrics,
    ConnectionPool,
    ConnectionState,
    EnhancedSSEConnection,
    EnhancedSSEManager,
    HealthMonitor,
    MessageCompressor,
)


class TestConnectionPool:
    """Test connection pool functionality."""

    def setup_method(self):
        self.pool = ConnectionPool(max_total=10, max_per_ip=3)

    def test_connection_limits(self):
        """Test connection limits are enforced."""
        # Test per-IP limit
        can_add, reason = self.pool.can_add_connection("192.168.1.1")
        assert can_add

        # Add connections up to IP limit
        for i in range(3):
            conn = Mock()
            conn.client_id = f"client_{i}"
            assert self.pool.add_connection(conn, "192.168.1.1")

        # Should reject 4th connection from same IP
        can_add, reason = self.pool.can_add_connection("192.168.1.1")
        assert not can_add
        assert "Maximum connections per IP" in reason

    def test_total_connection_limit(self):
        """Test total connection limit."""
        # Fill pool to capacity with different IPs
        for i in range(10):
            conn = Mock()
            conn.client_id = f"client_{i}"
            ip = f"192.168.1.{i + 1}"
            assert self.pool.add_connection(conn, ip)

        # Should reject 11th connection
        conn = Mock()
        conn.client_id = "overflow_client"
        assert not self.pool.add_connection(conn, "192.168.1.100")

    def test_connection_removal(self):
        """Test connection removal and cleanup."""
        conn = Mock()
        conn.client_id = "test_client"
        ip = "192.168.1.1"

        # Add and remove connection
        assert self.pool.add_connection(conn, ip)
        assert len(self.pool.connections) == 1

        assert self.pool.remove_connection("test_client", ip)
        assert len(self.pool.connections) == 0
        assert ip not in self.pool.ip_connections

    def test_pool_statistics(self):
        """Test pool statistics generation."""
        # Add connections with 2 different IPs
        for i in range(5):
            conn = Mock()
            conn.client_id = f"client_{i}"
            ip = f"192.168.1.{(i % 2) + 1}"
            self.pool.add_connection(conn, ip)

        stats = self.pool.get_pool_stats()
        assert stats["total_connections"] == 5
        assert stats["max_total"] == 10
        assert stats["unique_ips"] == 2
        assert stats["utilization_percent"] == 50.0


class TestMessageCompressor:
    """Test message compression functionality."""

    def test_compression_threshold(self):
        """Test compression threshold logic."""
        small_message = "a" * 500  # 500 bytes
        large_message = "a" * 2000  # 2000 bytes

        assert not MessageCompressor.should_compress(small_message)
        assert MessageCompressor.should_compress(large_message)

    def test_message_compression(self):
        """Test actual message compression."""
        # Create compressible message
        original_data = json.dumps(
            {
                "repeated_field": ["same_value"] * 100,
                "large_text": "This is a test message that should compress well. " * 50,
            }
        )

        # Compress the message
        compressed_data, compression_ratio = MessageCompressor.compress(original_data, CompressionLevel.MEDIUM)

        assert isinstance(compressed_data, bytes)
        assert compression_ratio < 1.0  # Should achieve compression

        # Verify decompression works
        decompressed = gzip.decompress(compressed_data).decode("utf-8")
        assert decompressed == original_data

    def test_compressed_event_formatting(self):
        """Test compressed event SSE formatting."""
        test_data = "test_data_" * 200  # Create compressible data
        compressed_data, _ = MessageCompressor.compress(test_data)

        formatted_event = MessageCompressor.format_compressed_event(
            "test_event", compressed_data, len(test_data.encode("utf-8"))
        )

        # Check SSE format
        assert "event: test_event" in formatted_event
        assert "data: {" in formatted_event
        assert '"compressed": true' in formatted_event
        assert '"original_size":' in formatted_event
        assert '"data":' in formatted_event
        assert formatted_event.endswith("\n\n")


class TestEnhancedSSEConnection:
    """Test enhanced SSE connection functionality."""

    def setup_method(self):
        self.connection = EnhancedSSEConnection(
            client_id="test_client", client_ip="192.168.1.1", subscriptions={"test_event", "heartbeat"}
        )

    def teardown_method(self):
        if hasattr(self, "connection"):
            self.connection.close()

    def test_connection_initialization(self):
        """Test connection proper initialization."""
        assert self.connection.client_id == "test_client"
        assert self.connection.client_ip == "192.168.1.1"
        assert self.connection.state == ConnectionState.CONNECTING
        assert isinstance(self.connection.metrics, ConnectionMetrics)
        assert self.connection.compression_enabled

    def test_event_sending(self):
        """Test event sending with queue management."""
        self.connection.set_state(ConnectionState.CONNECTED)

        test_data = {"message": "test"}
        success = self.connection.send_event("test_event", test_data)
        assert success
        assert self.connection.metrics.messages_sent == 1

        # Verify event is queued
        events = self.connection.get_events(timeout=0.1)
        assert len(events) == 1
        assert "test_event" in events[0]

    def test_heartbeat_functionality(self):
        """Test heartbeat sending and tracking."""
        self.connection.set_state(ConnectionState.CONNECTED)

        # Send heartbeat
        success = self.connection.send_heartbeat()
        assert success
        assert self.connection.metrics.heartbeats_sent == 1

        # Verify heartbeat event format
        events = self.connection.get_events(timeout=0.1)
        assert len(events) == 1

        heartbeat_event = events[0]
        assert "event: heartbeat" in heartbeat_event
        assert '"type":"heartbeat"' in heartbeat_event
        assert '"connection_id":"test_client"' in heartbeat_event

    def test_health_monitoring(self):
        """Test connection health assessment."""
        self.connection.set_state(ConnectionState.CONNECTED)

        # New connection should be healthy
        assert self.connection.is_healthy

        # Simulate missed heartbeats
        old_time = datetime.now() - timedelta(minutes=2)
        self.connection.metrics.last_heartbeat = old_time

        # Should now be unhealthy due to missed heartbeat
        assert not self.connection.is_healthy


class TestHealthMonitor:
    """Test health monitoring functionality."""

    def setup_method(self):
        self.pool = ConnectionPool(max_total=10, max_per_ip=3)
        self.monitor = HealthMonitor(check_interval=1)

        # Add test connections
        for i in range(3):
            conn = Mock()
            conn.client_id = f"client_{i}"
            conn.client_ip = f"192.168.1.{i + 1}"
            conn.is_healthy = True
            conn.metrics = Mock()
            conn.metrics.messages_sent = 10
            conn.metrics.messages_failed = 1
            conn.metrics.age_seconds = 60
            conn.metrics.compression_ratio = 0.7
            conn.metrics.bytes_sent = 1000
            conn.metrics.bytes_compressed = 700

            self.pool.add_connection(conn, conn.client_ip)

    def test_metrics_collection(self):
        """Test metrics collection from connection pool."""
        metrics = self.monitor._collect_metrics(self.pool)

        assert metrics["total_connections"] == 3
        assert metrics["healthy_connections"] == 3
        assert metrics["health_score"] > 0.8
        assert metrics["error_rate"] <= 0.1

    def test_health_report_generation(self):
        """Test health report generation."""
        # Collect metrics multiple times to build history
        for _ in range(3):
            self.monitor._collect_metrics(self.pool)
            time.sleep(0.1)

        report = self.monitor.get_health_report()

        assert "status" in report
        # Accept either structure depending on data availability
        assert "current_metrics" in report or "message" in report

    def test_health_recommendations(self):
        """Test health recommendation generation."""
        # Create degraded conditions
        degraded_metrics = {
            "health_score": 0.4,
            "error_rate": 0.15,
            "total_connections": 450,
            "average_compression_ratio": 0.9,
        }

        recommendations = self.monitor._generate_recommendations(degraded_metrics)

        assert len(recommendations) > 0
        assert any("degraded" in rec.lower() for rec in recommendations)


class TestEnhancedSSEManager:
    """Test enhanced SSE manager functionality."""

    def setup_method(self):
        self.manager = EnhancedSSEManager(
            heartbeat_interval=1,  # 1 second for testing
            max_connections=10,
            max_connections_per_ip=3,
            health_check_interval=2,
        )

    def teardown_method(self):
        if hasattr(self, "manager"):
            self.manager.shutdown()

    def test_connection_management(self):
        """Test connection addition and removal."""
        # Add connection
        conn = self.manager.add_connection(client_ip="192.168.1.1", client_id="test_client")

        assert isinstance(conn, EnhancedSSEConnection)
        assert conn.client_id == "test_client"
        assert conn.state == ConnectionState.CONNECTED

        # Remove connection
        success = self.manager.remove_connection("test_client", "192.168.1.1")
        assert success
        assert self.manager.get_connection("test_client") is None

    def test_ip_based_limits(self):
        """Test IP-based connection limits."""
        ip = "192.168.1.1"

        # Add connections up to IP limit
        for i in range(3):
            self.manager.add_connection(client_ip=ip, client_id=f"client_{i}")

        # 4th connection from same IP should fail
        with pytest.raises(RuntimeError, match="Maximum connections per IP"):
            self.manager.add_connection(client_ip=ip, client_id="client_overflow")

    def test_broadcast_functionality(self):
        """Test event broadcasting."""
        # Add multiple connections with proper subscriptions
        for i in range(3):
            self.manager.add_connection(
                client_ip=f"192.168.1.{i + 1}", client_id=f"client_{i}", subscriptions={"test_broadcast", "heartbeat"}
            )

        # Broadcast event
        result = self.manager.broadcast_event("test_broadcast", {"message": "broadcast test"})

        assert result["sent"] == 3
        assert result["failed"] == 0

    def test_heartbeat_system(self):
        """Test heartbeat system functionality."""
        # Add a connection with heartbeat subscription
        conn = self.manager.add_connection(
            client_ip="192.168.1.1", client_id="test_client", subscriptions={"heartbeat"}
        )

        # Clear initial events
        conn.get_events(timeout=0.1)

        # Simulate older connection by manipulating heartbeat timestamp
        old_time = datetime.now() - timedelta(seconds=30)
        conn.metrics.last_heartbeat = old_time

        # Force heartbeat
        result = self.manager.force_heartbeat()
        assert result["sent"] == 1

        # Verify heartbeat was received
        events = conn.get_events(timeout=0.1)
        heartbeat_received = any("heartbeat" in event for event in events)
        assert heartbeat_received


class TestIntegrationScenarios:
    """Test integration scenarios and edge cases."""

    def setup_method(self):
        self.manager = EnhancedSSEManager(heartbeat_interval=1, max_connections=5, max_connections_per_ip=2)

        # Mock memory stats to avoid psutil dependency
        def mock_memory_stats():
            return {"memory_usage_mb": 100, "memory_percent": 5.0}

        self.manager._get_memory_stats = mock_memory_stats

    def teardown_method(self):
        if hasattr(self, "manager"):
            self.manager.shutdown()

    def test_rapid_connection_cycling(self):
        """Test rapid connection and disconnection cycles."""
        ip = "192.168.1.1"

        # Rapidly add and remove connections
        for cycle in range(3):
            client_id = f"cycling_client_{cycle}"

            # Add connection
            conn = self.manager.add_connection(client_ip=ip, client_id=client_id)
            assert conn is not None

            # Send some events
            for i in range(2):
                conn.send_event("test", {"cycle": cycle, "event": i})

            # Remove connection
            success = self.manager.remove_connection(client_id, ip)
            assert success

        # Pool should be empty
        stats = self.manager.get_comprehensive_stats()
        assert stats["connection_pool"]["total_connections"] == 0

    def test_large_message_compression(self):
        """Test large message handling with compression."""
        conn = self.manager.add_connection(
            client_ip="192.168.1.1", client_id="compression_test", subscriptions={"large_message"}
        )

        # Create large message
        large_data = {
            "large_array": ["repeated_value"] * 100,
            "large_text": "This is a large text block. " * 30,
        }

        # Send large message (should succeed if subscribed)
        success = conn.send_event("large_message", large_data)
        assert success

        # Retrieve events
        events = conn.get_events(timeout=0.1)
        assert len(events) > 0


# Test fixtures
@pytest.fixture
def mock_health_monitor():
    """Provide a mock health monitor for testing."""
    monitor = Mock()
    monitor.get_health_report.return_value = {
        "status": "healthy",
        "current_metrics": {"total_connections": 0, "health_score": 1.0, "error_rate": 0.0},
        "recommendations": [],
    }
    return monitor


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
