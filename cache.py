import json
import os
import sqlite3
import tempfile
import threading
from collections.abc import MutableMapping
from datetime import datetime, timezone

# Serializes cache writes within a process so concurrent request threads and
# worker threads cannot truncate or interleave each other's writes.
_cache_write_lock = threading.Lock()


def load_summary_cache(cache_file):
    """Load the summary cache from disk.

    Args:
        cache_file: Path to the JSON cache file.

    Returns:
        dict: The loaded cache, or an empty dict if the file does not exist or
              contains invalid JSON.
    """
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_summary_cache(cache, cache_file):
    """Persist the summary cache to disk.

    Args:
        cache: dict mapping video_id to cache entry dicts, or a SummaryCache.
        cache_file: Path to the JSON cache file.

    A SummaryCache commits every write immediately, so for it this is a no-op.
    Plain dicts keep the legacy JSON behaviour: the write is atomic
    (serialized via a lock, written to a temp file in the same directory, then
    ``os.replace``d into place) so a crash or a concurrent writer can never
    leave a truncated/corrupt cache on disk.
    """
    if isinstance(cache, SummaryCache):
        return
    with _cache_write_lock:
        directory = os.path.dirname(cache_file) or "."
        os.makedirs(directory, exist_ok=True)
        # Snapshot under the lock to avoid "dictionary changed size during
        # iteration" if another thread mutates the cache while we serialize it.
        payload = json.dumps(dict(cache), indent=4)
        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, cache_file)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise


def build_cache_entry(title, summary, thumbnail_url, video_id, model_key, audio_filename=None):
    """Construct a standardised cache entry dict for a summarised video.

    Args:
        title: Human-readable video title.
        summary: Generated summary text.
        thumbnail_url: URL of the video thumbnail image.
        video_id: YouTube video ID (used to build the canonical video URL).
        model_key: Identifier of the AI model used to generate the summary.
        audio_filename: Optional filename of the pre-generated audio file.

    Returns:
        dict: A cache entry ready to be stored under summary_cache[video_id].
    """
    return {
        "title": title,
        "summary": summary,
        "thumbnail_url": thumbnail_url,
        "summarized_at": datetime.now(timezone.utc).isoformat(),
        "audio_filename": audio_filename,
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "model_used": model_key,
    }


# --- SQLite-backed summary store ---

# Columns stored natively. Any other keys in an entry go to the JSON ``extra``
# column so nothing is lost.
ENTRY_FIELDS = (
    "title",
    "summary",
    "thumbnail_url",
    "summarized_at",
    "audio_filename",
    "video_url",
    "model_used",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS summaries (
    video_id       TEXT PRIMARY KEY,
    title          TEXT,
    summary        TEXT,
    thumbnail_url  TEXT,
    summarized_at  TEXT,
    audio_filename TEXT,
    video_url      TEXT,
    model_used     TEXT,
    extra          TEXT
);
CREATE INDEX IF NOT EXISTS idx_summaries_summarized_at ON summaries (summarized_at);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

_SELECT_COLS = "video_id, " + ", ".join(ENTRY_FIELDS) + ", extra"
_UPSERT_SQL = (
    f"INSERT INTO summaries ({_SELECT_COLS}) VALUES ({', '.join('?' * (len(ENTRY_FIELDS) + 2))}) "
    "ON CONFLICT(video_id) DO UPDATE SET "
    + ", ".join(f"{c} = excluded.{c}" for c in ENTRY_FIELDS + ("extra",))
)
# Newest first (NULL sorts lowest, so last), ties in insertion order (same as a stable sort of the old dict).
_ORDER_BY = "ORDER BY summarized_at DESC, rowid ASC"
_MIGRATED_KEY = "migrated_from_json"


def _sql_lower(value):
    """Unicode-aware lower() for SQL (SQLite's built-in lower() is ASCII-only)."""
    return value.lower() if isinstance(value, str) else ""


class SummaryCache(MutableMapping):
    """Summary store backed by SQLite that behaves like ``dict[str, dict]``.

    Writes (``cache[k] = v``, ``del cache[k]``) are committed immediately.
    Values returned by ``cache[k]`` are fresh dicts: mutating one does not
    change the store; assign it back instead.

    Threading: one connection opened with ``check_same_thread=False``, with
    every statement serialized through a lock. Traffic is light (one write per
    generated summary, small paginated reads), so one connection is plenty, and
    it behaves the same for ``:memory:`` databases, where per-thread
    connections would each see a different empty database. Other processes
    share the file safely through SQLite's own locking (WAL mode plus a busy
    timeout), so the store no longer pins the app to one process.
    """

    def __init__(self, db_path):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._lock = threading.RLock()
        # isolation_level=None: autocommit; multi-statement transactions use explicit BEGIN.
        self._conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False, isolation_level=None)
        self._conn.create_function("py_lower", 1, _sql_lower)
        with self._lock:
            if db_path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)

    # -- row conversion --

    @staticmethod
    def _to_row(video_id, entry):
        if not isinstance(entry, dict):
            raise TypeError(f"cache entries must be dicts, got {type(entry).__name__}")
        extra = {k: v for k, v in entry.items() if k not in ENTRY_FIELDS}
        values = []
        for field in ENTRY_FIELDS:
            value = entry.get(field)
            if value is not None and not isinstance(value, (str, int, float)):
                # Not storable in a scalar column: keep it intact in extra.
                extra[field] = value
                value = None
            values.append(value)
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else None
        return (str(video_id), *values, extra_json)

    @staticmethod
    def _from_row(row):
        entry = dict(zip(ENTRY_FIELDS, row[1:-1]))
        if row[-1]:
            entry.update(json.loads(row[-1]))
        return row[0], entry

    def _query(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # -- MutableMapping interface --

    def __getitem__(self, video_id):
        rows = self._query(f"SELECT {_SELECT_COLS} FROM summaries WHERE video_id = ?", (video_id,))
        if not rows:
            raise KeyError(video_id)
        return self._from_row(rows[0])[1]

    def __setitem__(self, video_id, entry):
        row = self._to_row(video_id, entry)
        with self._lock:
            self._conn.execute(_UPSERT_SQL, row)

    def __delitem__(self, video_id):
        with self._lock:
            deleted = self._conn.execute("DELETE FROM summaries WHERE video_id = ?", (video_id,)).rowcount
        if not deleted:
            raise KeyError(video_id)

    def __contains__(self, video_id):
        return bool(self._query("SELECT 1 FROM summaries WHERE video_id = ?", (video_id,)))

    def __iter__(self):
        # Snapshot, so concurrent writes cannot break iteration.
        return iter([r[0] for r in self._query("SELECT video_id FROM summaries ORDER BY rowid")])

    def __len__(self):
        return self.count()

    def __repr__(self):
        return f"SummaryCache({self.db_path!r})"

    def items(self):
        """All (video_id, entry) pairs, loaded in one query."""
        return [self._from_row(r) for r in self._query(f"SELECT {_SELECT_COLS} FROM summaries ORDER BY rowid")]

    def values(self):
        return [entry for _, entry in self.items()]

    def clear(self):
        with self._lock:
            self._conn.execute("DELETE FROM summaries")

    # -- efficient queries --

    def count(self):
        return self._query("SELECT COUNT(*) FROM summaries")[0][0]

    def list_page(self, offset=0, limit=None):
        """Entries newest first as (video_id, entry) pairs; ``limit=None`` means all."""
        limit = -1 if limit is None else max(int(limit), 0)
        rows = self._query(
            f"SELECT {_SELECT_COLS} FROM summaries {_ORDER_BY} LIMIT ? OFFSET ?",
            (limit, max(int(offset), 0)),
        )
        return [self._from_row(r) for r in rows]

    def search(self, query):
        """Case-insensitive substring match on title or summary, newest first."""
        needle = query.lower()
        rows = self._query(
            f"SELECT {_SELECT_COLS} FROM summaries "
            f"WHERE instr(py_lower(title), ?) > 0 OR instr(py_lower(summary), ?) > 0 {_ORDER_BY}",
            (needle, needle),
        )
        return [self._from_row(r) for r in rows]

    def close(self):
        with self._lock:
            self._conn.close()

    # -- one-time JSON migration --

    def migrate_from_json(self, json_path):
        """Import a legacy ``summary_cache.json`` once, then rename it to ``*.migrated``.

        Runs only when the database is empty. The rows and a marker row are
        committed in one transaction and the rename happens afterwards, so if
        the process dies in between, the next start sees the marker and only
        finishes the rename. Returns the number of entries imported.
        """
        if not os.path.exists(json_path):
            return 0

        if self._query("SELECT 1 FROM meta WHERE key = ?", (_MIGRATED_KEY,)):
            _rename_migrated(json_path)
            return 0
        if self.count():
            print(f"⚠️ Not migrating {json_path}: {self.db_path} already holds summaries")
            return 0

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f"⚠️ Not migrating {json_path}: could not read it ({e})")
            return 0
        if not isinstance(data, dict):
            print(f"⚠️ Not migrating {json_path}: top level is not a JSON object")
            return 0

        rows = [self._to_row(vid, entry) for vid, entry in data.items() if isinstance(entry, dict)]
        skipped = len(data) - len(rows)

        with self._lock:
            # BEGIN IMMEDIATE takes the write lock, so two processes starting at
            # once cannot both import; re-check emptiness inside the transaction.
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
                if existing:
                    self._conn.execute("ROLLBACK")
                    print(f"⚠️ Not migrating {json_path}: {self.db_path} already holds {existing} summaries")
                    return 0
                self._conn.executemany(_UPSERT_SQL, rows)
                self._conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    (_MIGRATED_KEY, datetime.now(timezone.utc).isoformat()),
                )
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

        print(
            f"✅ Migrated {len(rows)} summaries from {json_path} to {self.db_path}"
            f" (skipped {skipped} non-object entries)"
        )
        _rename_migrated(json_path)
        return len(rows)


def _rename_migrated(json_path):
    """Rename ``json_path`` to ``json_path.migrated`` without overwriting an older one.

    A failed rename is reported but not fatal: the migration marker makes the
    next start retry it.
    """
    target = json_path + ".migrated"
    n = 1
    while os.path.exists(target):
        target = f"{json_path}.migrated.{n}"
        n += 1
    try:
        os.rename(json_path, target)
    except OSError as e:
        print(f"⚠️ Could not rename migrated {json_path}: {e}")
        return None
    print(f"   Original summary cache kept as {target}")
    return target


def open_summary_cache(db_path, json_path=None, testing=False):
    """Open the summary store, migrating ``json_path`` into it on first use.

    Under ``testing`` an in-memory database is used and no files are touched.
    """
    if testing:
        return SummaryCache(":memory:")
    store = SummaryCache(db_path)
    if json_path:
        store.migrate_from_json(json_path)
    return store


def _summary_sort_key(item):
    value = item[1].get("summarized_at")
    return (value is not None, value if value is not None else "")


def list_summary_entries(cache, offset=0, limit=None):
    """Return ``(total, [(video_id, entry), ...])`` newest first, for a SummaryCache or a plain dict."""
    if isinstance(cache, SummaryCache):
        return cache.count(), cache.list_page(offset, limit)
    ordered = sorted(cache.items(), key=_summary_sort_key, reverse=True)
    end = None if limit is None else offset + max(limit, 0)
    return len(ordered), ordered[offset:end]


def search_summary_entries(cache, query):
    """Case-insensitive substring search on title/summary, newest first, for either cache type."""
    if isinstance(cache, SummaryCache):
        return cache.search(query)
    needle = query.lower()
    matches = [
        (video_id, d)
        for video_id, d in cache.items()
        if needle in (d.get("title") or "").lower() or needle in (d.get("summary") or "").lower()
    ]
    return sorted(matches, key=_summary_sort_key, reverse=True)
