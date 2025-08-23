"""
SSE (Server-Sent Events) Manager for YouTube Summarizer

This module provides Server-Sent Events functionality for real-time communication
between the backend worker system and connected clients. It manages multiple
concurrent SSE connections, handles event queuing and broadcasting, and provides
thread-safe connection management.

Classes:
    SSEConnection: Individual client connection management
    SSEManager: Main SSE manager for handling multiple connections
"""

import json
import logging
import queue
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class SSEConnection:
    """
    Manages an individual SSE client connection.

    Each connection has its own event queue and manages the lifecycle
    of a single client connection including event queuing, connection
    state tracking, and cleanup.
    """

    def __init__(self, client_id: str, subscriptions: Set[str] = None):
        """
        Initialize a new SSE connection.

        Args:
            client_id: Unique identifier for this client connection
            subscriptions: Set of event types this client is subscribed to
        """
        self.client_id = client_id
        self.queue = queue.Queue(maxsize=1000)  # Limit queue size to prevent memory issues
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.subscriptions = subscriptions or {"summary_progress", "summary_complete", "system"}
        self.is_active = True
        self._lock = threading.Lock()

        logger.info(f"SSE connection created for client {client_id} with subscriptions: {self.subscriptions}")

    def send_event(self, event_type: str, data: Dict[str, Any]) -> bool:
        """
        Queue an event for sending to the client.

        Args:
            event_type: Type of the event (e.g., 'summary_progress', 'summary_complete')
            data: Event data to send

        Returns:
            bool: True if event was queued successfully, False otherwise
        """
        if not self.is_active:
            return False

        # Check if client is subscribed to this event type
        if event_type not in self.subscriptions:
            return False

        try:
            with self._lock:
                # Format the event for SSE
                formatted_event = self._format_sse_event(event_type, data)
                self.queue.put(formatted_event, timeout=1.0)  # 1 second timeout
                self.last_activity = datetime.now()
                logger.debug(f"Event queued for client {self.client_id}: {event_type}")
                return True
        except queue.Full:
            logger.warning(f"Event queue full for client {self.client_id}, dropping event")
            return False
        except Exception as e:
            logger.error(f"Error queuing event for client {self.client_id}: {e}")
            return False

    def get_events(self, timeout: float = 30.0) -> List[str]:
        """
        Get pending events from the queue.

        Args:
            timeout: Maximum time to wait for events

        Returns:
            List[str]: List of formatted SSE event strings
        """
        events = []
        end_time = time.time() + timeout

        try:
            # Get first event with timeout
            event = self.queue.get(timeout=timeout)
            events.append(event)

            # Get any additional events that are immediately available
            while time.time() < end_time:
                try:
                    event = self.queue.get_nowait()
                    events.append(event)
                except queue.Empty:
                    break

        except queue.Empty:
            # Send heartbeat if no events
            events.append(self._format_sse_event("ping", {"timestamp": datetime.now().isoformat()}))

        return events

    def close(self):
        """Close the connection and clean up resources."""
        with self._lock:
            self.is_active = False
            # Clear any remaining events
            try:
                while True:
                    self.queue.get_nowait()
            except queue.Empty:
                pass

        logger.info(f"SSE connection closed for client {self.client_id}")

    def _format_sse_event(self, event_type: str, data: Dict[str, Any]) -> str:
        """
        Format data as SSE event string.

        Args:
            event_type: Type of the event
            data: Event data

        Returns:
            str: Formatted SSE event string
        """
        # Add metadata
        formatted_data = {**data, "timestamp": datetime.now().isoformat(), "client_id": self.client_id}

        # Format as SSE event
        event_lines = [f"event: {event_type}", f"data: {json.dumps(formatted_data)}"]

        return "\n".join(event_lines) + "\n\n"

    @property
    def age_seconds(self) -> float:
        """Get the age of this connection in seconds."""
        return (datetime.now() - self.created_at).total_seconds()

    @property
    def idle_seconds(self) -> float:
        """Get seconds since last activity."""
        return (datetime.now() - self.last_activity).total_seconds()


class SSEManager:
    """
    Main SSE manager for handling multiple client connections.

    Manages the lifecycle of multiple SSE connections, provides broadcasting
    capabilities, handles connection cleanup, and maintains thread safety
    across all operations.
    """

    def __init__(self, heartbeat_interval: int = 30, max_connections: int = 100):
        """
        Initialize the SSE manager.

        Args:
            heartbeat_interval: Interval between heartbeat messages in seconds
            max_connections: Maximum number of concurrent connections
        """
        self.connections: Dict[str, SSEConnection] = {}
        self._lock = threading.RLock()  # Use RLock for nested locking
        self.heartbeat_interval = heartbeat_interval
        self.max_connections = max_connections
        self._cleanup_thread = None
        self._shutdown_event = threading.Event()

        # Start background cleanup thread
        self._start_cleanup_thread()

        logger.info(
            f"SSE Manager initialized with max_connections={max_connections}, heartbeat_interval={heartbeat_interval}s"
        )

    def add_connection(self, client_id: str = None, subscriptions: Set[str] = None) -> SSEConnection:
        """
        Register a new SSE connection.

        Args:
            client_id: Optional client ID. If not provided, a UUID will be generated
            subscriptions: Set of event types the client wants to subscribe to

        Returns:
            SSEConnection: The new connection instance

        Raises:
            RuntimeError: If maximum connections limit is reached
        """
        if client_id is None:
            client_id = str(uuid.uuid4())

        with self._lock:
            # Check connection limit
            if len(self.connections) >= self.max_connections:
                raise RuntimeError(f"Maximum connections limit reached ({self.max_connections})")

            # Remove existing connection if client reconnects
            if client_id in self.connections:
                logger.info(f"Replacing existing connection for client {client_id}")
                self.connections[client_id].close()
                del self.connections[client_id]

            # Create new connection
            connection = SSEConnection(client_id, subscriptions)
            self.connections[client_id] = connection

            # Send connection confirmation event
            connection.send_event(
                "connected",
                {
                    "connection_id": client_id,
                    "subscriptions": list(connection.subscriptions),
                    "server_time": datetime.now().isoformat(),
                },
            )

            logger.info(f"SSE connection added: {client_id} (total: {len(self.connections)})")
            return connection

    def remove_connection(self, client_id: str) -> bool:
        """
        Remove and clean up a client connection.

        Args:
            client_id: ID of the client to remove

        Returns:
            bool: True if connection was removed, False if not found
        """
        with self._lock:
            if client_id in self.connections:
                connection = self.connections[client_id]
                connection.close()
                del self.connections[client_id]
                logger.info(f"SSE connection removed: {client_id} (remaining: {len(self.connections)})")
                return True
            return False

    def get_connection(self, client_id: str) -> Optional[SSEConnection]:
        """
        Get a connection by client ID.

        Args:
            client_id: ID of the client

        Returns:
            SSEConnection or None if not found
        """
        with self._lock:
            return self.connections.get(client_id)

    def broadcast_event(
        self, event_type: str, data: Dict[str, Any], filter_func: Callable[[SSEConnection], bool] = None
    ) -> Dict[str, int]:
        """
        Broadcast an event to multiple clients.

        Args:
            event_type: Type of event to broadcast
            data: Event data
            filter_func: Optional function to filter which connections receive the event

        Returns:
            Dict with statistics about the broadcast
        """
        sent_count = 0
        failed_count = 0
        filtered_count = 0

        with self._lock:
            connections_snapshot = list(self.connections.items())

        for client_id, connection in connections_snapshot:
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
                logger.error(f"Error broadcasting to client {client_id}: {e}")
                failed_count += 1

        result = {
            "sent": sent_count,
            "failed": failed_count,
            "filtered": filtered_count,
            "total_connections": len(connections_snapshot),
        }

        logger.debug(f"Broadcast {event_type}: {result}")
        return result

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about current connections.

        Returns:
            Dict with connection statistics
        """
        with self._lock:
            connections_snapshot = list(self.connections.values())

        total = len(connections_snapshot)
        if total == 0:
            return {
                "total_connections": 0,
                "average_age_seconds": 0,
                "average_idle_seconds": 0,
                "oldest_connection_seconds": 0,
                "subscriptions_summary": {},
            }

        ages = [conn.age_seconds for conn in connections_snapshot]
        idle_times = [conn.idle_seconds for conn in connections_snapshot]

        # Count subscriptions
        subscriptions_count = {}
        for conn in connections_snapshot:
            for sub in conn.subscriptions:
                subscriptions_count[sub] = subscriptions_count.get(sub, 0) + 1

        return {
            "total_connections": total,
            "average_age_seconds": sum(ages) / total,
            "average_idle_seconds": sum(idle_times) / total,
            "oldest_connection_seconds": max(ages),
            "subscriptions_summary": subscriptions_count,
            "active_connections": len([c for c in connections_snapshot if c.is_active]),
        }

    def cleanup_stale_connections(self, max_idle_seconds: int = 300) -> int:
        """
        Clean up connections that have been idle for too long.

        Args:
            max_idle_seconds: Maximum idle time before cleanup (default 5 minutes)

        Returns:
            int: Number of connections cleaned up
        """
        cleaned_count = 0
        current_time = datetime.now()

        with self._lock:
            stale_clients = []
            for client_id, connection in self.connections.items():
                idle_time = (current_time - connection.last_activity).total_seconds()
                if not connection.is_active or idle_time > max_idle_seconds:
                    stale_clients.append(client_id)

            # Remove stale connections
            for client_id in stale_clients:
                if self.remove_connection(client_id):
                    cleaned_count += 1

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} stale SSE connections")

        return cleaned_count

    def shutdown(self):
        """Shutdown the SSE manager and cleanup all resources."""
        logger.info("Shutting down SSE Manager")

        # Signal shutdown to background thread
        self._shutdown_event.set()

        # Wait for cleanup thread to finish
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5.0)

        # Close all connections
        with self._lock:
            client_ids = list(self.connections.keys())
            for client_id in client_ids:
                self.remove_connection(client_id)

        logger.info("SSE Manager shutdown complete")

    def _start_cleanup_thread(self):
        """Start the background cleanup thread."""

        def cleanup_worker():
            while not self._shutdown_event.is_set():
                try:
                    # Wait for shutdown or heartbeat interval
                    if self._shutdown_event.wait(self.heartbeat_interval):
                        break  # Shutdown requested

                    # Cleanup stale connections
                    self.cleanup_stale_connections()

                    # Send heartbeat to active connections
                    self._send_heartbeat()

                except Exception as e:
                    logger.error(f"Error in SSE cleanup thread: {e}")

        self._cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        self._cleanup_thread.start()
        logger.debug("SSE cleanup thread started")

    def _send_heartbeat(self):
        """Send heartbeat events to all active connections."""
        heartbeat_data = {
            "message": "heartbeat",
            "server_time": datetime.now().isoformat(),
            "connection_count": len(self.connections),
        }

        # Only send to connections that haven't had activity recently
        def needs_heartbeat(conn: SSEConnection) -> bool:
            return conn.idle_seconds > (self.heartbeat_interval * 0.8)

        result = self.broadcast_event("ping", heartbeat_data, filter_func=needs_heartbeat)

        if result["sent"] > 0:
            logger.debug(f"Sent heartbeat to {result['sent']} connections")


# Utility functions for SSE event formatting


def format_summary_progress_event(
    job_id: str, video_id: str, progress: float, status: str, message: str = ""
) -> Dict[str, Any]:
    """
    Format a summary progress event.

    Args:
        job_id: Unique job identifier
        video_id: YouTube video ID
        progress: Progress value between 0.0 and 1.0
        status: Current status (e.g., 'processing', 'getting_transcript')
        message: Optional status message

    Returns:
        Dict formatted for SSE transmission
    """
    return {
        "job_id": job_id,
        "video_id": video_id,
        "progress": min(max(progress, 0.0), 1.0),  # Clamp between 0-1
        "status": status,
        "message": message,
    }


def format_summary_complete_event(
    job_id: str, video_id: str, title: str, summary: str, thumbnail_url: str = "", cached: bool = False
) -> Dict[str, Any]:
    """
    Format a summary completion event.

    Args:
        job_id: Unique job identifier
        video_id: YouTube video ID
        title: Video title
        summary: Generated summary text
        thumbnail_url: Optional video thumbnail URL
        cached: Whether the summary was served from cache

    Returns:
        Dict formatted for SSE transmission
    """
    return {
        "job_id": job_id,
        "video_id": video_id,
        "title": title,
        "summary": summary,
        "thumbnail_url": thumbnail_url,
        "cached": cached,
    }


def format_system_event(message: str, level: str = "info", data: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Format a system event.

    Args:
        message: System message
        level: Message level ('info', 'warning', 'error')
        data: Optional additional data

    Returns:
        Dict formatted for SSE transmission
    """
    event_data = {"message": message, "level": level}

    if data:
        event_data.update(data)

    return event_data


# Global SSE manager instance
_sse_manager_instance = None
_sse_manager_lock = threading.Lock()


def get_sse_manager() -> SSEManager:
    """
    Get the global SSE manager instance (singleton pattern).

    Returns:
        SSEManager: The global SSE manager instance
    """
    global _sse_manager_instance

    if _sse_manager_instance is None:
        with _sse_manager_lock:
            if _sse_manager_instance is None:
                _sse_manager_instance = SSEManager()

    return _sse_manager_instance


def shutdown_sse_manager():
    """Shutdown the global SSE manager instance."""
    global _sse_manager_instance

    with _sse_manager_lock:
        if _sse_manager_instance is not None:
            _sse_manager_instance.shutdown()
            _sse_manager_instance = None
