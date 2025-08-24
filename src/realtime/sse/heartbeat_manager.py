"""
Heartbeat Manager for SSE Connections

This module provides a heartbeat system for SSE connections that sends periodic
ping messages to maintain connection health and detect disconnected clients.

Features:
- Configurable heartbeat interval (default 30 seconds)
- Thread-safe heartbeat scheduling and delivery
- Connection failure tracking and notification
- Integration with connection pool for status updates
- Graceful shutdown with proper resource cleanup
"""

import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class HeartbeatManager:
    """
    Manages heartbeat messages for SSE connections.

    Sends periodic heartbeat messages to all active connections and tracks
    failures to notify the connection pool of disconnected clients.
    """

    def __init__(
        self,
        connection_pool,
        send_event_callback: Callable[[str, str, Dict[str, Any]], bool],
        heartbeat_interval: int = 30,
        failure_threshold: int = 3,
        timeout_seconds: float = 5.0,
    ):
        """
        Initialize heartbeat manager.

        Args:
            connection_pool: Connection pool instance for status updates
            send_event_callback: Callback to send events (connection_id, event_type, data) -> success
            heartbeat_interval: Seconds between heartbeats (default: 30)
            failure_threshold: Consecutive failures before marking connection dead
            timeout_seconds: Timeout for heartbeat delivery
        """
        self.connection_pool = connection_pool
        self.send_event_callback = send_event_callback
        self.heartbeat_interval = heartbeat_interval
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds

        # Thread management
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._running = False

        # Failure tracking
        self._failure_counts: Dict[str, int] = {}
        self._lock = threading.RLock()

        logger.info(
            f"HeartbeatManager initialized: interval={heartbeat_interval}s, " f"failure_threshold={failure_threshold}"
        )

    def start(self):
        """Start the heartbeat manager."""
        with self._lock:
            if self._running:
                logger.warning("HeartbeatManager already running")
                return

            self._running = True
            self._shutdown_event.clear()

            # Start heartbeat thread
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_worker, daemon=True, name="HeartbeatManager"
            )
            self._heartbeat_thread.start()

            logger.info("HeartbeatManager started")

    def stop(self):
        """Stop the heartbeat manager."""
        with self._lock:
            if not self._running:
                return

            logger.info("Stopping HeartbeatManager")

            # Signal shutdown
            self._running = False
            self._shutdown_event.set()

            # Wait for thread to finish
            if self._heartbeat_thread and self._heartbeat_thread.is_alive():
                self._heartbeat_thread.join(timeout=self.timeout_seconds)

            # Clear failure tracking
            self._failure_counts.clear()

            logger.info("HeartbeatManager stopped")

    def _heartbeat_worker(self):
        """Background worker that sends heartbeat messages."""
        logger.debug("Heartbeat worker started")

        while self._running and not self._shutdown_event.is_set():
            try:
                # Wait for heartbeat interval or shutdown
                if self._shutdown_event.wait(self.heartbeat_interval):
                    break  # Shutdown requested

                # Send heartbeats to all connections
                self._send_heartbeats()

            except Exception as e:
                logger.error(f"Error in heartbeat worker: {e}")
                # Continue running unless shutdown requested
                if not self._running:
                    break

        logger.debug("Heartbeat worker stopped")

    def _send_heartbeats(self):
        """Send heartbeat messages to all active connections."""
        if not self.connection_pool:
            return

        # Get all active connections
        stats = self.connection_pool.get_pool_stats()
        total_connections = stats.get("total_connections", 0)

        if total_connections == 0:
            return

        logger.debug(f"Sending heartbeats to {total_connections} connections")

        # Get connection list (thread-safe)
        with self.connection_pool._lock:
            connection_ids = list(self.connection_pool._connections.keys())

        sent_count = 0
        failed_count = 0

        # Send heartbeat to each connection
        for connection_id in connection_ids:
            try:
                success = self._send_heartbeat_to_connection(connection_id)
                if success:
                    sent_count += 1
                    # Reset failure count on success
                    self._failure_counts.pop(connection_id, None)
                else:
                    failed_count += 1
                    self._handle_heartbeat_failure(connection_id)

            except Exception as e:
                logger.error(f"Error sending heartbeat to {connection_id}: {e}")
                failed_count += 1
                self._handle_heartbeat_failure(connection_id)

        if sent_count > 0 or failed_count > 0:
            logger.debug(f"Heartbeat results: {sent_count} sent, {failed_count} failed")

    def _send_heartbeat_to_connection(self, connection_id: str) -> bool:
        """
        Send heartbeat message to a specific connection.

        Args:
            connection_id: Target connection ID

        Returns:
            bool: True if heartbeat sent successfully
        """
        heartbeat_data = {"type": "heartbeat", "timestamp": datetime.now().isoformat(), "connection_id": connection_id}

        try:
            # Use callback to send heartbeat event
            return self.send_event_callback(connection_id, "heartbeat", heartbeat_data)
        except Exception as e:
            logger.debug(f"Heartbeat failed for {connection_id}: {e}")
            return False

    def _handle_heartbeat_failure(self, connection_id: str):
        """
        Handle heartbeat failure for a connection.

        Args:
            connection_id: Connection that failed heartbeat
        """
        with self._lock:
            # Increment failure count
            current_failures = self._failure_counts.get(connection_id, 0) + 1
            self._failure_counts[connection_id] = current_failures

            logger.debug(f"Heartbeat failure #{current_failures} for {connection_id}")

            # Check if threshold reached
            if current_failures >= self.failure_threshold:
                logger.info(f"Connection {connection_id} failed {current_failures} heartbeats, " f"removing from pool")

                # Remove from connection pool
                self.connection_pool.remove_connection(connection_id)

                # Clear failure tracking
                self._failure_counts.pop(connection_id, None)

    def get_heartbeat_stats(self) -> Dict[str, Any]:
        """
        Get heartbeat manager statistics.

        Returns:
            Dictionary with heartbeat statistics
        """
        with self._lock:
            return {
                "running": self._running,
                "heartbeat_interval": self.heartbeat_interval,
                "failure_threshold": self.failure_threshold,
                "timeout_seconds": self.timeout_seconds,
                "connections_with_failures": len(self._failure_counts),
                "failure_counts": dict(self._failure_counts),
            }
