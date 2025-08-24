"""Enhanced SSE Manager with all performance and reliability improvements.

This module coordinates all SSE enhancement components while maintaining
compatibility with the existing sse_manager.py interface.
"""

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from flask import Response
from werkzeug.exceptions import BadRequest

from ..compression.message_compressor import MessageCompressor
from ..connections.connection_pool import ConnectionPool
from ..monitoring.health_monitor import HealthMonitor
from .heartbeat_manager import HeartbeatManager

logger = logging.getLogger(__name__)


class EnhancedSSEManager:
    """Enhanced SSE Manager coordinating all improvement modules."""

    def __init__(self, max_connections: int = 100):
        """Initialize enhanced SSE manager.

        Args:
            max_connections: Maximum concurrent connections
        """
        # Core components
        self.connection_pool = ConnectionPool(max_connections=max_connections)
        self.heartbeat_manager = HeartbeatManager()
        self.message_compressor = MessageCompressor()
        self.health_monitor = HealthMonitor()

        # Internal state
        self._lock = threading.RLock()
        self._running = False

        logger.info(f"Enhanced SSE Manager initialized with max_connections={max_connections}")

    def start(self):
        """Start all enhancement components."""
        with self._lock:
            if self._running:
                return

            try:
                self.heartbeat_manager.start()
                self.health_monitor.start()
                self._running = True
                logger.info("Enhanced SSE Manager started successfully")
            except Exception as e:
                logger.error(f"Failed to start Enhanced SSE Manager: {e}")
                self.stop()  # Cleanup partial initialization
                raise

    def stop(self):
        """Stop all enhancement components."""
        with self._lock:
            if not self._running:
                return

            try:
                self.heartbeat_manager.stop()
                self.health_monitor.stop()
                self.connection_pool.cleanup()
                self._running = False
                logger.info("Enhanced SSE Manager stopped successfully")
            except Exception as e:
                logger.error(f"Error stopping Enhanced SSE Manager: {e}")

    def is_running(self) -> bool:
        """Check if manager is running."""
        return self._running

    def get_sse_stream(self, client_id: str) -> Response:
        """Create SSE stream for client.

        Args:
            client_id: Unique client identifier

        Returns:
            Flask Response object for SSE stream

        Raises:
            BadRequest: If connection cannot be established
        """
        if not self._running:
            self.start()

        # Check connection limits
        if not self.connection_pool.can_accept_connection():
            logger.warning(f"Connection rejected for {client_id}: pool at capacity")
            raise BadRequest("Server at capacity. Please try again later.")

        # Create connection
        connection = self.connection_pool.create_connection(client_id)
        if not connection:
            logger.error(f"Failed to create connection for {client_id}")
            raise BadRequest("Failed to establish connection")

        # Register for heartbeats
        self.heartbeat_manager.register_connection(client_id)

        # Update health metrics
        self.health_monitor.record_connection(client_id)

        logger.info(f"SSE stream created for client {client_id}")

        def event_stream():
            """Generate SSE events for client."""
            try:
                # Send initial connection event
                yield self._format_sse_event("connected", {"client_id": client_id})

                # Stream events
                for event in connection.get_events():
                    if event is None:
                        break

                    # Compress large messages
                    compressed_event = self.message_compressor.compress_event(event)
                    yield self._format_sse_event(compressed_event["event"], compressed_event["data"])

            except Exception as e:
                logger.error(f"Error in event stream for {client_id}: {e}")
                yield self._format_sse_event("error", {"message": "Stream error occurred"})

            finally:
                # Cleanup on disconnect
                self._cleanup_client(client_id)

        return Response(
            event_stream(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    def send_event(self, event_type: str, data: Any, client_id: Optional[str] = None):
        """Send event to client(s).

        Args:
            event_type: Type of event
            data: Event data
            client_id: Specific client ID (None for broadcast)
        """
        if not self._running:
            logger.warning("Cannot send event: manager not running")
            return

        try:
            if client_id:
                # Send to specific client
                connection = self.connection_pool.get_connection(client_id)
                if connection:
                    connection.send_event(event_type, data)
                    self.health_monitor.record_message_sent(client_id)
                else:
                    logger.warning(f"No connection found for client {client_id}")
            else:
                # Broadcast to all clients
                active_connections = self.connection_pool.get_active_connections()
                for cid, connection in active_connections.items():
                    connection.send_event(event_type, data)
                    self.health_monitor.record_message_sent(cid)

                logger.debug(f"Broadcast {event_type} to {len(active_connections)} clients")

        except Exception as e:
            logger.error(f"Error sending event {event_type}: {e}")

    def get_connection_count(self) -> int:
        """Get current connection count."""
        return self.connection_pool.get_connection_count()

    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status."""
        return {
            "running": self._running,
            "connections": {
                "active": self.connection_pool.get_connection_count(),
                "max": self.connection_pool.max_connections,
                "utilization": self.connection_pool.get_utilization(),
            },
            "health": self.health_monitor.get_health_status(),
            "heartbeat": self.heartbeat_manager.get_status(),
            "compression": self.message_compressor.get_stats(),
        }

    def disconnect_client(self, client_id: str):
        """Disconnect specific client."""
        connection = self.connection_pool.get_connection(client_id)
        if connection:
            connection.close()
            self._cleanup_client(client_id)
            logger.info(f"Client {client_id} disconnected")

    def _cleanup_client(self, client_id: str):
        """Clean up client resources."""
        try:
            self.heartbeat_manager.unregister_connection(client_id)
            self.connection_pool.remove_connection(client_id)
            self.health_monitor.record_disconnection(client_id)
            logger.debug(f"Cleaned up resources for client {client_id}")
        except Exception as e:
            logger.error(f"Error cleaning up client {client_id}: {e}")

    def _format_sse_event(self, event_type: str, data: Any) -> str:
        """Format SSE event according to specification."""
        import json

        if isinstance(data, dict):
            data_str = json.dumps(data)
        else:
            data_str = str(data)

        return f"event: {event_type}\ndata: {data_str}\n\n"

    # Compatibility methods for existing interface
    def send_progress_update(self, client_id: str, progress: Dict[str, Any]):
        """Send progress update (compatibility method)."""
        self.send_event("progress", progress, client_id)

    def send_job_completion(self, client_id: str, result: Dict[str, Any]):
        """Send job completion (compatibility method)."""
        self.send_event("job_complete", result, client_id)

    def send_error(self, client_id: str, error: Dict[str, Any]):
        """Send error event (compatibility method)."""
        self.send_event("error", error, client_id)

    def broadcast_status(self, status: Dict[str, Any]):
        """Broadcast status update (compatibility method)."""
        self.send_event("status", status)
