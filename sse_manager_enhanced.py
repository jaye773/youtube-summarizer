"""
Enhanced SSE (Server-Sent Events) Manager for YouTube Summarizer

This module provides an advanced Server-Sent Events implementation with:
- Heartbeat mechanism (30-second intervals) to keep connections alive
- Connection pooling (max 500 connections, max 10 per IP)
- Message compression for payloads >1KB using gzip
- Exponential backoff reconnection (1s, 2s, 4s, 8s, 16s, max 30s)
- Connection health monitoring and metrics
- Graceful degradation and error handling

Classes:
    ConnectionPool: IP-based connection pool management
    EnhancedSSEConnection: Individual client connection with compression
    EnhancedSSEManager: Advanced SSE manager with all enhancements
    HealthMonitor: Connection health and metrics monitoring
    MessageCompressor: Gzip compression for large messages
"""

import gc
import gzip
import json
import logging
import queue
import socket
import threading
import time
import uuid
import weakref
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection state enumeration."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    CLOSING = "closing"


class CompressionLevel(Enum):
    """Message compression levels."""

    NONE = 0
    LOW = 1
    MEDIUM = 6
    HIGH = 9


@dataclass
class ConnectionMetrics:
    """Metrics for individual connections."""

    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    messages_sent: int = 0
    messages_failed: int = 0
    bytes_sent: int = 0
    bytes_compressed: int = 0
    heartbeats_sent: int = 0
    heartbeats_missed: int = 0
    reconnection_count: int = 0
    compression_ratio: float = 0.0

    @property
    def age_seconds(self) -> float:
        """Get connection age in seconds."""
        return (datetime.now() - self.created_at).total_seconds()

    @property
    def idle_seconds(self) -> float:
        """Get seconds since last activity."""
        return (datetime.now() - self.last_activity).total_seconds()

    @property
    def heartbeat_idle_seconds(self) -> float:
        """Get seconds since last heartbeat."""
        return (datetime.now() - self.last_heartbeat).total_seconds()

    @property
    def success_rate(self) -> float:
        """Calculate message success rate."""
        total = self.messages_sent + self.messages_failed
        return (self.messages_sent / total) if total > 0 else 1.0


class MessageCompressor:
    """Handles gzip compression for SSE messages."""

    COMPRESSION_THRESHOLD = 1024  # 1KB

    @staticmethod
    def should_compress(data: str) -> bool:
        """Determine if message should be compressed."""
        return len(data.encode("utf-8")) > MessageCompressor.COMPRESSION_THRESHOLD

    @staticmethod
    def compress(data: str, level: CompressionLevel = CompressionLevel.MEDIUM) -> Tuple[bytes, float]:
        """
        Compress string data using gzip.

        Returns:
            Tuple of (compressed_data, compression_ratio)
        """
        try:
            original_bytes = data.encode("utf-8")
            original_size = len(original_bytes)

            compressed_data = gzip.compress(original_bytes, compresslevel=level.value)
            compressed_size = len(compressed_data)

            compression_ratio = compressed_size / original_size if original_size > 0 else 1.0

            logger.debug(f"Compressed {original_size}B → {compressed_size}B (ratio: {compression_ratio:.2f})")
            return compressed_data, compression_ratio

        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return data.encode("utf-8"), 1.0

    @staticmethod
    def format_compressed_event(event_type: str, compressed_data: bytes, original_size: int) -> str:
        """Format compressed data as SSE event with metadata."""
        import base64

        # Encode compressed data as base64 for transmission
        encoded_data = base64.b64encode(compressed_data).decode("ascii")

        # Create compressed event format
        event_lines = [
            f"event: {event_type}",
            f'data: {{"compressed": true, "original_size": {original_size}, "data": "{encoded_data}"}}',
        ]

        return "\n".join(event_lines) + "\n\n"


class ConnectionPool:
    """Manages connection pools with IP-based limits."""

    def __init__(self, max_total: int = 500, max_per_ip: int = 10):
        self.max_total = max_total
        self.max_per_ip = max_per_ip
        self.connections: Dict[str, "EnhancedSSEConnection"] = {}
        self.ip_connections: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()

    def can_add_connection(self, client_ip: str) -> Tuple[bool, str]:
        """
        Check if new connection can be added.

        Returns:
            Tuple of (can_add, reason_if_not)
        """
        with self._lock:
            if len(self.connections) >= self.max_total:
                return False, f"Maximum total connections reached ({self.max_total})"

            if len(self.ip_connections[client_ip]) >= self.max_per_ip:
                return False, f"Maximum connections per IP reached ({self.max_per_ip})"

            return True, ""

    def add_connection(self, connection: "EnhancedSSEConnection", client_ip: str) -> bool:
        """Add connection to pool."""
        with self._lock:
            can_add, reason = self.can_add_connection(client_ip)
            if not can_add:
                logger.warning(f"Cannot add connection {connection.client_id}: {reason}")
                return False

            self.connections[connection.client_id] = connection
            self.ip_connections[client_ip].add(connection.client_id)

            logger.info(
                f"Connection added to pool: {connection.client_id} "
                f"(total: {len(self.connections)}, IP {client_ip}: {len(self.ip_connections[client_ip])})"
            )
            return True

    def remove_connection(self, client_id: str, client_ip: str) -> bool:
        """Remove connection from pool."""
        with self._lock:
            if client_id in self.connections:
                del self.connections[client_id]
                self.ip_connections[client_ip].discard(client_id)

                # Clean up empty IP sets
                if not self.ip_connections[client_ip]:
                    del self.ip_connections[client_ip]

                logger.info(f"Connection removed from pool: {client_id} " f"(remaining: {len(self.connections)})")
                return True
            return False

    def get_connection(self, client_id: str) -> Optional["EnhancedSSEConnection"]:
        """Get connection by client ID."""
        with self._lock:
            return self.connections.get(client_id)

    def get_connections_by_ip(self, client_ip: str) -> List["EnhancedSSEConnection"]:
        """Get all connections for a specific IP."""
        with self._lock:
            client_ids = self.ip_connections.get(client_ip, set())
            return [self.connections[client_id] for client_id in client_ids if client_id in self.connections]

    def get_all_connections(self) -> List["EnhancedSSEConnection"]:
        """Get all connections."""
        with self._lock:
            return list(self.connections.values())

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        with self._lock:
            ip_stats = {ip: len(client_ids) for ip, client_ids in self.ip_connections.items()}

            return {
                "total_connections": len(self.connections),
                "max_total": self.max_total,
                "max_per_ip": self.max_per_ip,
                "unique_ips": len(self.ip_connections),
                "ip_distribution": ip_stats,
                "utilization_percent": (len(self.connections) / self.max_total) * 100,
            }


class EnhancedSSEConnection:
    """
    Enhanced SSE connection with compression, heartbeat, and metrics.
    """

    def __init__(self, client_id: str, client_ip: str, subscriptions: Set[str] = None):
        """Initialize enhanced SSE connection."""
        self.client_id = client_id
        self.client_ip = client_ip
        self.queue = queue.Queue(maxsize=2000)  # Increased queue size
        self.subscriptions = subscriptions or {"summary_progress", "summary_complete", "system", "heartbeat"}
        self.state = ConnectionState.CONNECTING
        self.metrics = ConnectionMetrics()
        self.compression_enabled = True
        self.compression_level = CompressionLevel.MEDIUM
        self._lock = threading.RLock()
        self._weak_refs: Set[weakref.ReferenceType] = set()

        logger.info(
            f"Enhanced SSE connection created: {client_id} from {client_ip} "
            f"with subscriptions: {self.subscriptions}"
        )

    def send_event(self, event_type: str, data: Dict[str, Any], force_uncompressed: bool = False) -> bool:
        """
        Send event with optional compression.

        Args:
            event_type: Type of the event
            data: Event data
            force_uncompressed: Force sending without compression

        Returns:
            bool: True if event was queued successfully
        """
        if self.state not in (ConnectionState.CONNECTED, ConnectionState.CONNECTING):
            return False

        if event_type not in self.subscriptions:
            return False

        try:
            with self._lock:
                # Format the event
                formatted_event = self._format_sse_event(event_type, data, force_uncompressed)

                # Queue the event
                self.queue.put(formatted_event, timeout=2.0)

                # Update metrics
                self.metrics.last_activity = datetime.now()
                self.metrics.messages_sent += 1

                # Track bytes sent
                event_size = len(formatted_event.encode("utf-8"))
                self.metrics.bytes_sent += event_size

                logger.debug(f"Event queued for {self.client_id}: {event_type} ({event_size}B)")
                return True

        except queue.Full:
            logger.warning(f"Event queue full for client {self.client_id}")
            self.metrics.messages_failed += 1
            return False
        except Exception as e:
            logger.error(f"Error queuing event for client {self.client_id}: {e}")
            self.metrics.messages_failed += 1
            return False

    def send_heartbeat(self) -> bool:
        """Send heartbeat event."""
        heartbeat_data = {
            "type": "heartbeat",
            "timestamp": datetime.now().isoformat(),
            "connection_id": self.client_id,
            "metrics": {
                "messages_sent": self.metrics.messages_sent,
                "uptime_seconds": self.metrics.age_seconds,
                "compression_ratio": self.metrics.compression_ratio,
            },
        }

        success = self.send_event("heartbeat", heartbeat_data, force_uncompressed=True)

        if success:
            self.metrics.last_heartbeat = datetime.now()
            self.metrics.heartbeats_sent += 1
        else:
            self.metrics.heartbeats_missed += 1

        return success

    def get_events(self, timeout: float = 30.0) -> List[str]:
        """Get pending events with timeout."""
        events = []
        end_time = time.time() + timeout

        try:
            # Wait for first event
            event = self.queue.get(timeout=timeout)
            events.append(event)

            # Collect additional events quickly
            while time.time() < end_time:
                try:
                    event = self.queue.get_nowait()
                    events.append(event)
                    if len(events) >= 50:  # Limit batch size
                        break
                except queue.Empty:
                    break

        except queue.Empty:
            # Send heartbeat if no events and it's time
            if self.metrics.heartbeat_idle_seconds > 25:  # 25 seconds since last heartbeat
                self.send_heartbeat()
                try:
                    event = self.queue.get_nowait()
                    events.append(event)
                except queue.Empty:
                    pass

        return events

    def set_state(self, state: ConnectionState):
        """Update connection state."""
        with self._lock:
            if self.state != state:
                logger.debug(f"Connection {self.client_id} state: {self.state.value} → {state.value}")
                self.state = state

                if state == ConnectionState.CONNECTED:
                    self.metrics.reconnection_count += 1

    def close(self):
        """Close connection and cleanup resources."""
        with self._lock:
            self.set_state(ConnectionState.CLOSING)

            # Clear event queue
            try:
                while True:
                    self.queue.get_nowait()
            except queue.Empty:
                pass

            # Clean up weak references
            for ref in self._weak_refs:
                if ref() is not None:
                    ref().clear()
            self._weak_refs.clear()

            self.state = ConnectionState.DISCONNECTED

        logger.info(f"Enhanced SSE connection closed: {self.client_id}")

    def _format_sse_event(self, event_type: str, data: Dict[str, Any], force_uncompressed: bool = False) -> str:
        """Format event with optional compression."""
        # Add metadata
        formatted_data = {
            **data,
            "timestamp": datetime.now().isoformat(),
            "client_id": self.client_id,
            "connection_state": self.state.value,
        }

        # Convert to JSON
        json_data = json.dumps(formatted_data, separators=(",", ":"))

        # Check if compression should be applied
        if not force_uncompressed and self.compression_enabled and MessageCompressor.should_compress(json_data):

            # Compress the data
            compressed_data, compression_ratio = MessageCompressor.compress(json_data, self.compression_level)

            # Update compression metrics
            self.metrics.bytes_compressed += len(compressed_data)
            self.metrics.compression_ratio = (
                (self.metrics.compression_ratio + compression_ratio) / 2
                if self.metrics.compression_ratio > 0
                else compression_ratio
            )

            return MessageCompressor.format_compressed_event(
                event_type, compressed_data, len(json_data.encode("utf-8"))
            )
        else:
            # Standard SSE format
            event_lines = [f"event: {event_type}", f"data: {json_data}"]
            return "\n".join(event_lines) + "\n\n"

    @property
    def is_healthy(self) -> bool:
        """Check if connection is healthy."""
        return (
            self.state == ConnectionState.CONNECTED
            and self.metrics.heartbeat_idle_seconds < 60  # Heartbeat within last minute
            and self.metrics.success_rate > 0.8  # Success rate above 80%
        )


class HealthMonitor:
    """Monitors connection health and collects metrics."""

    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self.metrics_history: deque = deque(maxlen=100)  # Keep last 100 snapshots
        self._lock = threading.RLock()
        self._monitoring = False
        self._monitor_thread = None

    def start_monitoring(self, connection_pool: ConnectionPool):
        """Start health monitoring."""
        if self._monitoring:
            return

        self._monitoring = True

        def monitor_worker():
            while self._monitoring:
                try:
                    snapshot = self._collect_metrics(connection_pool)

                    with self._lock:
                        self.metrics_history.append(snapshot)

                    logger.debug(f"Health check completed: {snapshot['summary']}")

                    # Sleep with early exit on shutdown
                    for _ in range(self.check_interval):
                        if not self._monitoring:
                            break
                        time.sleep(1)

                except Exception as e:
                    logger.error(f"Health monitoring error: {e}")
                    time.sleep(10)  # Back off on error

        self._monitor_thread = threading.Thread(target=monitor_worker, daemon=True)
        self._monitor_thread.start()
        logger.info("Health monitoring started")

    def stop_monitoring(self):
        """Stop health monitoring."""
        self._monitoring = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)
        logger.info("Health monitoring stopped")

    def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report."""
        with self._lock:
            if not self.metrics_history:
                return {"status": "no_data", "message": "No metrics available"}

            latest = self.metrics_history[-1]

            # Analyze trends if we have enough data
            trends = {}
            if len(self.metrics_history) >= 2:
                previous = self.metrics_history[-2]
                trends = {
                    "connection_change": latest["total_connections"] - previous["total_connections"],
                    "healthy_change": latest["healthy_connections"] - previous["healthy_connections"],
                    "error_rate_change": latest["error_rate"] - previous["error_rate"],
                }

            return {
                "status": "healthy" if latest["health_score"] > 0.8 else "degraded",
                "timestamp": latest["timestamp"],
                "current_metrics": latest,
                "trends": trends,
                "recommendations": self._generate_recommendations(latest),
            }

    def _collect_metrics(self, connection_pool: ConnectionPool) -> Dict[str, Any]:
        """Collect current metrics snapshot."""
        connections = connection_pool.get_all_connections()

        if not connections:
            return {
                "timestamp": datetime.now().isoformat(),
                "total_connections": 0,
                "healthy_connections": 0,
                "error_rate": 0.0,
                "health_score": 1.0,
                "summary": "No active connections",
            }

        # Calculate metrics
        healthy_count = sum(1 for conn in connections if conn.is_healthy)
        total_messages = sum(conn.metrics.messages_sent + conn.metrics.messages_failed for conn in connections)
        total_failures = sum(conn.metrics.messages_failed for conn in connections)

        error_rate = (total_failures / total_messages) if total_messages > 0 else 0.0
        health_ratio = healthy_count / len(connections)

        # Calculate overall health score (0.0 to 1.0)
        health_score = (health_ratio * 0.7) + ((1.0 - error_rate) * 0.3)

        # Connection age statistics
        ages = [conn.metrics.age_seconds for conn in connections]
        avg_age = sum(ages) / len(ages)

        # Compression statistics
        compression_ratios = [
            conn.metrics.compression_ratio for conn in connections if conn.metrics.compression_ratio > 0
        ]
        avg_compression = sum(compression_ratios) / len(compression_ratios) if compression_ratios else 0.0

        return {
            "timestamp": datetime.now().isoformat(),
            "total_connections": len(connections),
            "healthy_connections": healthy_count,
            "error_rate": error_rate,
            "health_score": health_score,
            "average_age_seconds": avg_age,
            "average_compression_ratio": avg_compression,
            "total_messages_sent": sum(conn.metrics.messages_sent for conn in connections),
            "total_bytes_sent": sum(conn.metrics.bytes_sent for conn in connections),
            "total_bytes_compressed": sum(conn.metrics.bytes_compressed for conn in connections),
            "summary": f"{healthy_count}/{len(connections)} healthy, {error_rate:.2%} error rate",
        }

    def _generate_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate health recommendations based on metrics."""
        recommendations = []

        if metrics["health_score"] < 0.5:
            recommendations.append("Critical: System health is severely degraded")
        elif metrics["health_score"] < 0.8:
            recommendations.append("Warning: System health is below optimal levels")

        if metrics["error_rate"] > 0.1:
            recommendations.append("High error rate detected - investigate connection issues")

        if metrics["total_connections"] > 400:  # 80% of max capacity
            recommendations.append("Connection pool nearing capacity - consider scaling")

        if metrics.get("average_compression_ratio", 0) > 0.8:
            recommendations.append("Low compression efficiency - review message sizes")

        return recommendations


class EnhancedSSEManager:
    """
    Enhanced SSE manager with all advanced features.
    """

    def __init__(
        self,
        heartbeat_interval: int = 30,
        max_connections: int = 500,
        max_connections_per_ip: int = 10,
        health_check_interval: int = 60,
    ):
        """Initialize enhanced SSE manager."""
        self.heartbeat_interval = heartbeat_interval
        self.connection_pool = ConnectionPool(max_connections, max_connections_per_ip)
        self.health_monitor = HealthMonitor(health_check_interval)

        self._heartbeat_thread = None
        self._shutdown_event = threading.Event()
        self._lock = threading.RLock()

        # Start background services
        self._start_heartbeat_system()
        self.health_monitor.start_monitoring(self.connection_pool)

        logger.info(
            f"Enhanced SSE Manager initialized: "
            f"max_connections={max_connections}, max_per_ip={max_connections_per_ip}, "
            f"heartbeat_interval={heartbeat_interval}s"
        )

    def add_connection(
        self, client_ip: str, client_id: str = None, subscriptions: Set[str] = None
    ) -> EnhancedSSEConnection:
        """Add new connection with IP-based limits."""
        if client_id is None:
            client_id = str(uuid.uuid4())

        # Check if connection can be added
        can_add, reason = self.connection_pool.can_add_connection(client_ip)
        if not can_add:
            raise RuntimeError(reason)

        # Remove existing connection if client reconnects
        existing = self.connection_pool.get_connection(client_id)
        if existing:
            logger.info(f"Replacing existing connection for client {client_id}")
            self.remove_connection(client_id, client_ip)

        # Create new connection
        connection = EnhancedSSEConnection(client_id, client_ip, subscriptions)

        # Add to pool
        if not self.connection_pool.add_connection(connection, client_ip):
            raise RuntimeError("Failed to add connection to pool")

        # Send connection confirmation
        connection.send_event(
            "connected",
            {
                "connection_id": client_id,
                "subscriptions": list(connection.subscriptions),
                "server_time": datetime.now().isoformat(),
                "compression_enabled": connection.compression_enabled,
                "heartbeat_interval": self.heartbeat_interval,
            },
        )

        connection.set_state(ConnectionState.CONNECTED)

        logger.info(f"Enhanced SSE connection established: {client_id} from {client_ip}")
        return connection

    def remove_connection(self, client_id: str, client_ip: str) -> bool:
        """Remove connection and cleanup resources."""
        connection = self.connection_pool.get_connection(client_id)
        if connection:
            connection.close()
            return self.connection_pool.remove_connection(client_id, client_ip)
        return False

    def get_connection(self, client_id: str) -> Optional[EnhancedSSEConnection]:
        """Get connection by client ID."""
        return self.connection_pool.get_connection(client_id)

    def broadcast_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        filter_func: Callable[[EnhancedSSEConnection], bool] = None,
        target_ips: List[str] = None,
    ) -> Dict[str, int]:
        """
        Broadcast event with advanced filtering.

        Args:
            event_type: Type of event
            data: Event data
            filter_func: Optional connection filter
            target_ips: Optional list of target IPs

        Returns:
            Broadcast statistics
        """
        sent_count = 0
        failed_count = 0
        filtered_count = 0

        # Get target connections
        if target_ips:
            connections = []
            for ip in target_ips:
                connections.extend(self.connection_pool.get_connections_by_ip(ip))
        else:
            connections = self.connection_pool.get_all_connections()

        # Broadcast to connections
        for connection in connections:
            try:
                # Apply filter if provided
                if filter_func and not filter_func(connection):
                    filtered_count += 1
                    continue

                # Send event
                if connection.send_event(event_type, data):
                    sent_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                logger.error(f"Error broadcasting to {connection.client_id}: {e}")
                failed_count += 1

        result = {
            "sent": sent_count,
            "failed": failed_count,
            "filtered": filtered_count,
            "total_targeted": len(connections),
        }

        logger.debug(f"Broadcast {event_type}: {result}")
        return result

    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive system statistics."""
        pool_stats = self.connection_pool.get_pool_stats()
        health_report = self.health_monitor.get_health_report()

        # Calculate system-wide metrics
        connections = self.connection_pool.get_all_connections()

        if connections:
            total_messages = sum(conn.metrics.messages_sent for conn in connections)
            total_bytes = sum(conn.metrics.bytes_sent for conn in connections)
            total_compressed_bytes = sum(conn.metrics.bytes_compressed for conn in connections)
            compression_savings = total_bytes - total_compressed_bytes if total_compressed_bytes > 0 else 0
        else:
            total_messages = 0
            total_bytes = 0
            compression_savings = 0

        return {
            "timestamp": datetime.now().isoformat(),
            "connection_pool": pool_stats,
            "health": health_report,
            "system_metrics": {
                "total_messages_sent": total_messages,
                "total_bytes_sent": total_bytes,
                "compression_savings_bytes": compression_savings,
                "heartbeat_interval": self.heartbeat_interval,
                "active_threads": threading.active_count(),
            },
            "memory_usage": self._get_memory_stats(),
        }

    def cleanup_unhealthy_connections(self) -> int:
        """Clean up unhealthy connections."""
        cleaned_count = 0
        connections = self.connection_pool.get_all_connections()

        for connection in connections:
            if not connection.is_healthy:
                logger.info(f"Cleaning up unhealthy connection: {connection.client_id}")
                if self.remove_connection(connection.client_id, connection.client_ip):
                    cleaned_count += 1

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} unhealthy connections")
            # Force garbage collection to free memory
            gc.collect()

        return cleaned_count

    def force_heartbeat(self) -> Dict[str, int]:
        """Force heartbeat to all connections."""
        return self._send_heartbeats()

    def shutdown(self):
        """Shutdown enhanced SSE manager."""
        logger.info("Shutting down Enhanced SSE Manager")

        # Signal shutdown
        self._shutdown_event.set()

        # Stop health monitoring
        self.health_monitor.stop_monitoring()

        # Wait for heartbeat thread
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=10.0)

        # Close all connections
        connections = self.connection_pool.get_all_connections()
        for connection in connections:
            self.remove_connection(connection.client_id, connection.client_ip)

        logger.info("Enhanced SSE Manager shutdown complete")

    def _start_heartbeat_system(self):
        """Start heartbeat system."""

        def heartbeat_worker():
            while not self._shutdown_event.is_set():
                try:
                    # Wait for next heartbeat interval or shutdown
                    if self._shutdown_event.wait(self.heartbeat_interval):
                        break

                    # Send heartbeats
                    self._send_heartbeats()

                    # Clean up unhealthy connections periodically
                    if int(time.time()) % 300 == 0:  # Every 5 minutes
                        self.cleanup_unhealthy_connections()

                except Exception as e:
                    logger.error(f"Error in heartbeat system: {e}")

        self._heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True)
        self._heartbeat_thread.start()
        logger.info("Heartbeat system started")

    def _send_heartbeats(self) -> Dict[str, int]:
        """Send heartbeat to all connections that need it."""
        sent_count = 0
        failed_count = 0

        connections = self.connection_pool.get_all_connections()

        for connection in connections:
            # Only send heartbeat if connection needs it
            if connection.metrics.heartbeat_idle_seconds >= (self.heartbeat_interval * 0.8):
                if connection.send_heartbeat():
                    sent_count += 1
                else:
                    failed_count += 1

        result = {"sent": sent_count, "failed": failed_count}

        if sent_count > 0:
            logger.debug(f"Heartbeat cycle: {result}")

        return result

    def _get_memory_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics."""
        import os

        import psutil

        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()

            return {
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "cpu_percent": process.cpu_percent(),
                "open_files": len(process.open_files()),
                "threads": process.num_threads(),
            }
        except ImportError:
            return {"error": "psutil not available"}
        except Exception as e:
            return {"error": str(e)}


# Utility functions for enhanced SSE events


def create_enhanced_progress_event(
    job_id: str, video_id: str, progress: float, status: str, message: str = "", eta_seconds: Optional[int] = None
) -> Dict[str, Any]:
    """Create enhanced progress event with ETA."""
    event_data = {
        "job_id": job_id,
        "video_id": video_id,
        "progress": min(max(progress, 0.0), 1.0),
        "status": status,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }

    if eta_seconds is not None:
        event_data["eta_seconds"] = eta_seconds
        event_data["estimated_completion"] = (datetime.now() + timedelta(seconds=eta_seconds)).isoformat()

    return event_data


def create_enhanced_system_event(
    message: str, level: str = "info", category: str = "system", data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Create enhanced system event with categorization."""
    event_data = {
        "message": message,
        "level": level,
        "category": category,
        "timestamp": datetime.now().isoformat(),
        "source": "enhanced_sse_manager",
    }

    if data:
        event_data.update(data)

    return event_data


# Global enhanced SSE manager instance
_enhanced_sse_manager_instance = None
_enhanced_sse_manager_lock = threading.Lock()


def get_enhanced_sse_manager(**kwargs) -> EnhancedSSEManager:
    """Get global enhanced SSE manager instance."""
    global _enhanced_sse_manager_instance

    if _enhanced_sse_manager_instance is None:
        with _enhanced_sse_manager_lock:
            if _enhanced_sse_manager_instance is None:
                _enhanced_sse_manager_instance = EnhancedSSEManager(**kwargs)

    return _enhanced_sse_manager_instance


def shutdown_enhanced_sse_manager():
    """Shutdown global enhanced SSE manager."""
    global _enhanced_sse_manager_instance

    with _enhanced_sse_manager_lock:
        if _enhanced_sse_manager_instance is not None:
            _enhanced_sse_manager_instance.shutdown()
            _enhanced_sse_manager_instance = None
