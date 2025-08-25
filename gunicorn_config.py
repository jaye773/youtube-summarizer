"""
Gunicorn configuration for YouTube Summarizer with SSE support
This configuration uses async workers to handle long-lived SSE connections
"""

import multiprocessing
import os

# Worker configuration
# CRITICAL: Use gevent or eventlet for SSE support
worker_class = 'gevent'  # Async worker for SSE
workers = int(os.environ.get('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_connections = 1000
threads = 1  # Not used with gevent, but kept for compatibility

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"
backlog = 2048

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Logging
errorlog = '-'  # Log to stderr
loglevel = os.environ.get('LOG_LEVEL', 'info')
accesslog = '-'  # Log to stdout
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'youtube-summarizer'

# Server hooks
def when_ready(server):
    """Called just after the master process is initialized."""
    server.log.info("Server is ready. Spawning workers")
    server.log.info(f"Using worker class: {worker_class}")
    server.log.info(f"Number of workers: {workers}")

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info("Worker received INT or QUIT signal")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def worker_exit(server, worker):
    """Called just after a worker has been exited."""
    server.log.info(f"Worker exit (pid: {worker.pid})")

def nworkers_changed(server, new_value, old_value):
    """Called just after num_workers has been changed."""
    server.log.info(f"Number of workers changed from {old_value} to {new_value}")

# Timeouts
# CRITICAL: Long timeout for SSE connections
timeout = 86400  # 24 hours - for long-lived SSE connections
keepalive = 5  # Seconds to wait for requests on Keep-Alive connection
graceful_timeout = 30  # Timeout for graceful workers restart

# Limit requests
max_requests = 1000  # Restart workers after this many requests (helps with memory leaks)
max_requests_jitter = 50  # Randomize worker restart to avoid all workers restarting at once

# SSL Configuration (if needed)
# keyfile = None
# certfile = None
# ssl_version = ssl.PROTOCOL_TLS
# cert_reqs = ssl.CERT_NONE
# ca_certs = None

# Security
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# Server mechanics
preload_app = False  # Don't preload app for better development experience
reuse_port = False
spew = False
check_config = False
print_config = False

# StatsD integration (optional)
# statsd_host = None
# statsd_prefix = 'youtube-summarizer'
