"""Background summary requests: a small bounded executor plus an in-memory request store.

``POST /summarize/start`` submits a batch of URLs here and returns at once; the
batch runs on a ``ThreadPoolExecutor`` and its results are recorded in a
``RequestStore`` keyed by request id and owned by the submitting session.

Like the SSE registry and the summary cache, this state lives in process
memory, so it relies on the app running as a single process.
"""

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

MAX_WORKERS = max(1, int(os.environ.get("SUMMARY_WORKERS", "2")))
# How long a finished request's results stay retrievable
REQUEST_TTL_SECONDS = int(os.environ.get("SUMMARY_REQUEST_TTL", "3600"))
# Upper bound on stored requests (finished ones are evicted first, oldest first)
MAX_REQUESTS = int(os.environ.get("SUMMARY_MAX_REQUESTS", "200"))
# Upper bound on requests one session may have queued or running at once
MAX_ACTIVE_PER_SESSION = int(os.environ.get("SUMMARY_MAX_ACTIVE_PER_SESSION", "3"))

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
FINISHED_STATUSES = (STATUS_COMPLETED, STATUS_FAILED)


class StoreFullError(Exception):
    """Raised when a request cannot be accepted because a limit is reached."""


class RequestStore:
    """Thread-safe store of background summary requests.

    Each request records:
      - ``results``: the same list ``POST /summarize`` returns (playlist entries
        grow as their videos finish), and
      - ``items``: the ordered stream of per-result payloads that were also
        pushed over SSE, each with a ``seq`` number so clients can tell which
        ones they have already rendered.
    """

    def __init__(self, ttl_seconds=REQUEST_TTL_SECONDS, max_requests=MAX_REQUESTS,
                 max_active_per_session=MAX_ACTIVE_PER_SESSION, clock=time.time):
        self.ttl_seconds = ttl_seconds
        self.max_requests = max_requests
        self.max_active_per_session = max_active_per_session
        self._clock = clock
        self._lock = threading.Lock()
        self._requests = {}

    # -- lifecycle -----------------------------------------------------------
    def create(self, session_id, urls, model_key):
        """Register a new queued request and return its id."""
        with self._lock:
            self._cleanup_locked()
            active = sum(
                1 for r in self._requests.values()
                if r["session_id"] == session_id and r["status"] not in FINISHED_STATUSES
            )
            if active >= self.max_active_per_session:
                raise StoreFullError("Too many summary requests in progress; wait for one to finish.")
            if len(self._requests) >= self.max_requests:
                self._evict_finished_locked(len(self._requests) - self.max_requests + 1)
            if len(self._requests) >= self.max_requests:
                raise StoreFullError("The server is busy; try again shortly.")

            request_id = uuid.uuid4().hex
            now = self._clock()
            self._requests[request_id] = {
                "request_id": request_id,
                "session_id": session_id,
                "status": STATUS_QUEUED,
                "model": model_key,
                "url_count": len(urls),
                "results": [],
                "items": [],
                "error": None,
                "created_at": now,
                "updated_at": now,
                "finished_at": None,
            }
            return request_id

    def mark_running(self, request_id):
        self._update(request_id, status=STATUS_RUNNING)

    def finish(self, request_id, results=None, error=None):
        """Mark a request completed (or failed when ``error`` is given)."""
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                return
            if results is not None:
                req["results"] = results
            req["error"] = error
            req["status"] = STATUS_FAILED if error else STATUS_COMPLETED
            req["updated_at"] = req["finished_at"] = self._clock()

    def discard(self, request_id):
        with self._lock:
            self._requests.pop(request_id, None)

    # -- results -------------------------------------------------------------
    def add_item(self, request_id, payload):
        """Append a per-result payload, assigning and returning its ``seq``."""
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                return None
            payload = dict(payload, seq=len(req["items"]))
            req["items"].append(payload)
            _fold_into_results(req["results"], payload)
            req["updated_at"] = self._clock()
            return payload

    # -- reads ---------------------------------------------------------------
    def get(self, request_id, session_id):
        """Return a snapshot of the request if ``session_id`` owns it, else None."""
        with self._lock:
            self._cleanup_locked()
            req = self._requests.get(request_id)
            if req is None or req["session_id"] != session_id:
                return None
            return {
                "request_id": req["request_id"],
                "status": req["status"],
                "model": req["model"],
                "url_count": req["url_count"],
                "results": _copy_results(req["results"]),
                "items": list(req["items"]),
                "error": req["error"],
                "done": req["status"] in FINISHED_STATUSES,
            }

    def __len__(self):
        with self._lock:
            return len(self._requests)

    def clear(self):
        with self._lock:
            self._requests.clear()

    # -- housekeeping --------------------------------------------------------
    def cleanup(self):
        with self._lock:
            self._cleanup_locked()

    def _update(self, request_id, **fields):
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                return
            req.update(fields)
            req["updated_at"] = self._clock()

    def _cleanup_locked(self):
        cutoff = self._clock() - self.ttl_seconds
        expired = [
            rid for rid, r in self._requests.items()
            # Finished requests expire TTL after finishing; anything untouched for a
            # whole TTL (e.g. a worker that died) is dropped too.
            if (r["finished_at"] is not None and r["finished_at"] < cutoff) or r["updated_at"] < cutoff
        ]
        for rid in expired:
            del self._requests[rid]

    def _evict_finished_locked(self, count):
        finished = sorted(
            (r for r in self._requests.values() if r["status"] in FINISHED_STATUSES),
            key=lambda r: r["finished_at"],
        )
        for req in finished[:count]:
            del self._requests[req["request_id"]]


def _fold_into_results(results, payload):
    """Apply one per-result payload to a ``/summarize``-shaped results list."""
    kind, item = payload.get("kind"), payload.get("item")
    if kind == "playlist":
        results.append(dict(item, summaries=list(item.get("summaries") or []), _index=payload.get("index")))
    elif kind == "playlist_video":
        for entry in reversed(results):
            if entry.get("type") == "playlist" and entry.get("_index") == payload.get("index"):
                entry["summaries"].append(item)
                return
        results.append({
            "type": "playlist", "title": payload.get("playlist_title"),
            "summaries": [item], "_index": payload.get("index"),
        })
    else:
        results.append(item)


def _copy_results(results):
    """Copy the results list deeply enough that playlist ``summaries`` lists are not shared."""
    copied = []
    for item in results:
        item = {k: v for k, v in item.items() if k != "_index"}
        if isinstance(item.get("summaries"), list):
            item["summaries"] = list(item["summaries"])
        copied.append(item)
    return copied


class _ImmediateFuture:
    def __init__(self, exc=None):
        self._exc = exc

    def result(self, timeout=None):
        if self._exc:
            raise self._exc

    def done(self):
        return True


class SummaryExecutor:
    """Bounded thread pool; ``synchronous=True`` runs jobs inline (used by tests)."""

    def __init__(self, max_workers=MAX_WORKERS, synchronous=False):
        self.max_workers = max_workers
        self.synchronous = synchronous
        self._pool = None
        self._lock = threading.Lock()

    def submit(self, fn, *args, **kwargs):
        if self.synchronous:
            try:
                fn(*args, **kwargs)
            except Exception as e:  # mirror Future semantics: never raise from submit
                return _ImmediateFuture(e)
            return _ImmediateFuture()
        with self._lock:
            if self._pool is None:
                self._pool = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="summary")
            pool = self._pool
        return pool.submit(fn, *args, **kwargs)

    def shutdown(self, wait=True):
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=wait)


store = RequestStore()
executor = SummaryExecutor()
