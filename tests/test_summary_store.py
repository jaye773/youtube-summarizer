"""Tests for the SQLite-backed SummaryCache in cache.py."""

import json
import os
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from cache import (
    SummaryCache,
    build_cache_entry,
    list_summary_entries,
    open_summary_cache,
    save_summary_cache,
    search_summary_entries,
)


def entry(title, summary="text", summarized_at="2024-01-01T00:00:00", **extra):
    data = {
        "title": title,
        "summary": summary,
        "thumbnail_url": f"http://example.com/{title}.jpg",
        "summarized_at": summarized_at,
        "audio_filename": None,
        "video_url": f"https://www.youtube.com/watch?v={title}",
        "model_used": "gemini-2.5-flash",
    }
    data.update(extra)
    return data


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "summaries.db")
        self.json_path = os.path.join(self.tmp, "summary_cache.json")
        self.stores = []

    def tearDown(self):
        for store in self.stores:
            store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def open(self, path=None):
        store = SummaryCache(path or self.db_path)
        self.stores.append(store)
        return store


class TestMappingSemantics(TempDirTestCase):
    def test_set_get_contains_len(self):
        cache = self.open()
        self.assertEqual(len(cache), 0)
        self.assertFalse(cache)
        cache["a"] = entry("A")
        self.assertIn("a", cache)
        self.assertNotIn("b", cache)
        self.assertEqual(len(cache), 1)
        self.assertTrue(cache)
        self.assertEqual(cache["a"], entry("A"))
        self.assertEqual(cache.get("a"), entry("A"))
        self.assertIsNone(cache.get("missing"))

    def test_missing_key_raises(self):
        cache = self.open()
        with self.assertRaises(KeyError):
            cache["nope"]
        with self.assertRaises(KeyError):
            del cache["nope"]

    def test_overwrite_and_delete(self):
        cache = self.open()
        cache["a"] = entry("A")
        cache["a"] = entry("A2", summary="new")
        self.assertEqual(len(cache), 1)
        self.assertEqual(cache["a"]["summary"], "new")
        del cache["a"]
        self.assertNotIn("a", cache)
        self.assertEqual(len(cache), 0)

    def test_iteration_items_values(self):
        cache = self.open()
        cache["a"] = entry("A")
        cache["b"] = entry("B")
        self.assertEqual(list(cache), ["a", "b"])
        self.assertEqual(dict(cache.items()), {"a": entry("A"), "b": entry("B")})
        self.assertEqual(cache.values(), [entry("A"), entry("B")])
        self.assertEqual(dict(cache), {"a": entry("A"), "b": entry("B")})

    def test_pop_update_clear(self):
        cache = self.open()
        cache.update({"a": entry("A"), "b": entry("B")})
        self.assertEqual(cache.pop("a"), entry("A"))
        self.assertEqual(list(cache), ["b"])
        cache.clear()
        self.assertEqual(len(cache), 0)

    def test_returned_entries_are_copies(self):
        cache = self.open()
        cache["a"] = entry("A")
        cache["a"]["title"] = "changed"
        self.assertEqual(cache["a"]["title"], "A")

    def test_build_cache_entry_round_trip(self):
        cache = self.open()
        e = build_cache_entry("T", "S", "http://t.jpg", "vid", "gpt-5", "x.mp3")
        cache["vid"] = e
        self.assertEqual(cache["vid"], e)

    def test_extra_fields_preserved(self):
        cache = self.open()
        e = entry("A", tags=["x", "y"], rating=4.5, nested={"k": "v"})
        cache["a"] = e
        self.assertEqual(cache["a"], e)

    def test_non_scalar_known_field_preserved(self):
        cache = self.open()
        e = entry("A", model_used={"provider": "google"})
        cache["a"] = e
        self.assertEqual(cache["a"], e)

    def test_missing_known_fields_read_back_as_none(self):
        cache = self.open()
        cache["a"] = {"title": "A", "summary": "S"}
        got = cache["a"]
        self.assertEqual(got["title"], "A")
        self.assertIsNone(got["thumbnail_url"])
        self.assertIsNone(got["summarized_at"])

    def test_rejects_non_dict_entries(self):
        cache = self.open()
        with self.assertRaises(TypeError):
            cache["a"] = "not a dict"

    def test_unicode(self):
        cache = self.open()
        e = entry("Ünïcödé 日本語 🎉", summary="Résumé — ñ, 中文, emoji 🚀")
        cache["ü"] = e
        self.assertEqual(cache["ü"], e)
        self.assertIn("ü", cache)

    def test_save_summary_cache_is_noop_for_store(self):
        cache = self.open()
        cache["a"] = entry("A")
        save_summary_cache(cache, self.json_path)
        self.assertFalse(os.path.exists(self.json_path))

    def test_save_summary_cache_still_writes_dicts(self):
        save_summary_cache({"a": entry("A")}, self.json_path)
        with open(self.json_path) as f:
            self.assertEqual(json.load(f), {"a": entry("A")})


class TestPersistence(TempDirTestCase):
    def test_persists_across_reopen(self):
        cache = self.open()
        cache["a"] = entry("A", extra_field="kept")
        cache["b"] = entry("B")
        del cache["b"]
        cache.close()
        self.stores.remove(cache)

        reopened = self.open()
        self.assertEqual(list(reopened), ["a"])
        self.assertEqual(reopened["a"]["extra_field"], "kept")

    def test_wal_mode(self):
        cache = self.open()
        mode = cache._query("PRAGMA journal_mode")[0][0]
        self.assertEqual(mode.lower(), "wal")

    def test_two_connections_see_each_others_writes(self):
        first = self.open()
        second = self.open()
        first["a"] = entry("A")
        self.assertIn("a", second)
        del second["a"]
        self.assertNotIn("a", first)

    def test_memory_store(self):
        cache = self.open(":memory:")
        cache["a"] = entry("A")
        self.assertEqual(len(cache), 1)
        self.assertEqual(os.listdir(self.tmp), [])


class TestConcurrency(TempDirTestCase):
    def test_concurrent_writes_from_threads(self):
        cache = self.open()
        errors = []

        def worker(n):
            try:
                for i in range(50):
                    key = f"t{n}-{i}"
                    cache[key] = entry(key)
                    self.assertIn(key, cache)
                    len(cache)
                    list(cache.items())
            except Exception as e:  # pragma: no cover - surfaced below
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(cache), 400)

    def test_concurrent_writes_from_separate_connections(self):
        stores = [self.open() for _ in range(4)]
        errors = []

        def worker(n):
            try:
                for i in range(25):
                    stores[n][f"c{n}-{i}"] = entry(f"c{n}-{i}")
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(stores[0]), 100)


class TestMigration(TempDirTestCase):
    def write_json(self, data):
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def test_migrates_and_renames(self):
        data = {
            "a": entry("A", custom="x"),
            "b": entry("Ünïcödé", summarized_at="2024-02-01T00:00:00"),
            "bad": "not an object",
        }
        self.write_json(data)

        store = open_summary_cache(self.db_path, self.json_path)
        self.stores.append(store)

        self.assertEqual(len(store), 2)
        self.assertEqual(store["a"], data["a"])
        self.assertEqual(store["b"], data["b"])
        self.assertFalse(os.path.exists(self.json_path))
        with open(self.json_path + ".migrated", encoding="utf-8") as f:
            self.assertEqual(json.load(f), data)

    def test_idempotent(self):
        self.write_json({"a": entry("A")})
        store = self.open()
        self.assertEqual(store.migrate_from_json(self.json_path), 1)
        self.assertEqual(store.migrate_from_json(self.json_path), 0)  # JSON gone
        store["b"] = entry("B")

        # A new JSON appearing later does not clobber or merge into the database
        self.write_json({"c": entry("C")})
        self.assertEqual(store.migrate_from_json(self.json_path), 0)
        self.assertEqual(sorted(store), ["a", "b"])

    def test_does_not_import_into_non_empty_db(self):
        store = self.open()
        store["existing"] = entry("E")
        self.write_json({"a": entry("A")})
        self.assertEqual(store.migrate_from_json(self.json_path), 0)
        self.assertEqual(list(store), ["existing"])
        self.assertTrue(os.path.exists(self.json_path))

    def test_finishes_rename_after_interrupted_migration(self):
        self.write_json({"a": entry("A")})
        store = self.open()
        with patch("cache.os.rename", side_effect=OSError("simulated crash")):
            self.assertEqual(store.migrate_from_json(self.json_path), 1)
        self.assertTrue(os.path.exists(self.json_path))

        # Next start: rows are already committed, so only the rename happens
        self.assertEqual(store.migrate_from_json(self.json_path), 0)
        self.assertFalse(os.path.exists(self.json_path))
        self.assertTrue(os.path.exists(self.json_path + ".migrated"))
        self.assertEqual(list(store), ["a"])

    def test_failed_import_rolls_back(self):
        self.write_json({"a": entry("A"), "b": entry("B")})
        store = self.open()
        with patch.object(store, "_conn", wraps=store._conn) as conn:
            conn.executemany.side_effect = RuntimeError("boom")
            with self.assertRaises(RuntimeError):
                store.migrate_from_json(self.json_path)
        self.assertEqual(len(store), 0)
        self.assertTrue(os.path.exists(self.json_path))
        self.assertEqual(store.migrate_from_json(self.json_path), 2)

    def test_does_not_overwrite_existing_migrated_file(self):
        with open(self.json_path + ".migrated", "w") as f:
            f.write("older")
        self.write_json({"a": entry("A")})
        self.open().migrate_from_json(self.json_path)
        with open(self.json_path + ".migrated") as f:
            self.assertEqual(f.read(), "older")
        self.assertTrue(os.path.exists(self.json_path + ".migrated.1"))

    def test_invalid_json_left_alone(self):
        with open(self.json_path, "w") as f:
            f.write("{not json")
        store = self.open()
        self.assertEqual(store.migrate_from_json(self.json_path), 0)
        self.assertTrue(os.path.exists(self.json_path))
        self.assertEqual(len(store), 0)

    def test_no_json_is_fine(self):
        self.assertEqual(self.open().migrate_from_json(self.json_path), 0)

    def test_testing_mode_touches_no_files(self):
        self.write_json({"a": entry("A")})
        store = open_summary_cache(self.db_path, self.json_path, testing=True)
        self.stores.append(store)
        self.assertEqual(len(store), 0)
        self.assertEqual(os.listdir(self.tmp), ["summary_cache.json"])


class TestListingAndSearch(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.data = {
            "old": entry("Old Python talk", summary="About snakes", summarized_at="2024-01-01T00:00:00"),
            "new": entry("New Rust talk", summary="Crabs and python bindings", summarized_at="2024-03-01T00:00:00"),
            "mid": entry("Café Ünïcode", summary="ÉCLAIR recipes", summarized_at="2024-02-01T00:00:00"),
            "tie": entry("Tie", summary="same time", summarized_at="2024-02-01T00:00:00"),
            "nodate": {"title": "No date", "summary": "Missing timestamp", "thumbnail_url": None},
        }
        self.store = self.open()
        for k, v in self.data.items():
            self.store[k] = v

    def keys(self, pairs):
        return [k for k, _ in pairs]

    def test_list_page_order(self):
        self.assertEqual(self.keys(self.store.list_page()), ["new", "mid", "tie", "old", "nodate"])

    def test_list_page_offset_limit(self):
        self.assertEqual(self.keys(self.store.list_page(1, 2)), ["mid", "tie"])
        self.assertEqual(self.keys(self.store.list_page(4, 10)), ["nodate"])
        self.assertEqual(self.store.list_page(10, 10), [])
        self.assertEqual(self.store.list_page(0, 0), [])
        self.assertEqual(self.store.count(), 5)

    def test_overwrite_keeps_position_for_ties(self):
        self.store["mid"] = self.data["mid"]
        self.assertEqual(self.keys(self.store.list_page()), ["new", "mid", "tie", "old", "nodate"])

    def test_dict_and_store_agree(self):
        for offset, limit in [(0, None), (0, 2), (2, 2), (3, 10)]:
            self.assertEqual(
                list_summary_entries(self.store, offset, limit),
                list_summary_entries(dict(self.store.items()), offset, limit),
            )
        for q in ["python", "PYTHON", "éclair", "Ünï", "café", "talk", "zzz", "%", "_"]:
            self.assertEqual(
                search_summary_entries(self.store, q),
                search_summary_entries(dict(self.store.items()), q),
                q,
            )

    def test_search_case_insensitive_title_and_summary(self):
        self.assertEqual(self.keys(self.store.search("PYTHON")), ["new", "old"])
        self.assertEqual(self.keys(self.store.search("crabs")), ["new"])

    def test_search_unicode_case_folding(self):
        self.assertEqual(self.keys(self.store.search("éclair")), ["mid"])
        self.assertEqual(self.keys(self.store.search("ÜNÏCODE")), ["mid"])

    def test_search_treats_wildcards_literally(self):
        self.assertEqual(self.store.search("%"), [])
        self.assertEqual(self.store.search("_"), [])
        self.store["pct"] = entry("100% done")
        self.assertEqual(self.keys(self.store.search("100%")), ["pct"])


class TestRoutesWithStore(unittest.TestCase):
    """The two listing routes produce the same responses from a SummaryCache as from a dict."""

    def setUp(self):
        from app import app

        app.config["TESTING"] = True
        self.client = app.test_client()
        login_patch = patch("app.LOGIN_ENABLED", False)
        login_patch.start()
        self.addCleanup(login_patch.stop)
        self.data = {
            f"v{i}": entry(f"Video {i}", summary=f"Summary {i}", summarized_at=f"2024-01-{i + 1:02d}T00:00:00")
            for i in range(25)
        }
        self.store = SummaryCache(":memory:")
        for k, v in self.data.items():
            self.store[k] = v

    def tearDown(self):
        self.store.close()

    def get_both(self, url):
        with patch("app.summary_cache", self.store):
            from_store = self.client.get(url)
        with patch("app.summary_cache", dict(self.data)):
            from_dict = self.client.get(url)
        self.assertEqual(from_store.status_code, from_dict.status_code)
        self.assertEqual(from_store.get_json(), from_dict.get_json())
        return from_store.get_json()

    def test_legacy_list(self):
        body = self.get_both("/get_cached_summaries")
        self.assertEqual(len(body), 25)
        self.assertEqual(body[0]["video_id"], "v24")
        expected_keys = {"type", "video_id", "title", "thumbnail_url", "summary", "summarized_at", "video_url", "error"}
        self.assertEqual(set(body[0]), expected_keys)

    def test_legacy_limit(self):
        self.assertEqual(len(self.get_both("/get_cached_summaries?limit=3")), 3)
        self.assertEqual(self.get_both("/get_cached_summaries?limit=0"), [])
        self.assertEqual(len(self.get_both("/get_cached_summaries?limit=-1")), 25)
        self.assertEqual(len(self.get_both("/get_cached_summaries?limit=5&page=2")), 5)

    def test_pagination(self):
        body = self.get_both("/get_cached_summaries?page=3&per_page=10")
        self.assertEqual(body["total"], 25)
        self.assertEqual(body["total_pages"], 3)
        self.assertEqual([s["video_id"] for s in body["summaries"]], ["v4", "v3", "v2", "v1", "v0"])
        self.get_both("/get_cached_summaries?page=0&per_page=500")
        self.get_both("/get_cached_summaries?page=99")

    def test_empty(self):
        self.store.clear()
        self.data = {}
        self.assertEqual(self.get_both("/get_cached_summaries"), [])
        self.assertEqual(self.get_both("/get_cached_summaries?page=1")["total"], 0)
        self.assertEqual(self.get_both("/search_summaries?q=video"), [])

    def test_search(self):
        body = self.get_both("/search_summaries?q=SUMMARY%201")
        self.assertEqual([r["video_id"] for r in body][:2], ["v19", "v18"])
        self.assertEqual(self.get_both("/search_summaries?q=nothing"), [])


if __name__ == "__main__":
    unittest.main()
