"""Tests for the sse module (connection registry, broadcast, formatting)."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import sse


class TestSSE(unittest.TestCase):
    def setUp(self):
        with sse.lock:
            sse.connections.clear()

    tearDown = setUp

    def _drain(self, connection):
        messages = []
        while not connection.message_queue.empty():
            messages.append(connection.message_queue.get_nowait())
        return messages

    def test_format_sse_message(self):
        msg = sse.format_sse_message("summary_progress", {"a": 1}, event_id="e1")
        self.assertEqual(msg, 'id: e1\nevent: summary_progress\ndata: {"a": 1}\n\n')

    def test_format_multiline_data(self):
        msg = sse.format_sse_message("system", "line1\nline2")
        self.assertIn("data: line1\ndata: line2\n", msg)

    def test_broadcast_is_scoped_to_session(self):
        mine = sse.register("session-a", "1.1.1.1")
        other = sse.register("session-b", "2.2.2.2")
        sse.broadcast("summary_progress", {"x": 1}, session_filter="session-a", subscription_filter="summary_progress")
        self.assertEqual(len(self._drain(mine)), 1)
        self.assertEqual(self._drain(other), [])

    def test_broadcast_respects_subscriptions(self):
        conn = sse.register("s", "ip", subscriptions={"system"})
        sse.broadcast("summary_progress", {}, subscription_filter="summary_progress")
        self.assertEqual(self._drain(conn), [])

    def test_connection_cap(self):
        with patch("sse.MAX_CONNECTIONS", 2):
            self.assertIsNotNone(sse.register("s", "ip"))
            self.assertIsNotNone(sse.register("s", "ip"))
            self.assertIsNone(sse.register("s", "ip"))

    def test_keepalive_ping_refreshes_activity(self):
        """An idle but open stream must not be reaped as stale"""
        conn = sse.register("s", "ip")
        conn.last_activity = datetime.now(timezone.utc) - timedelta(minutes=10)
        gen = conn.get_messages(timeout=0.01)
        self.assertEqual(next(gen)["event"], "ping")
        next(gen)  # resumes after the yield, recording activity
        self.assertGreater(conn.last_activity, datetime.now(timezone.utc) - timedelta(minutes=1))

    def test_stale_connections_are_reaped(self):
        conn = sse.register("s", "ip")
        conn.last_activity = datetime.now(timezone.utc) - timedelta(minutes=10)
        sse.cleanup_stale_connections()
        self.assertEqual(sse.connection_count(), 0)
        self.assertFalse(conn.is_active)

    def test_stream_unregisters_on_close(self):
        conn = sse.register("s", "ip")
        stream = sse.stream(conn)
        first = next(stream)
        self.assertIn("event: connected", first)
        payload = json.loads(first.split("data: ", 1)[1])
        self.assertEqual(payload["connection_id"], conn.connection_id)
        stream.close()
        self.assertEqual(sse.connection_count(), 0)


if __name__ == "__main__":
    unittest.main()
