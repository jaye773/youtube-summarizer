"""Server-Sent Events: connection registry, broadcasting and message formatting.

Connections live in process memory, which is why the app runs as a single
gunicorn process (see gunicorn_config.py). Each open stream occupies one
server thread, so the number of concurrent streams is capped.
"""

import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from queue import Empty, Queue

# Each stream holds a gunicorn thread; keep this below GUNICORN_THREADS so
# ordinary requests always have threads available.
MAX_CONNECTIONS = int(os.environ.get("SSE_MAX_CONNECTIONS", "20"))
STALE_AFTER = timedelta(minutes=5)
KEEPALIVE_SECONDS = 30

DEFAULT_SUBSCRIPTIONS = frozenset({"summary_complete", "summary_progress", "system"})

connections = {}
lock = threading.Lock()


class SSEConnection:
    """State for one client's event stream."""

    def __init__(self, connection_id, session_id=None, user_ip=None, subscriptions=None):
        self.connection_id = connection_id
        self.session_id = session_id
        self.user_ip = user_ip
        self.message_queue = Queue()
        self.created_at = datetime.now(timezone.utc)
        self.last_activity = self.created_at
        self.is_active = True
        self.subscriptions = set(subscriptions or DEFAULT_SUBSCRIPTIONS)

    def send_message(self, event_type, data, event_id=None, retry=None):
        """Queue a message for this connection. Returns False if the connection is dead."""
        if not self.is_active:
            return False
        try:
            self.message_queue.put(
                {
                    "event": event_type,
                    "data": data,
                    "id": event_id or str(uuid.uuid4()),
                    "retry": retry,
                },
                timeout=1,
            )
            return True
        except Exception:
            self.is_active = False
            return False

    def get_messages(self, timeout=KEEPALIVE_SECONDS):
        """Yield queued messages, emitting a keep-alive ping when idle."""
        while self.is_active:
            try:
                message = self.message_queue.get(timeout=timeout)
            except Empty:
                message = {"event": "ping", "data": "keep-alive", "id": str(uuid.uuid4())}
            if message is None:  # Poison pill from close()
                break
            yield message
            # A successful yield (including a ping) means the client is still there
            self.last_activity = datetime.now(timezone.utc)

    def close(self):
        self.is_active = False
        self.message_queue.put(None)


def register(session_id, user_ip, subscriptions=None):
    """Create and register a connection, or return None if at capacity."""
    cleanup_stale_connections()
    with lock:
        if len(connections) >= MAX_CONNECTIONS:
            return None
        connection = SSEConnection(str(uuid.uuid4()), session_id, user_ip, subscriptions)
        connections[connection.connection_id] = connection
        return connection


def unregister(connection):
    with lock:
        connections.pop(connection.connection_id, None)
    connection.close()


def connection_count():
    with lock:
        return len(connections)


def cleanup_stale_connections():
    """Drop connections with no successful write for STALE_AFTER, or already closed."""
    cutoff_time = datetime.now(timezone.utc) - STALE_AFTER
    with lock:
        stale = [cid for cid, conn in connections.items() if conn.last_activity < cutoff_time or not conn.is_active]
        for cid in stale:
            connections.pop(cid).close()


def broadcast(event_type, data, session_filter=None, subscription_filter=None):
    """Send an event to every connection matching the session and subscription filters."""
    cleanup_stale_connections()
    with lock:
        for cid, connection in list(connections.items()):
            if session_filter and connection.session_id != session_filter:
                continue
            if subscription_filter and subscription_filter not in connection.subscriptions:
                continue
            if not connection.send_message(event_type, data):
                connections.pop(cid, None)


def format_sse_message(event_type, data, event_id=None, retry=None):
    """Format one Server-Sent Events message."""
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    if retry:
        lines.append(f"retry: {retry}")
    lines.append(f"event: {event_type}")

    data_str = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
    for line in data_str.split("\n"):
        lines.append(f"data: {line}")

    lines.append("")
    return "\n".join(lines) + "\n"


def stream(connection):
    """Generator producing the wire format for a registered connection."""
    try:
        yield format_sse_message(
            "connected",
            {
                "connection_id": connection.connection_id,
                "message": "Connected to notification stream",
                "subscriptions": sorted(connection.subscriptions),
            },
            event_id=connection.connection_id,
        )
        for message in connection.get_messages():
            yield format_sse_message(message["event"], message["data"], message["id"], message.get("retry"))
    finally:
        unregister(connection)


# Response headers for an event stream (no hop-by-hop headers: WSGI forbids them)
STREAM_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "X-Accel-Buffering": "no",  # disable buffering in nginx-style proxies
}
