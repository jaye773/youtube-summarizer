"""
Connection Pool Manager for SSE Connections

This module provides a thread-safe connection pool implementation for managing
SSE connections with IP-based rate limiting, automatic cleanup, and connection
tracking with metadata.

Features:
- Maximum 500 total connections
- Maximum 10 connections per IP address
- Thread-safe implementation with proper locking
- Connection metadata tracking and monitoring
- Automatic cleanup of stale connections
- IP-based rate limiting and connection counting
"""

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ConnectionMetadata:
    """Metadata for tracking individual connections."""

    def __init__(self, connection_id: str, client_ip: str, user_agent: str = ""):
        self.connection_id = connection_id
        self.client_ip = client_ip
        self.user_agent = user_agent
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.subscriptions: Set[str] = set()
        self.events_sent = 0
        self.events_failed = 0
        self.is_active = True

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now()

    def get_age_seconds(self) -> float:
        """Get connection age in seconds."""
        return (datetime.now() - self.created_at).total_seconds()

    def get_idle_seconds(self) -> float:
        """Get seconds since last activity."""
        return (datetime.now() - self.last_activity).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "connection_id": self.connection_id,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "age_seconds": self.get_age_seconds(),
            "idle_seconds": self.get_idle_seconds(),
            "subscriptions": list(self.subscriptions),
            "events_sent": self.events_sent,
            "events_failed": self.events_failed,
            "is_active": self.is_active,
        }


class ConnectionPool:
    """
    Thread-safe connection pool manager for SSE connections.

    Manages connections with IP-based limits, automatic cleanup,
    and connection tracking with metadata.
    """

    def __init__(
        self,
        max_total_connections: int = 500,
        max_connections_per_ip: int = 10,
        stale_timeout_seconds: int = 300,
        cleanup_interval_seconds: int = 60,
    ):
        """
        Initialize connection pool.

        Args:
            max_total_connections: Maximum total connections allowed
            max_connections_per_ip: Maximum connections per IP address
            stale_timeout_seconds: Timeout for stale connection cleanup
            cleanup_interval_seconds: Interval for automatic cleanup
        """
        self.max_total_connections = max_total_connections
        self.max_connections_per_ip = max_connections_per_ip
        self.stale_timeout_seconds = stale_timeout_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds

        # Connection storage
        self._connections: Dict[str, ConnectionMetadata] = {}
        self._ip_connections: Dict[str, Set[str]] = defaultdict(set)

        # Thread safety
        self._lock = threading.RLock()

        # Cleanup management
        self._cleanup_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

        # Statistics
        self._total_connections_created = 0
        self._total_connections_rejected = 0

        # Start cleanup thread
        self._start_cleanup_thread()

        logger.info(
            f"ConnectionPool initialized: max_total={max_total_connections}, " f"max_per_ip={max_connections_per_ip}"
        )

    def add_connection(
        self, connection_id: str, client_ip: str, user_agent: str = "", subscriptions: Set[str] = None
    ) -> Tuple[bool, str]:
        """
        Add a new connection to the pool.

        Args:
            connection_id: Unique connection identifier
            client_ip: Client IP address
            user_agent: Optional user agent string
            subscriptions: Set of event subscriptions

        Returns:
            Tuple[bool, str]: (success, message)
        """
        with self._lock:
            # Check total connection limit
            if len(self._connections) >= self.max_total_connections:
                self._total_connections_rejected += 1
                return False, f"Maximum total connections limit reached ({self.max_total_connections})"

            # Check per-IP limit
            if len(self._ip_connections[client_ip]) >= self.max_connections_per_ip:
                self._total_connections_rejected += 1
                return False, f"Maximum connections per IP limit reached ({self.max_connections_per_ip})"

            # Remove existing connection if reconnecting
            if connection_id in self._connections:
                self.remove_connection(connection_id)

            # Create new connection metadata
            metadata = ConnectionMetadata(connection_id, client_ip, user_agent)
            if subscriptions:
                metadata.subscriptions = subscriptions

            # Add to storage
            self._connections[connection_id] = metadata
            self._ip_connections[client_ip].add(connection_id)
            self._total_connections_created += 1

            logger.info(f"Connection added: {connection_id} from {client_ip} " f"(total: {len(self._connections)})")

            return True, "Connection added successfully"

    def remove_connection(self, connection_id: str) -> bool:
        """
        Remove a connection from the pool.

        Args:
            connection_id: Connection identifier to remove

        Returns:
            bool: True if connection was removed, False if not found
        """
        with self._lock:
            if connection_id not in self._connections:
                return False

            metadata = self._connections[connection_id]
            client_ip = metadata.client_ip

            # Remove from main storage
            del self._connections[connection_id]

            # Remove from IP tracking
            if client_ip in self._ip_connections:
                self._ip_connections[client_ip].discard(connection_id)
                if not self._ip_connections[client_ip]:
                    del self._ip_connections[client_ip]

            logger.info(
                f"Connection removed: {connection_id} from {client_ip} " f"(remaining: {len(self._connections)})"
            )

            return True

    def get_connection(self, connection_id: str) -> Optional[ConnectionMetadata]:
        """
        Get connection metadata by ID.

        Args:
            connection_id: Connection identifier

        Returns:
            ConnectionMetadata or None if not found
        """
        with self._lock:
            return self._connections.get(connection_id)

    def update_connection_activity(self, connection_id: str) -> bool:
        """
        Update last activity timestamp for a connection.

        Args:
            connection_id: Connection identifier

        Returns:
            bool: True if connection was found and updated
        """
        with self._lock:
            if connection_id in self._connections:
                self._connections[connection_id].update_activity()
                return True
            return False

    def get_connections_by_ip(self, client_ip: str) -> List[ConnectionMetadata]:
        """
        Get all connections for a specific IP address.

        Args:
            client_ip: IP address to query

        Returns:
            List of ConnectionMetadata for the IP
        """
        with self._lock:
            connection_ids = self._ip_connections.get(client_ip, set())
            return [self._connections[conn_id] for conn_id in connection_ids if conn_id in self._connections]

    def cleanup_stale_connections(self) -> int:
        """
        Remove connections that have been idle too long.

        Returns:
            int: Number of connections cleaned up
        """
        stale_connections = []
        current_time = datetime.now()

        with self._lock:
            for conn_id, metadata in self._connections.items():
                idle_seconds = (current_time - metadata.last_activity).total_seconds()
                if idle_seconds > self.stale_timeout_seconds or not metadata.is_active:
                    stale_connections.append(conn_id)

            # Remove stale connections
            cleanup_count = 0
            for conn_id in stale_connections:
                if self.remove_connection(conn_id):
                    cleanup_count += 1

        if cleanup_count > 0:
            logger.info(f"Cleaned up {cleanup_count} stale connections")

        return cleanup_count

    def get_pool_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive pool statistics.

        Returns:
            Dictionary with pool statistics
        """
        with self._lock:
            total_connections = len(self._connections)
            ip_distribution = {ip: len(conn_ids) for ip, conn_ids in self._ip_connections.items()}

            if total_connections > 0:
                ages = [metadata.get_age_seconds() for metadata in self._connections.values()]
                idle_times = [metadata.get_idle_seconds() for metadata in self._connections.values()]
                avg_age = sum(ages) / len(ages)
                avg_idle = sum(idle_times) / len(idle_times)
                max_age = max(ages)
            else:
                avg_age = avg_idle = max_age = 0

            return {
                "total_connections": total_connections,
                "max_total_connections": self.max_total_connections,
                "max_connections_per_ip": self.max_connections_per_ip,
                "unique_ips": len(self._ip_connections),
                "ip_distribution": ip_distribution,
                "average_age_seconds": avg_age,
                "average_idle_seconds": avg_idle,
                "oldest_connection_seconds": max_age,
                "total_created": self._total_connections_created,
                "total_rejected": self._total_connections_rejected,
                "utilization_percent": (total_connections / self.max_total_connections) * 100,
            }

    def shutdown(self):
        """Shutdown the connection pool and cleanup resources."""
        logger.info("Shutting down ConnectionPool")

        # Signal shutdown
        self._shutdown_event.set()

        # Wait for cleanup thread
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5.0)

        # Clear all connections
        with self._lock:
            connection_count = len(self._connections)
            self._connections.clear()
            self._ip_connections.clear()

        logger.info(f"ConnectionPool shutdown complete. Removed {connection_count} connections")

    def _start_cleanup_thread(self):
        """Start background cleanup thread."""

        def cleanup_worker():
            while not self._shutdown_event.is_set():
                try:
                    # Wait for shutdown or cleanup interval
                    if self._shutdown_event.wait(self.cleanup_interval_seconds):
                        break  # Shutdown requested

                    # Run cleanup
                    self.cleanup_stale_connections()

                except Exception as e:
                    logger.error(f"Error in connection pool cleanup: {e}")

        self._cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True, name="ConnectionPool-Cleanup")
        self._cleanup_thread.start()
        logger.debug("ConnectionPool cleanup thread started")
