"""Tests for background summary requests: POST /summarize/start and GET /summarize/<id>."""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

import summary_jobs
from app import app

VIDEO_A = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
VIDEO_B = "https://www.youtube.com/watch?v=bbbbbbbbbbb"
VIDEO_C = "https://www.youtube.com/watch?v=ccccccccccc"
PLAYLIST = "https://www.youtube.com/playlist?list=PLtestplaylist0001"


def fake_details(ids):
    return {i: {"title": f"Title {i}", "thumbnail_url": f"http://example.com/{i}.jpg"} for i in ids}


def fake_transcript(video_id):
    return f"transcript {video_id}", None


def fake_summary(transcript, title, model_key):
    return f"summary of {title} ({model_key})", None


def playlist_item(video_id, title):
    return {"snippet": {"resourceId": {"videoId": video_id}, "title": title, "thumbnails": {}}}


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class BackgroundSummaryTestCase(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        os.environ["TESTING"] = "true"
        self.client = app.test_client()
        self.clock = FakeClock()
        self.store = summary_jobs.RequestStore(ttl_seconds=3600, max_requests=50, max_active_per_session=3,
                                               clock=self.clock)
        self.executor = summary_jobs.SummaryExecutor(synchronous=True)
        self.broadcasts = []
        patches = [
            patch.object(summary_jobs, "store", self.store),
            patch.object(summary_jobs, "executor", self.executor),
            patch("app.summary_cache", {}),
            patch("app.save_summary_cache"),
            patch("app.get_video_details", side_effect=fake_details),
            patch("app.get_transcript", side_effect=fake_transcript),
            patch("app.generate_summary", side_effect=fake_summary),
            patch("app.sse.broadcast", side_effect=lambda event, data, **kw: self.broadcasts.append((event, data, kw))),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        os.environ.pop("TESTING", None)

    def start(self, urls, client=None, **body):
        body = dict(body, urls=urls)
        return (client or self.client).post("/summarize/start", json=body)

    def events(self, name):
        return [data for event, data, _ in self.broadcasts if event == name]


class TestStartAndStatus(BackgroundSummaryTestCase):
    def test_start_returns_202_and_results_are_retrievable(self):
        response = self.start([VIDEO_A, VIDEO_B], model="gpt-6-luna")
        self.assertEqual(response.status_code, 202)
        body = response.get_json()
        request_id = body["request_id"]
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["status_url"], f"/summarize/{request_id}")

        status = self.client.get(f"/summarize/{request_id}")
        self.assertEqual(status.status_code, 200)
        state = status.get_json()
        self.assertEqual(state["status"], "completed")
        self.assertTrue(state["done"])
        self.assertIsNone(state["error"])
        self.assertEqual(state["model"], "gpt-6-luna")
        self.assertEqual([r["video_id"] for r in state["results"]], ["aaaaaaaaaaa", "bbbbbbbbbbb"])
        self.assertEqual(state["results"][0]["summary"], "summary of Title aaaaaaaaaaa (gpt-6-luna)")
        self.assertEqual([i["seq"] for i in state["items"]], [0, 1])
        self.assertEqual([i["index"] for i in state["items"]], [0, 1])
        self.assertTrue(all(i["kind"] == "item" for i in state["items"]))

    def test_background_results_match_sync_endpoint(self):
        request_id = self.start([VIDEO_A, "not a url"]).get_json()["request_id"]
        background = self.client.get(f"/summarize/{request_id}").get_json()["results"]
        with patch("app.summary_cache", {}):
            sync = self.client.post("/summarize", json={"urls": [VIDEO_A, "not a url"]}).get_json()
        self.assertEqual(background, sync)

    def test_results_are_pushed_over_sse_with_a_final_done_event(self):
        request_id = self.start([VIDEO_A, VIDEO_B]).get_json()["request_id"]

        results = self.events("summary_result")
        self.assertEqual([r["seq"] for r in results], [0, 1])
        self.assertTrue(all(r["request_id"] == request_id for r in results))
        self.assertEqual(results[1]["item"]["video_id"], "bbbbbbbbbbb")

        done = self.events("summary_done")
        self.assertEqual(done, [{"request_id": request_id, "status": "completed", "error": None, "results_count": 2}])
        # Every broadcast is scoped to the requesting session
        with self.client.session_transaction() as sess:
            session_id = sess["session_id"]
        self.assertTrue(all(kw["session_filter"] == session_id for _, _, kw in self.broadcasts))
        # The existing progress events are still sent
        self.assertEqual(self.events("summary_progress")[-1]["status"], "completed")

    @patch("app.get_videos_from_playlist")
    @patch("app.youtube")
    def test_playlist_videos_are_streamed_individually(self, mock_youtube, mock_get_videos):
        mock_youtube.playlists.return_value.list.return_value.execute.return_value = {
            "items": [{"snippet": {"title": "My Playlist"}}]
        }
        mock_get_videos.return_value = (
            [playlist_item("ppppppppp01", "One"), playlist_item("ppppppppp02", "Private video")],
            None,
        )
        request_id = self.start([PLAYLIST, VIDEO_A]).get_json()["request_id"]
        state = self.client.get(f"/summarize/{request_id}").get_json()

        kinds = [(i["index"], i["kind"]) for i in state["items"]]
        self.assertEqual(kinds, [(0, "playlist"), (0, "playlist_video"), (0, "playlist_video"), (1, "item")])
        self.assertEqual(state["items"][1]["playlist_title"], "My Playlist")
        self.assertEqual(state["items"][2]["item"]["error"], "Video is private or deleted.")
        playlist = state["results"][0]
        self.assertEqual(playlist["type"], "playlist")
        self.assertEqual([v["video_id"] for v in playlist["summaries"]], ["ppppppppp01", "ppppppppp02"])

    def test_partial_results_are_visible_while_running(self):
        """The store builds /summarize-shaped results from items as they arrive."""
        request_id = self.store.create("s1", [PLAYLIST, VIDEO_A], "gemini-2.5-flash")
        self.store.mark_running(request_id)
        self.store.add_item(request_id, {"index": 0, "kind": "playlist",
                                         "item": {"type": "playlist", "title": "P", "summaries": []}})
        self.store.add_item(request_id, {"index": 0, "kind": "playlist_video", "playlist_title": "P",
                                         "item": {"video_id": "v1", "summary": "s"}})
        state = self.store.get(request_id, "s1")
        self.assertEqual(state["status"], "running")
        self.assertFalse(state["done"])
        self.assertEqual(state["results"], [{"type": "playlist", "title": "P", "summaries": [{"video_id": "v1",
                                                                                              "summary": "s"}]}])
        # Snapshots are copies
        state["results"][0]["summaries"].append("x")
        self.assertEqual(len(self.store.get(request_id, "s1")["results"][0]["summaries"]), 1)


class TestValidationAndLimits(BackgroundSummaryTestCase):
    def test_start_validates_like_summarize(self):
        self.assertEqual(self.start([]).status_code, 400)
        self.assertEqual(self.start("https://youtu.be/aaaaaaaaaaa").status_code, 400)
        bad_model = self.start([VIDEO_A], model="nope")
        self.assertEqual(bad_model.status_code, 400)
        self.assertIn("Unsupported model", bad_model.get_json()["error"])
        # Non-JSON content types are rejected by the CSRF guard before validation
        not_json = self.client.post("/summarize/start", data="x", content_type="text/plain")
        self.assertEqual(not_json.status_code, 415)
        malformed = self.client.post("/summarize/start", data="{not json", content_type="application/json")
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(len(self.store), 0)

    def test_too_many_active_requests_returns_429(self):
        with self.client.session_transaction() as sess:
            sess["session_id"] = "busy-session"
        for _ in range(3):
            self.store.create("busy-session", [VIDEO_A], "gemini-2.5-flash")
        response = self.start([VIDEO_A])
        self.assertEqual(response.status_code, 429)
        self.assertIn("error", response.get_json())
        # Another session is unaffected
        self.assertEqual(self.start([VIDEO_A], client=app.test_client()).status_code, 202)

    def test_store_evicts_oldest_finished_request_at_capacity(self):
        store = summary_jobs.RequestStore(max_requests=2, clock=self.clock)
        first = store.create("s", [VIDEO_A], "m")
        store.finish(first, results=[])
        self.clock.now += 1
        second = store.create("s", [VIDEO_A], "m")
        store.finish(second, results=[])
        third = store.create("s", [VIDEO_A], "m")
        self.assertIsNone(store.get(first, "s"))
        self.assertIsNotNone(store.get(second, "s"))
        self.assertIsNotNone(store.get(third, "s"))

    def test_store_refuses_when_full_of_running_requests(self):
        store = summary_jobs.RequestStore(max_requests=1, max_active_per_session=5, clock=self.clock)
        store.create("s", [VIDEO_A], "m")
        with self.assertRaises(summary_jobs.StoreFullError):
            store.create("other", [VIDEO_A], "m")


class TestSessionIsolation(BackgroundSummaryTestCase):
    def test_other_session_gets_404(self):
        request_id = self.start([VIDEO_A]).get_json()["request_id"]
        self.assertEqual(self.client.get(f"/summarize/{request_id}").status_code, 200)

        other = app.test_client()
        response = other.get(f"/summarize/{request_id}")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("results", response.get_json())

    def test_unknown_request_id_gets_404(self):
        response = self.client.get("/summarize/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content_type, "application/json")


class TestTTLCleanup(BackgroundSummaryTestCase):
    def test_finished_requests_expire_after_ttl(self):
        request_id = self.start([VIDEO_A]).get_json()["request_id"]
        self.clock.now += 3599
        self.assertEqual(self.client.get(f"/summarize/{request_id}").status_code, 200)
        self.clock.now += 2
        self.assertEqual(self.client.get(f"/summarize/{request_id}").status_code, 404)
        self.assertEqual(len(self.store), 0)

    def test_abandoned_running_request_expires(self):
        request_id = self.store.create("s", [VIDEO_A], "m")
        self.store.mark_running(request_id)
        self.clock.now += 3601
        self.store.cleanup()
        self.assertIsNone(self.store.get(request_id, "s"))

    def test_active_request_is_kept_while_it_makes_progress(self):
        request_id = self.store.create("s", [VIDEO_A], "m")
        self.store.mark_running(request_id)
        for _ in range(3):
            self.clock.now += 3000
            self.store.add_item(request_id, {"index": 0, "kind": "item", "item": {"type": "video"}})
        self.assertIsNotNone(self.store.get(request_id, "s"))


class TestErrorIsolation(BackgroundSummaryTestCase):
    def test_error_in_one_url_does_not_stop_the_batch(self):
        def details(ids):
            if ids == ["bbbbbbbbbbb"]:
                raise RuntimeError("boom")
            return fake_details(ids)

        def transcript(video_id):
            if video_id == "ccccccccccc":
                return None, "No transcript"
            return fake_transcript(video_id)

        with patch("app.get_video_details", side_effect=details), patch("app.get_transcript", side_effect=transcript):
            request_id = self.start([VIDEO_A, VIDEO_B, "https://example.com/x", VIDEO_C, VIDEO_A]).get_json()[
                "request_id"]
        state = self.client.get(f"/summarize/{request_id}").get_json()

        self.assertEqual(state["status"], "completed")
        results = state["results"]
        self.assertEqual(len(results), 5)
        self.assertIsNone(results[0]["error"])
        self.assertIn("Failed to process video", results[1]["error"])
        self.assertEqual(results[2]["type"], "error")
        self.assertEqual(results[3]["error"], "No transcript")
        self.assertIsNone(results[4]["error"])
        self.assertEqual(len(state["items"]), 5)

    def test_unexpected_batch_failure_marks_request_failed(self):
        with patch("app._run_summary_batch", side_effect=RuntimeError("secret internal detail")):
            request_id = self.start([VIDEO_A]).get_json()["request_id"]
        state = self.client.get(f"/summarize/{request_id}").get_json()
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["done"])
        self.assertNotIn("secret internal detail", json.dumps(state))
        done = self.events("summary_done")[-1]
        self.assertEqual(done["status"], "failed")
        self.assertNotIn("secret internal detail", done["error"])


class TestThreadedExecutor(BackgroundSummaryTestCase):
    def test_runs_in_a_worker_thread(self):
        executor = summary_jobs.SummaryExecutor(max_workers=1)
        self.addCleanup(executor.shutdown)
        futures = []
        original_submit = executor.submit

        def recording_submit(*args, **kwargs):
            future = original_submit(*args, **kwargs)
            futures.append(future)
            return future

        executor.submit = recording_submit
        with patch.object(summary_jobs, "executor", executor):
            request_id = self.start([VIDEO_A, VIDEO_B]).get_json()["request_id"]
            futures[0].result(timeout=10)
        state = self.client.get(f"/summarize/{request_id}").get_json()
        self.assertEqual(state["status"], "completed")
        self.assertEqual(len(state["results"]), 2)

    def test_sync_executor_swallows_job_exceptions(self):
        future = summary_jobs.SummaryExecutor(synchronous=True).submit(MagicMock(side_effect=ValueError("x")))
        with self.assertRaises(ValueError):
            future.result()


if __name__ == "__main__":
    unittest.main()
