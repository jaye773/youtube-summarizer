import json
import os
import unittest
from unittest.mock import MagicMock, mock_open, patch

from app import app, clean_youtube_url, get_playlist_id, get_video_id


class TestYouTubeSummarizer(unittest.TestCase):
    """Test suite for YouTube Summarizer Flask application"""

    def setUp(self):
        """Set up test client and test data"""
        self.app = app
        self.client = self.app.test_client()
        self.app.config["TESTING"] = True
        # Set environment variable to bypass authentication during testing
        os.environ["TESTING"] = "true"

        # Sample test data
        self.test_video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.test_playlist_url = "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        self.test_video_id = "dQw4w9WgXcQ"
        self.test_playlist_id = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"

    def tearDown(self):
        """Clean up after each test"""
        # Remove testing environment variable
        if "TESTING" in os.environ:
            del os.environ["TESTING"]

    def test_home_page(self):
        """Test that home page loads successfully"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    @patch("app.LOGIN_ENABLED", True)
    def test_home_page_requires_auth_when_enabled(self):
        """Test that home page redirects to login when authentication is enabled and user not logged in"""
        # Remove testing environment variable to enable authentication
        if "TESTING" in os.environ:
            del os.environ["TESTING"]

        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)  # Redirect
        self.assertIn("/login", response.location)

    @patch("app.LOGIN_ENABLED", True)
    def test_home_page_accessible_when_authenticated(self):
        """Test that home page is accessible when user is authenticated"""
        # Remove testing environment variable to enable authentication
        if "TESTING" in os.environ:
            del os.environ["TESTING"]

        # First login
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_get_cached_summaries_empty(self):
        """Test getting cached summaries when cache is empty"""
        with patch("app.summary_cache", {}):
            response = self.client.get("/get_cached_summaries")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(json.loads(response.data), [])

    def test_get_cached_summaries_with_data(self):
        """Test getting cached summaries with data"""
        mock_cache = {
            "video1": {
                "title": "Test Video",
                "thumbnail_url": "http://example.com/thumb.jpg",
                "summary": "Test summary",
                "summarized_at": "2024-01-01T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video1",
            }
        }
        with patch("app.summary_cache", mock_cache):
            response = self.client.get("/get_cached_summaries")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["title"], "Test Video")
            self.assertEqual(data[0]["video_url"], "https://www.youtube.com/watch?v=video1")
            self.assertEqual(data[0]["video_id"], "video1")  # Verify video_id is included

    def test_summarize_no_urls(self):
        """Test summarize endpoint with no URLs provided"""
        response = self.client.post("/summarize", data=json.dumps({"urls": []}), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn("error", data)

    @patch("app.summary_cache", {})  # Clear the cache for this test
    @patch("app.generate_summary")
    @patch("app.get_transcript")
    @patch("app.get_video_details")
    @patch("app.youtube")
    def test_summarize_single_video(
        self, mock_youtube, mock_get_video_details, mock_get_transcript, mock_generate_summary
    ):
        """Test summarizing a single video"""
        # Mock the functions
        mock_get_video_details.return_value = {
            self.test_video_id: {"title": "Test Video Title", "thumbnail_url": "http://example.com/thumb.jpg"}
        }
        mock_get_transcript.return_value = ("This is a test transcript", None)
        mock_generate_summary.return_value = ("This is a test summary", None)

        # Make youtube non-None for the check
        mock_youtube.return_value = MagicMock()

        response = self.client.post(
            "/summarize", data=json.dumps({"urls": [self.test_video_url]}), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["type"], "video")
        self.assertEqual(data[0]["title"], "Test Video Title")
        self.assertEqual(data[0]["summary"], "This is a test summary")
        self.assertEqual(data[0]["video_url"], f"https://www.youtube.com/watch?v={self.test_video_id}")

    @patch("app.summary_cache", {})  # Clear the cache for this test
    @patch("app.get_transcript")
    @patch("app.youtube")
    def test_summarize_video_no_transcript(self, mock_youtube, mock_get_transcript):
        """Test summarizing a video with no transcript available"""
        mock_get_transcript.return_value = (None, "No transcripts are available for this video.")

        # Make youtube non-None for the check
        mock_youtube.return_value = MagicMock()

        with patch("app.get_video_details") as mock_details:
            mock_details.return_value = {
                self.test_video_id: {"title": "Test Video", "thumbnail_url": "http://example.com/thumb.jpg"}
            }

            response = self.client.post(
                "/summarize", data=json.dumps({"urls": [self.test_video_url]}), content_type="application/json"
            )

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            # Check that there's an error (the specific message might vary)
            self.assertIn("error", data[0])
            self.assertEqual(data[0]["error"], "No transcripts are available for this video.")
            self.assertEqual(data[0]["video_url"], f"https://www.youtube.com/watch?v={self.test_video_id}")

    def test_speak_no_text(self):
        """Test speak endpoint with no text provided"""
        response = self.client.post("/speak", data=json.dumps({}), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data=b"fake audio content")
    def test_speak_cached_audio(self, mock_file, mock_exists):
        """Test speak endpoint with cached audio file"""
        mock_exists.return_value = True

        response = self.client.post("/speak", data=json.dumps({"text": "Test text"}), content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "audio/mpeg")

    @patch("app.tts_client")
    @patch("os.path.exists")
    def test_speak_generate_new_audio(self, mock_exists, mock_tts_client):
        """Test speak endpoint generating new audio"""
        mock_exists.return_value = False

        # Mock TTS response
        mock_response = MagicMock()
        mock_response.audio_content = b"generated audio content"
        mock_tts_client.synthesize_speech.return_value = mock_response

        with patch("builtins.open", mock_open()) as mock_file:
            response = self.client.post(
                "/speak", data=json.dumps({"text": "Test text"}), content_type="application/json"
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, "audio/mpeg")
            # Verify file was written
            mock_file().write.assert_called_with(b"generated audio content")

    @patch("app.summary_cache", {})  # Clear the cache for this test
    @patch("app.generate_summary")
    @patch("app.get_transcript")
    @patch("app.get_video_details")
    @patch("app.youtube")
    def test_video_url_in_response(
        self, mock_youtube, mock_get_video_details, mock_get_transcript, mock_generate_summary
    ):
        """Test that video URL is included in API responses"""
        # Mock the functions
        mock_get_video_details.return_value = {
            self.test_video_id: {"title": "Test Video", "thumbnail_url": "http://example.com/thumb.jpg"}
        }
        mock_get_transcript.return_value = ("Test transcript", None)
        mock_generate_summary.return_value = ("Test summary", None)
        mock_youtube.return_value = MagicMock()

        response = self.client.post(
            "/summarize", data=json.dumps({"urls": [self.test_video_url]}), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["type"], "video")
        self.assertIn("video_url", data[0])
        self.assertEqual(data[0]["video_url"], f"https://www.youtube.com/watch?v={self.test_video_id}")

    def test_get_cached_summaries_with_missing_video_url(self):
        """Test getting cached summaries when video_url is missing from cache (backward compatibility)"""
        mock_cache = {
            "video1": {
                "title": "Test Video",
                "thumbnail_url": "http://example.com/thumb.jpg",
                "summary": "Test summary",
                "summarized_at": "2024-01-01T00:00:00.000000",
                # Note: no video_url field to test backward compatibility
            }
        }
        with patch("app.summary_cache", mock_cache):
            response = self.client.get("/get_cached_summaries")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["title"], "Test Video")
            self.assertIsNone(data[0]["video_url"])

    def test_get_cached_summaries_with_limit(self):
        """Test getting cached summaries with limit parameter"""
        mock_cache = {
            "video1": {
                "title": "Video 1",
                "thumbnail_url": "http://example.com/thumb1.jpg",
                "summary": "Summary 1",
                "summarized_at": "2024-01-01T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video1",
            },
            "video2": {
                "title": "Video 2",
                "thumbnail_url": "http://example.com/thumb2.jpg",
                "summary": "Summary 2",
                "summarized_at": "2024-01-02T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video2",
            },
            "video3": {
                "title": "Video 3",
                "thumbnail_url": "http://example.com/thumb3.jpg",
                "summary": "Summary 3",
                "summarized_at": "2024-01-03T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video3",
            },
        }
        with patch("app.summary_cache", mock_cache):
            # Test with limit of 2
            response = self.client.get("/get_cached_summaries?limit=2")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 2)
            # Should be sorted by date (most recent first)
            self.assertEqual(data[0]["title"], "Video 3")
            self.assertEqual(data[1]["title"], "Video 2")

    def test_get_cached_summaries_with_limit_5(self):
        """Test getting cached summaries with limit of 5 (initial page load scenario)"""
        # Create 7 videos to test that only 5 are returned
        mock_cache = {}
        for i in range(1, 8):  # videos 1-7
            mock_cache[f"video{i}"] = {
                "title": f"Video {i}",
                "thumbnail_url": f"http://example.com/thumb{i}.jpg",
                "summary": f"Summary {i}",
                "summarized_at": f"2024-01-{i:02d}T00:00:00.000000",
                "video_url": f"https://www.youtube.com/watch?v=video{i}",
            }

        with patch("app.summary_cache", mock_cache):
            # Test with limit of 5
            response = self.client.get("/get_cached_summaries?limit=5")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 5)
            # Should be the 5 most recent (videos 7, 6, 5, 4, 3)
            expected_titles = ["Video 7", "Video 6", "Video 5", "Video 4", "Video 3"]
            actual_titles = [item["title"] for item in data]
            self.assertEqual(actual_titles, expected_titles)

    def test_get_cached_summaries_with_invalid_limit(self):
        """Test getting cached summaries with invalid limit parameter"""
        mock_cache = {
            "video1": {
                "title": "Video 1",
                "thumbnail_url": "http://example.com/thumb1.jpg",
                "summary": "Summary 1",
                "summarized_at": "2024-01-01T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video1",
            }
        }
        with patch("app.summary_cache", mock_cache):
            # Test with zero limit (should return empty)
            response = self.client.get("/get_cached_summaries?limit=0")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 0)

            # Test with negative limit (should return all, ignoring the limit)
            response = self.client.get("/get_cached_summaries?limit=-1")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 1)

            # Test with non-integer limit (should be ignored)
            response = self.client.get("/get_cached_summaries?limit=abc")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 1)

    def test_get_cached_summaries_without_limit(self):
        """Test getting cached summaries without limit parameter (should return all)"""
        mock_cache = {
            "video1": {
                "title": "Video 1",
                "thumbnail_url": "http://example.com/thumb1.jpg",
                "summary": "Summary 1",
                "summarized_at": "2024-01-01T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video1",
            },
            "video2": {
                "title": "Video 2",
                "thumbnail_url": "http://example.com/thumb2.jpg",
                "summary": "Summary 2",
                "summarized_at": "2024-01-02T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video2",
            },
        }
        with patch("app.summary_cache", mock_cache):
            # Test without limit parameter (should return all)
            response = self.client.get("/get_cached_summaries")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 2)

    def test_speak_endpoint_invalid_json(self):
        """Test speak endpoint with invalid JSON"""
        response = self.client.post("/speak", data="invalid json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_speak_endpoint_no_text(self):
        """Test speak endpoint with no text"""
        response = self.client.post("/speak", data=json.dumps({}), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    # --- SEARCH FUNCTIONALITY TESTS ---
    def test_search_summaries_no_query(self):
        """Test search endpoint with no query parameter"""
        response = self.client.get("/search_summaries")
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn("error", data)

    def test_search_summaries_empty_query(self):
        """Test search endpoint with empty query"""
        response = self.client.get("/search_summaries?q=")
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn("error", data)

    def test_search_summaries_empty_cache(self):
        """Test search when cache is empty"""
        with patch("app.summary_cache", {}):
            response = self.client.get("/search_summaries?q=test")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data, [])

    def test_search_summaries_by_title(self):
        """Test searching summaries by title"""
        mock_cache = {
            "video1": {
                "title": "Python Programming Tutorial",
                "summary": "Learn the basics of web development",
                "thumbnail_url": "http://example.com/thumb1.jpg",
                "summarized_at": "2024-01-01T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video1",
            },
            "video2": {
                "title": "JavaScript Fundamentals",
                "summary": "Master Python programming concepts",
                "thumbnail_url": "http://example.com/thumb2.jpg",
                "summarized_at": "2024-01-02T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video2",
            },
        }

        with patch("app.summary_cache", mock_cache):
            response = self.client.get("/search_summaries?q=python")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 2)  # Should match both title and summary
            # Verify most recent first
            self.assertEqual(data[0]["video_id"], "video2")
            self.assertEqual(data[1]["video_id"], "video1")

    def test_search_summaries_by_content(self):
        """Test searching summaries by content"""
        mock_cache = {
            "video1": {
                "title": "Tutorial Video",
                "summary": "This video covers machine learning algorithms",
                "thumbnail_url": "http://example.com/thumb1.jpg",
                "summarized_at": "2024-01-01T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video1",
            },
            "video2": {
                "title": "Another Video",
                "summary": "Basic programming concepts explained",
                "thumbnail_url": "http://example.com/thumb2.jpg",
                "summarized_at": "2024-01-02T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video2",
            },
        }

        with patch("app.summary_cache", mock_cache):
            response = self.client.get("/search_summaries?q=machine%20learning")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["video_id"], "video1")

    def test_search_summaries_case_insensitive(self):
        """Test that search is case insensitive"""
        mock_cache = {
            "video1": {
                "title": "Python PROGRAMMING Tutorial",
                "summary": "Learn the basics of WEB development",
                "thumbnail_url": "http://example.com/thumb1.jpg",
                "summarized_at": "2024-01-01T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video1",
            }
        }

        with patch("app.summary_cache", mock_cache):
            # Test lowercase search on uppercase content
            response = self.client.get("/search_summaries?q=python")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 1)

            # Test uppercase search on mixed case content
            response = self.client.get("/search_summaries?q=WEB")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 1)

    def test_search_summaries_no_results(self):
        """Test search with no matching results"""
        mock_cache = {
            "video1": {
                "title": "Python Tutorial",
                "summary": "Learn programming",
                "thumbnail_url": "http://example.com/thumb1.jpg",
                "summarized_at": "2024-01-01T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video1",
            }
        }

        with patch("app.summary_cache", mock_cache):
            response = self.client.get("/search_summaries?q=nonexistent")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 0)

    def test_search_summaries_special_characters(self):
        """Test search with special characters and spaces"""
        mock_cache = {
            "video1": {
                "title": "React.js & Node.js",
                "summary": "Full-stack development tutorial",
                "thumbnail_url": "http://example.com/thumb1.jpg",
                "summarized_at": "2024-01-01T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video1",
            }
        }

        with patch("app.summary_cache", mock_cache):
            response = self.client.get("/search_summaries?q=react.js")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 1)

            response = self.client.get("/search_summaries?q=full-stack")
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 1)

    # --- NEW ENDPOINT TESTS ---
    def test_api_status_endpoint(self):
        """Test the API status endpoint"""
        response = self.client.get("/api_status")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        # Check that all expected keys are present
        expected_keys = [
            "google_api_key_set",
            "youtube_client_initialized",
            "tts_client_initialized",
            "ai_model_initialized",
            "testing_mode",
        ]
        for key in expected_keys:
            self.assertIn(key, data)

    def test_debug_transcript_no_url(self):
        """Test debug transcript endpoint with no URL"""
        response = self.client.get("/debug_transcript")
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn("error", data)

    def test_debug_transcript_invalid_url(self):
        """Test debug transcript endpoint with invalid URL"""
        response = self.client.get("/debug_transcript?url=invalid_url")
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn("error", data)
        self.assertIn("Invalid YouTube URL", data["error"])

    @patch("app.get_video_details")
    @patch("app.get_transcript")
    def test_debug_transcript_valid_url(self, mock_get_transcript, mock_get_video_details):
        """Test debug transcript endpoint with valid URL"""
        mock_get_video_details.return_value = {
            "dQw4w9WgXcQ": {"title": "Test Video", "thumbnail_url": "http://example.com/thumb.jpg"}
        }
        mock_get_transcript.return_value = ("Test transcript", None)

        response = self.client.get("/debug_transcript?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertEqual(data["video_id"], "dQw4w9WgXcQ")
        self.assertEqual(data["video_title"], "Test Video")
        self.assertTrue(data["transcript_success"])
        self.assertEqual(data["transcript_length"], 15)  # Length of "Test transcript"

    # --- DELETE SUMMARY TESTS ---
    @patch("app.summary_cache", {})
    @patch("app.save_summary_cache")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_delete_summary_success(self, mock_remove, mock_exists, mock_save_cache):
        """Test successful deletion of a summary"""
        # Set up test data
        test_video_id = "test_video_123"
        test_cache = {
            test_video_id: {
                "title": "Test Video",
                "summary": "Test summary",
                "thumbnail_url": "http://example.com/thumb.jpg",
                "audio_filename": "test_audio.mp3",
                "summarized_at": "2023-01-01T00:00:00.000000",
                "video_url": f"https://www.youtube.com/watch?v={test_video_id}",
            }
        }

        with patch("app.summary_cache", test_cache):
            # Mock audio file exists and removal
            mock_exists.return_value = True

            response = self.client.delete(
                "/delete_summary", json={"video_id": test_video_id}, content_type="application/json"
            )

            # Check response
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data["success"])
            self.assertIn("deleted successfully", data["message"])

            # Verify cache was updated
            mock_save_cache.assert_called_once()

            # Verify audio file removal was attempted
            mock_remove.assert_called_once()

    @patch("app.summary_cache", {})
    def test_delete_summary_not_found(self):
        """Test deletion of non-existent summary"""
        response = self.client.delete(
            "/delete_summary", json={"video_id": "nonexistent_video"}, content_type="application/json"
        )

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "Summary not found")

    def test_delete_summary_missing_video_id(self):
        """Test deletion without video_id parameter"""
        response = self.client.delete("/delete_summary", json={}, content_type="application/json")

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "video_id is required")

    def test_delete_summary_invalid_json(self):
        """Test deletion with invalid JSON"""
        response = self.client.delete("/delete_summary", data="invalid json", content_type="application/json")

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "Invalid JSON in request body")

    @patch("app.summary_cache", {})
    @patch("app.save_summary_cache")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_delete_summary_without_audio_file(self, mock_remove, mock_exists, mock_save_cache):
        """Test deletion of summary without audio filename"""
        test_video_id = "test_video_no_audio"
        test_cache = {
            test_video_id: {
                "title": "Test Video",
                "summary": "Test summary",
                "thumbnail_url": "http://example.com/thumb.jpg",
                "summarized_at": "2023-01-01T00:00:00.000000",
                "video_url": f"https://www.youtube.com/watch?v={test_video_id}",
                # No audio_filename
            }
        }

        with patch("app.summary_cache", test_cache):
            response = self.client.delete(
                "/delete_summary", json={"video_id": test_video_id}, content_type="application/json"
            )

            # Should still succeed
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data["success"])

            # Audio file operations should not be called
            mock_exists.assert_not_called()
            mock_remove.assert_not_called()

            # Cache should still be saved
            mock_save_cache.assert_called_once()

    @patch("app.summary_cache", {})
    @patch("app.save_summary_cache")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_delete_summary_audio_file_not_exists(self, mock_remove, mock_exists, mock_save_cache):
        """Test deletion when audio file doesn't exist"""
        test_video_id = "test_video_missing_audio"
        test_cache = {
            test_video_id: {
                "title": "Test Video",
                "summary": "Test summary",
                "thumbnail_url": "http://example.com/thumb.jpg",
                "audio_filename": "missing_audio.mp3",
                "summarized_at": "2023-01-01T00:00:00.000000",
                "video_url": f"https://www.youtube.com/watch?v={test_video_id}",
            }
        }

        with patch("app.summary_cache", test_cache):
            # Mock audio file doesn't exist
            mock_exists.return_value = False

            response = self.client.delete(
                "/delete_summary", json={"video_id": test_video_id}, content_type="application/json"
            )

            # Should still succeed
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data["success"])

            # File removal should not be attempted
            mock_remove.assert_not_called()

            # Cache should be saved
            mock_save_cache.assert_called_once()

    @patch("app.summary_cache", {})
    @patch("app.save_summary_cache")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_delete_summary_audio_removal_fails(self, mock_remove, mock_exists, mock_save_cache):
        """Test deletion when audio file removal fails"""
        test_video_id = "test_video_audio_fail"
        test_cache = {
            test_video_id: {
                "title": "Test Video",
                "summary": "Test summary",
                "thumbnail_url": "http://example.com/thumb.jpg",
                "audio_filename": "error_audio.mp3",
                "summarized_at": "2023-01-01T00:00:00.000000",
                "video_url": f"https://www.youtube.com/watch?v={test_video_id}",
            }
        }

        with patch("app.summary_cache", test_cache):
            # Mock audio file exists but removal fails
            mock_exists.return_value = True
            mock_remove.side_effect = OSError("Permission denied")

            response = self.client.delete(
                "/delete_summary", json={"video_id": test_video_id}, content_type="application/json"
            )

            # Should still succeed (audio removal failure is non-fatal)
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data["success"])

            # Cache should still be saved
            mock_save_cache.assert_called_once()

    @patch("app.summary_cache", {})
    @patch("app.save_summary_cache")
    def test_delete_summary_save_cache_error(self, mock_save_cache):
        """Test deletion when saving cache fails"""
        test_video_id = "test_video_save_fail"
        test_cache = {
            test_video_id: {
                "title": "Test Video",
                "summary": "Test summary",
                "thumbnail_url": "http://example.com/thumb.jpg",
                "summarized_at": "2023-01-01T00:00:00.000000",
                "video_url": f"https://www.youtube.com/watch?v={test_video_id}",
            }
        }

        with patch("app.summary_cache", test_cache):
            # Mock save cache failure
            mock_save_cache.side_effect = Exception("Disk full")

            response = self.client.delete(
                "/delete_summary", json={"video_id": test_video_id}, content_type="application/json"
            )

            # Should return error
            self.assertEqual(response.status_code, 500)
            data = json.loads(response.data)
            self.assertEqual(data["error"], "Failed to delete summary")

    @patch("app.LOGIN_ENABLED", True)
    def test_delete_summary_requires_auth(self):
        """Test that delete endpoint requires authentication when enabled"""
        # Remove testing environment variable to enable authentication
        if "TESTING" in os.environ:
            del os.environ["TESTING"]

        response = self.client.delete(
            "/delete_summary", json={"video_id": "test_video"}, content_type="application/json"
        )

        # Should redirect or return unauthorized
        self.assertIn(response.status_code, [302, 401])


class TestHelperFunctions(unittest.TestCase):
    """Test suite for helper functions"""

    def test_clean_youtube_url(self):
        """Test clean_youtube_url function"""
        # Test with watch later list parameter
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=WL"
        cleaned = clean_youtube_url(url)
        self.assertNotIn("&list=WL", cleaned)
        self.assertIn("v=dQw4w9WgXcQ", cleaned)

        # Test with regular playlist
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        cleaned = clean_youtube_url(url)
        self.assertIn("list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf", cleaned)

        # Test with extra parameters
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share&t=10"
        cleaned = clean_youtube_url(url)
        self.assertNotIn("feature=share", cleaned)
        self.assertNotIn("t=10", cleaned)

    def test_get_video_id(self):
        """Test get_video_id function"""
        # Test standard watch URL
        self.assertEqual(get_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")

        # Test short URL
        self.assertEqual(get_video_id("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ")

        # Test URL with additional parameters
        self.assertEqual(get_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share"), "dQw4w9WgXcQ")

        # Test invalid URL
        self.assertIsNone(get_video_id("https://www.youtube.com/"))

    def test_get_playlist_id(self):
        """Test get_playlist_id function"""
        # Test standard playlist URL
        self.assertEqual(
            get_playlist_id("https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"),
            "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
        )

        # Test watch URL with playlist
        self.assertEqual(
            get_playlist_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"),
            "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
        )

        # Test URL without playlist
        self.assertIsNone(get_playlist_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))

        # Test watch later list (should be removed)
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=WL"
        cleaned_url = url.replace("&list=WL", "")
        self.assertIsNone(get_playlist_id(cleaned_url))


if __name__ == "__main__":
    unittest.main()
