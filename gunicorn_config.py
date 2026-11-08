"""
Gunicorn configuration for YouTube Summarizer.

The app keeps its state in process memory (summary cache, SSE connections,
login lockouts), so it MUST run as a single process. Concurrency comes from
threads: the gthread worker gives each request - including each long-lived
SSE stream - its own thread, and its heartbeat runs independently of request
threads so slow summaries are not killed by the worker timeout.
"""

import os

worker_class = "gthread"
workers = 1  # Do not raise: state is per-process (see module docstring)
threads = int(os.environ.get("GUNICORN_THREADS", "32"))

bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"

# Worker heartbeat timeout (not a per-request limit under gthread)
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5

errorlog = "-"
accesslog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

proc_name = "youtube-summarizer"

limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# Must stay False: importing app starts background threads, which would not
# survive the fork into the worker process.
preload_app = False
