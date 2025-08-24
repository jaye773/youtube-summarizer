"""
Health Monitoring System for SSE Connections

This module provides comprehensive health monitoring for SSE connections including
connection metrics, system health tracking, and performance monitoring with
thread-safe operations and moving averages.
"""

import json
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


class HealthMetrics:
    """Thread-safe metrics collector with moving averages."""

    def __init__(self, window_size: int = 100):
        """Initialize metrics collector.

        Args:
            window_size: Number of samples for moving averages
        """
        self.window_size = window_size
        self._lock = threading.Lock()

        # Connection metrics
        self.connection_latencies = deque(maxlen=window_size)
        self.connection_successes = deque(maxlen=window_size)
        self.connection_errors = deque(maxlen=window_size)

        # Event metrics
        self.event_send_times = deque(maxlen=window_size)
        self.event_queue_sizes = deque(maxlen=window_size)

        # System metrics
        self.cpu_usage = deque(maxlen=window_size)
        self.memory_usage = deque(maxlen=window_size)

        # Error tracking
        self.error_counts = defaultdict(int)
        self.last_errors = deque(maxlen=50)

    def record_connection_latency(self, latency_ms: float):
        """Record connection latency."""
        with self._lock:
            self.connection_latencies.append(latency_ms)

    def record_connection_result(self, success: bool):
        """Record connection attempt result."""
        with self._lock:
            self.connection_successes.append(1 if success else 0)

    def record_connection_error(self, error_type: str, error_msg: str):
        """Record connection error."""
        with self._lock:
            self.connection_errors.append(1)
            self.error_counts[error_type] += 1
            self.last_errors.append({"type": error_type, "message": error_msg, "timestamp": datetime.now().isoformat()})

    def record_event_send_time(self, send_time_ms: float):
        """Record event send time."""
        with self._lock:
            self.event_send_times.append(send_time_ms)

    def record_queue_size(self, size: int):
        """Record event queue size."""
        with self._lock:
            self.event_queue_sizes.append(size)

    def record_system_metrics(self):
        """Record current system metrics."""
        try:
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()

            with self._lock:
                self.cpu_usage.append(cpu_percent)
                self.memory_usage.append(memory.percent)
        except Exception as e:
            logger.warning(f"Failed to collect system metrics: {e}")

    def get_moving_average(self, data: deque, default: float = 0.0) -> float:
        """Calculate moving average of data."""
        if not data:
            return default
        return sum(data) / len(data)

    def get_success_rate(self, window: int = None) -> float:
        """Calculate connection success rate."""
        with self._lock:
            successes = list(self.connection_successes)
            if not successes:
                return 100.0

            if window and len(successes) > window:
                successes = successes[-window:]

            return (sum(successes) / len(successes)) * 100.0


class HealthMonitor:
    """Main health monitoring system for SSE connections."""

    def __init__(self, sse_manager=None):
        """Initialize health monitor.

        Args:
            sse_manager: SSE manager instance to monitor
        """
        self.sse_manager = sse_manager
        self.metrics = HealthMetrics()
        self.start_time = datetime.now()
        self._monitoring = False
        self._monitor_thread = None
        self._lock = threading.Lock()

        # Health status thresholds
        self.thresholds = {
            "cpu_critical": 90.0,
            "cpu_warning": 70.0,
            "memory_critical": 90.0,
            "memory_warning": 80.0,
            "latency_critical": 5000.0,  # 5 seconds
            "latency_warning": 1000.0,  # 1 second
            "success_rate_critical": 50.0,
            "success_rate_warning": 80.0,
            "queue_size_critical": 800,
            "queue_size_warning": 500,
        }

    def start_monitoring(self, interval: int = 10):
        """Start background health monitoring.

        Args:
            interval: Monitoring interval in seconds
        """
        if self._monitoring:
            return

        with self._lock:
            self._monitoring = True
            self._monitor_thread = threading.Thread(target=self._monitor_loop, args=(interval,), daemon=True)
            self._monitor_thread.start()

        logger.info(f"Health monitoring started with {interval}s interval")

    def stop_monitoring(self):
        """Stop background monitoring."""
        with self._lock:
            self._monitoring = False

        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)

        logger.info("Health monitoring stopped")

    def _monitor_loop(self, interval: int):
        """Background monitoring loop."""
        while self._monitoring:
            try:
                self.metrics.record_system_metrics()
                self._check_sse_health()
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                time.sleep(interval)

    def _check_sse_health(self):
        """Check SSE manager health and record metrics."""
        if not self.sse_manager:
            return

        try:
            stats = self.sse_manager.get_connection_stats()

            # Record connection count as queue size metric
            self.metrics.record_queue_size(stats.get("total_connections", 0))

            # Check for stale connections (potential latency issues)
            avg_idle = stats.get("average_idle_seconds", 0)
            if avg_idle > 0:
                self.metrics.record_connection_latency(avg_idle * 1000)  # Convert to ms

        except Exception as e:
            self.metrics.record_connection_error("sse_health_check", str(e))

    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status."""
        with self._lock:
            # Calculate metrics
            avg_latency = self.metrics.get_moving_average(self.metrics.connection_latencies)
            avg_cpu = self.metrics.get_moving_average(self.metrics.cpu_usage)
            avg_memory = self.metrics.get_moving_average(self.metrics.memory_usage)
            avg_queue_size = self.metrics.get_moving_average(self.metrics.event_queue_sizes)
            success_rate = self.metrics.get_success_rate()

            # Determine overall health status
            status = self._calculate_health_status(avg_latency, avg_cpu, avg_memory, avg_queue_size, success_rate)

            # Get SSE stats if available
            sse_stats = {}
            if self.sse_manager:
                try:
                    sse_stats = self.sse_manager.get_connection_stats()
                except Exception as e:
                    logger.warning(f"Failed to get SSE stats: {e}")

            uptime = (datetime.now() - self.start_time).total_seconds()

            return {
                "status": status,
                "uptime_seconds": uptime,
                "connection_metrics": {
                    "avg_latency_ms": round(avg_latency, 2),
                    "success_rate_percent": round(success_rate, 2),
                    "total_errors": len(self.metrics.connection_errors),
                    "recent_errors": list(self.metrics.last_errors)[-5:],  # Last 5 errors
                },
                "system_metrics": {
                    "cpu_usage_percent": round(avg_cpu, 2),
                    "memory_usage_percent": round(avg_memory, 2),
                    "avg_queue_size": round(avg_queue_size, 1),
                },
                "sse_metrics": sse_stats,
                "error_summary": dict(self.metrics.error_counts),
                "thresholds": self.thresholds,
            }

    def _calculate_health_status(
        self, latency: float, cpu: float, memory: float, queue_size: float, success_rate: float
    ) -> str:
        """Calculate overall health status based on metrics."""
        # Check critical conditions
        if (
            cpu >= self.thresholds["cpu_critical"]
            or memory >= self.thresholds["memory_critical"]
            or latency >= self.thresholds["latency_critical"]
            or success_rate <= self.thresholds["success_rate_critical"]
            or queue_size >= self.thresholds["queue_size_critical"]
        ):
            return "critical"

        # Check warning conditions
        if (
            cpu >= self.thresholds["cpu_warning"]
            or memory >= self.thresholds["memory_warning"]
            or latency >= self.thresholds["latency_warning"]
            or success_rate <= self.thresholds["success_rate_warning"]
            or queue_size >= self.thresholds["queue_size_warning"]
        ):
            return "warning"

        return "healthy"

    def get_alerts(self) -> List[Dict[str, Any]]:
        """Get current health alerts."""
        alerts = []
        status_data = self.get_health_status()

        system = status_data["system_metrics"]
        connection = status_data["connection_metrics"]

        # CPU alerts
        if system["cpu_usage_percent"] >= self.thresholds["cpu_critical"]:
            alerts.append(
                {
                    "type": "critical",
                    "message": f"CPU usage critical: {system['cpu_usage_percent']:.1f}%",
                    "metric": "cpu",
                    "value": system["cpu_usage_percent"],
                }
            )
        elif system["cpu_usage_percent"] >= self.thresholds["cpu_warning"]:
            alerts.append(
                {
                    "type": "warning",
                    "message": f"CPU usage high: {system['cpu_usage_percent']:.1f}%",
                    "metric": "cpu",
                    "value": system["cpu_usage_percent"],
                }
            )

        # Memory alerts
        if system["memory_usage_percent"] >= self.thresholds["memory_critical"]:
            alerts.append(
                {
                    "type": "critical",
                    "message": f"Memory usage critical: {system['memory_usage_percent']:.1f}%",
                    "metric": "memory",
                    "value": system["memory_usage_percent"],
                }
            )
        elif system["memory_usage_percent"] >= self.thresholds["memory_warning"]:
            alerts.append(
                {
                    "type": "warning",
                    "message": f"Memory usage high: {system['memory_usage_percent']:.1f}%",
                    "metric": "memory",
                    "value": system["memory_usage_percent"],
                }
            )

        # Connection alerts
        if connection["success_rate_percent"] <= self.thresholds["success_rate_critical"]:
            alerts.append(
                {
                    "type": "critical",
                    "message": f"Connection success rate critical: {connection['success_rate_percent']:.1f}%",
                    "metric": "success_rate",
                    "value": connection["success_rate_percent"],
                }
            )

        return alerts
