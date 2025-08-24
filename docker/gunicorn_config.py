"""
Gunicorn configuration for SSE support
"""

import multiprocessing
import os

# Server Socket
bind = "0.0.0.0:5001"
backlog = 2048

# Worker Processes
# IMPORTANT: For SSE, we need to use single worker or implement sticky sessions
workers = 1  # SSE requires single worker or sticky sessions
worker_class = "eventlet"  # Async worker for SSE support
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50

# Timeouts
timeout = 300  # 5 minutes for long-lived SSE connections
graceful_timeout = 30
keepalive = 75  # Keep connections alive longer for SSE

# Logging
accesslog = "/app/logs/gunicorn.access.log"
errorlog = "/app/logs/gunicorn.error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process Naming
proc_name = "youtube-summarizer-sse"

# Server Mechanics
daemon = False
pidfile = "/var/run/gunicorn.pid"
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
keyfile = None
certfile = None

# SSE-specific settings via environment
raw_env = [
    "SSE_HEARTBEAT_INTERVAL=30",
    "SSE_MAX_CONNECTIONS=500",
    "SSE_COMPRESSION_THRESHOLD=1024",
]


def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Gunicorn server is ready. Listening at: %s", server.address)


def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info("Worker received INT or QUIT signal")


def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info("Forking worker %s", worker)


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)


def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    worker.log.info("Worker received SIGABRT signal")
