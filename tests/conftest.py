"""Shared pytest setup.

Point DATA_DIR at a throwaway directory before any test imports ``app``, so
tests never read or write the developer's real data (summary database, audio
cache, settings .env). Some tests delete TESTING and reload ``app``; without
this, that reload would open (and migrate into) a database in the repo root.
"""

import atexit
import os
import shutil
import tempfile

if "DATA_DIR" not in os.environ:
    _data_dir = tempfile.mkdtemp(prefix="yt-summarizer-test-data-")
    os.environ["DATA_DIR"] = _data_dir
    atexit.register(shutil.rmtree, _data_dir, ignore_errors=True)
