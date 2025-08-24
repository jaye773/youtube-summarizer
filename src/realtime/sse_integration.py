"""
SSE Integration Module - Bridges enhanced SSE with existing Flask app
"""

import logging

from flask import Response, request

from src.realtime.sse.enhanced_sse_manager import EnhancedSSEManager

logger = logging.getLogger(__name__)

# Global SSE manager instance
_sse_manager = None


def init_sse(app, config=None):
    """Initialize enhanced SSE with Flask app"""
    global _sse_manager

    # Default configuration
    default_config = {
        "max_connections": 500,
        "max_connections_per_ip": 10,
        "heartbeat_interval": 30,
        "compression_threshold": 1024,
        "cleanup_interval": 60,
        "idle_timeout": 300,
    }

    # Merge with provided config
    if config:
        default_config.update(config)

    # Create enhanced SSE manager
    _sse_manager = EnhancedSSEManager(**default_config)

    # Register Flask routes
    @app.route("/sse")
    def sse_stream():
        """SSE streaming endpoint"""
        client_ip = request.remote_addr
        user_agent = request.headers.get("User-Agent", "Unknown")

        # Register connection
        client_id = _sse_manager.register_connection(client_ip, user_agent)

        if not client_id:
            return Response("Connection limit reached", status=503)

        try:
            # Return SSE stream
            return Response(
                _sse_manager.get_sse_stream(client_id),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
            )
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            _sse_manager.remove_connection(client_id)
            raise

    @app.route("/sse/health")
    def sse_health():
        """SSE health status endpoint"""
        return _sse_manager.get_health_status()

    # Start SSE manager
    _sse_manager.start()
    logger.info("Enhanced SSE initialized successfully")

    # Register shutdown handler
    @app.teardown_appcontext
    def shutdown_sse(error=None):
        if _sse_manager:
            _sse_manager.stop()

    return _sse_manager


def get_sse_manager():
    """Get the global SSE manager instance"""
    return _sse_manager


def send_job_update(job_id, event_type, data):
    """Send job update to all clients subscribed to this job"""
    if not _sse_manager:
        logger.warning("SSE manager not initialized")
        return

    # Send to all clients (manager handles filtering)
    for client_id in _sse_manager.get_active_connections():
        _sse_manager.send_event(client_id, event_type, {"job_id": job_id, **data})


def send_progress_update(job_id, progress, message=None):
    """Send progress update for a job"""
    send_job_update(job_id, "job_progress", {"progress": progress, "message": message})


def send_completion_update(job_id, result):
    """Send completion update for a job"""
    send_job_update(job_id, "job_complete", {"result": result})


def send_error_update(job_id, error):
    """Send error update for a job"""
    send_job_update(job_id, "job_error", {"error": str(error)})
