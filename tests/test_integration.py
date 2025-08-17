import json
import os
import unittest
from unittest.mock import MagicMock, patch

from app import app


class TestIntegration(unittest.TestCase):
    """Integration tests for end-to-end scenarios"""

    def setUp(self):
        """Set up test client"""
        self.app = app
        self.client = self.app.test_client()
        self.app.config["TESTING"] = True
        # Set environment variable to bypass authentication during testing
        os.environ["TESTING"] = "true"

    def tearDown(self):
        """Clean up after each test"""
        # Remove testing environment variable
        if "TESTING" in os.environ:
            del os.environ["TESTING"]

    @patch("app.youtube")
    @patch("app.YouTubeTranscriptApi")
    @patch("app.generate_summary")
    @patch("app.get_video_details")
    @patch("app.summary_cache", {})
    def test_full_video_summarization_flow(
        self, mock_get_video_details, mock_generate_summary, mock_transcript_api, mock_youtube
    ):
        """Test complete flow: URL -> Transcript -> Summary -> Cache"""
        video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        video_id = "dQw4w9WgXcQ"

        # Mock video details
        mock_get_video_details.return_value = {
            video_id: {"title": "Never Gonna Give You Up", "thumbnail_url": "http://example.com/thumb.jpg"}
        }

        # Mock transcript
        mock_transcript_api.get_transcript.return_value = [
            {"text": "Never gonna give you up"},
            {"text": "Never gonna let you down"},
        ]

        # Mock summary generation
        mock_generate_summary.return_value = ("This is a summary of Rick Astley's famous song.", None)

        # Make request
        response = self.client.post(
            "/summarize", data=json.dumps({"urls": [video_url]}), content_type="application/json"
        )

        # Verify response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["type"], "video")
        self.assertEqual(data[0]["title"], "Never Gonna Give You Up")
        self.assertEqual(data[0]["summary"], "This is a summary of Rick Astley's famous song.")

    @patch("app.youtube")
    @patch("app.get_transcript")
    @patch("app.generate_summary")
    def test_playlist_summarization_flow(self, mock_generate_summary, mock_get_transcript, mock_youtube):
        """Test complete playlist summarization flow"""
        playlist_url = "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"

        # Mock playlist metadata
        playlist_request = MagicMock()
        playlist_request.execute.return_value = {"items": [{"snippet": {"title": "Test Playlist"}}]}
        mock_youtube.playlists().list.return_value = playlist_request

        # Mock playlist items
        pl_items_request = MagicMock()
        pl_items_request.execute.return_value = {
            "items": [
                {
                    "snippet": {
                        "resourceId": {"videoId": "video1"},
                        "title": "Video 1",
                        "thumbnails": {"medium": {"url": "http://example.com/thumb1.jpg"}},
                    }
                },
                {"snippet": {"resourceId": {"videoId": "video2"}, "title": "Private video"}},
            ],
            "nextPageToken": None,
        }

        # Setup mock returns
        mock_youtube.playlistItems().list.return_value = pl_items_request

        # Mock cache for video1
        mock_get_transcript.side_effect = lambda x: ("Video 1 transcript", None)
        mock_generate_summary.side_effect = lambda x, y, z=None: ("Cached summary for video 1", None)

        # Make request
        response = self.client.post(
            "/summarize", data=json.dumps({"urls": [playlist_url]}), content_type="application/json"
        )

        # Verify response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["type"], "playlist")
        self.assertEqual(data[0]["title"], "Test Playlist")
        self.assertEqual(len(data[0]["summaries"]), 2)

        # Check first video (cached)
        self.assertEqual(data[0]["summaries"][0]["title"], "Video 1")
        self.assertEqual(data[0]["summaries"][0]["summary"], "Cached summary for video 1")

        # Check second video (private)
        self.assertEqual(data[0]["summaries"][1]["title"], "Private video")
        self.assertEqual(data[0]["summaries"][1]["error"], "Video is private or deleted.")

    def test_invalid_url_handling(self):
        """Test handling of invalid YouTube URLs"""
        invalid_urls = ["https://www.google.com", "not a url", "https://youtube.com/", ""]

        response = self.client.post(
            "/summarize", data=json.dumps({"urls": invalid_urls}), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        for result in data:
            self.assertEqual(result["type"], "error")
            self.assertIn("Invalid or unsupported YouTube URL", result["error"])

    @patch("app.tts_client")
    @patch("os.path.exists")
    def test_text_to_speech_flow(self, mock_exists, mock_tts_client):
        """Test text-to-speech generation flow"""
        mock_exists.return_value = False

        # Mock TTS response
        mock_response = MagicMock()
        mock_response.audio_content = b"test audio content"
        mock_tts_client.synthesize_speech.return_value = mock_response

        test_text = "This is a test summary to convert to speech."

        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            response = self.client.post("/speak", data=json.dumps({"text": test_text}), content_type="application/json")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, "audio/mpeg")

            # Verify synthesis was called with correct parameters
            call_args = mock_tts_client.synthesize_speech.call_args
            self.assertEqual(call_args[1]["input"].text, test_text)
            self.assertEqual(call_args[1]["voice"].language_code, "en-US")
            self.assertEqual(call_args[1]["voice"].name, "en-US-Chirp3-HD-Zephyr")

    @patch("app.summary_cache")
    def test_search_functionality_integration(self, mock_cache):
        """Test search functionality with realistic cached data"""
        # Set up realistic cached summaries
        mock_cache_data = {
            "abc123": {
                "title": "Introduction to Python Programming",
                "summary": (
                    "This video covers the fundamentals of Python programming including variables, "
                    "loops, and functions. Great for beginners who want to learn coding."
                ),
                "thumbnail_url": "http://example.com/thumb1.jpg",
                "summarized_at": "2024-01-01T12:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=abc123",
            },
            "def456": {
                "title": "Advanced JavaScript Concepts",
                "summary": (
                    "Deep dive into JavaScript closures, async/await, and modern ES6+ features. "
                    "Perfect for experienced developers."
                ),
                "thumbnail_url": "http://example.com/thumb2.jpg",
                "summarized_at": "2024-01-02T15:30:00.000000",
                "video_url": "https://www.youtube.com/watch?v=def456",
            },
            "ghi789": {
                "title": "Machine Learning with Python",
                "summary": (
                    "Learn how to build machine learning models using Python libraries " "like scikit-learn and pandas."
                ),
                "thumbnail_url": "http://example.com/thumb3.jpg",
                "summarized_at": "2024-01-03T10:15:00.000000",
                "video_url": "https://www.youtube.com/watch?v=ghi789",
            },
        }

        # Mock the items() method to return our test data
        mock_cache.items.return_value = mock_cache_data.items()

        # Test search by programming language
        response = self.client.get("/search_summaries?q=python")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)  # Should find both Python videos

        # Verify results are sorted by date (most recent first)
        self.assertEqual(data[0]["video_id"], "ghi789")  # Machine Learning (Jan 3)
        self.assertEqual(data[1]["video_id"], "abc123")  # Introduction (Jan 1)

        # Test search by skill level
        response = self.client.get("/search_summaries?q=beginners")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Introduction to Python Programming")

        # Test search by specific technology
        response = self.client.get("/search_summaries?q=javascript")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Advanced JavaScript Concepts")

        # Test search with no results
        response = self.client.get("/search_summaries?q=blockchain")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 0)

        # Test partial word search
        response = self.client.get("/search_summaries?q=learn")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)  # Should match "learn" in summaries

    @patch("app.get_playlist_id")
    @patch("app.get_video_id")
    @patch("app.get_video_details")
    @patch("app.get_transcript")
    @patch("app.generate_summary")
    @patch("app.summary_cache", {})
    @patch("os.path.exists")
    @patch("os.remove")
    def test_summarize_then_delete_integration(
        self,
        mock_remove,
        mock_exists,
        mock_generate_summary,
        mock_get_transcript,
        mock_get_video_details,
        mock_get_video_id,
        mock_get_playlist_id,
    ):
        """Test complete flow: Summarize video then delete it"""
        video_url = "https://www.youtube.com/watch?v=test123"
        video_id = "test123"

        # Mock URL parsing - playlist ID should return None, video ID should return our test ID
        mock_get_playlist_id.return_value = None
        mock_get_video_id.return_value = video_id

        # Mock video details
        mock_get_video_details.return_value = {
            video_id: {"title": "Integration Test Video", "thumbnail_url": "http://example.com/thumb.jpg"}
        }

        # Mock transcript
        mock_get_transcript.return_value = ("This is a test transcript", None)

        # Mock summary generation
        mock_generate_summary.return_value = ("This is a test summary for integration testing.", None)

        # Step 1: Summarize the video
        response = self.client.post("/summarize", json={"urls": [video_url]}, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 1)
        # Debug: print the actual response if it's an error
        if data[0]["type"] != "video":
            print(f"Unexpected response: {data}")
        self.assertEqual(data[0]["type"], "video")
        self.assertEqual(data[0]["video_id"], video_id)
        self.assertIsNotNone(data[0]["summary"])

        # Step 2: Verify summary is in cache
        response = self.client.get("/get_cached_summaries")
        self.assertEqual(response.status_code, 200)
        cached_data = json.loads(response.data)
        self.assertEqual(len(cached_data), 1)
        self.assertEqual(cached_data[0]["title"], "Integration Test Video")

        # Step 3: Delete the summary
        mock_exists.return_value = True  # Mock audio file exists
        response = self.client.delete("/delete_summary", json={"video_id": video_id}, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        delete_data = json.loads(response.data)
        self.assertTrue(delete_data["success"])
        self.assertIn("deleted successfully", delete_data["message"])

        # Step 4: Verify summary is removed from cache
        response = self.client.get("/get_cached_summaries")
        self.assertEqual(response.status_code, 200)
        final_cached_data = json.loads(response.data)
        self.assertEqual(len(final_cached_data), 0)

        # Verify audio file removal was attempted
        mock_remove.assert_called_once()

    def test_delete_from_search_results_integration(self):
        """Test deleting a summary found through search"""
        # Set up cache with test data
        test_cache = {
            "video1": {
                "title": "Machine Learning Basics",
                "summary": "Learn the fundamentals of ML",
                "thumbnail_url": "http://example.com/thumb1.jpg",
                "summarized_at": "2023-01-01T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video1",
            },
            "video2": {
                "title": "Python Tutorial",
                "summary": "Python programming guide",
                "thumbnail_url": "http://example.com/thumb2.jpg",
                "summarized_at": "2023-01-02T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=video2",
            },
        }

        with patch("app.summary_cache", test_cache), patch("app.save_summary_cache") as mock_save:

            # Step 1: Search for summaries
            response = self.client.get("/search_summaries?q=Machine")
            self.assertEqual(response.status_code, 200)
            search_data = json.loads(response.data)
            self.assertEqual(len(search_data), 1)
            self.assertEqual(search_data[0]["video_id"], "video1")

            # Step 2: Delete the found summary
            response = self.client.delete(
                "/delete_summary", json={"video_id": "video1"}, content_type="application/json"
            )

            self.assertEqual(response.status_code, 200)
            delete_data = json.loads(response.data)
            self.assertTrue(delete_data["success"])

            # Verify save was called
            mock_save.assert_called_once()

            # Step 3: Verify it no longer appears in search
            response = self.client.get("/search_summaries?q=Machine")
            self.assertEqual(response.status_code, 200)
            final_search_data = json.loads(response.data)
            # The delete should have removed the item, so search should return 0 results
            self.assertEqual(len(final_search_data), 0)

    def test_delete_multiple_summaries_integration(self):
        """Test deleting multiple summaries in sequence"""
        test_cache = {
            "vid1": {
                "title": "Video 1",
                "summary": "Summary 1",
                "thumbnail_url": "http://example.com/thumb1.jpg",
                "summarized_at": "2023-01-01T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=vid1",
            },
            "vid2": {
                "title": "Video 2",
                "summary": "Summary 2",
                "thumbnail_url": "http://example.com/thumb2.jpg",
                "summarized_at": "2023-01-02T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=vid2",
            },
            "vid3": {
                "title": "Video 3",
                "summary": "Summary 3",
                "thumbnail_url": "http://example.com/thumb3.jpg",
                "summarized_at": "2023-01-03T00:00:00.000000",
                "video_url": "https://www.youtube.com/watch?v=vid3",
            },
        }

        with patch("app.summary_cache", test_cache), patch("app.save_summary_cache") as mock_save:

            # Verify initial state
            response = self.client.get("/get_cached_summaries")
            self.assertEqual(response.status_code, 200)
            initial_data = json.loads(response.data)
            self.assertEqual(len(initial_data), 3)

            # Delete first summary
            response = self.client.delete("/delete_summary", json={"video_id": "vid1"}, content_type="application/json")
            self.assertEqual(response.status_code, 200)

            # Delete second summary
            response = self.client.delete("/delete_summary", json={"video_id": "vid2"}, content_type="application/json")
            self.assertEqual(response.status_code, 200)

            # Verify cache save was called for each deletion
            self.assertEqual(mock_save.call_count, 2)

            # Try to delete already deleted summary
            response = self.client.delete("/delete_summary", json={"video_id": "vid1"}, content_type="application/json")
            self.assertEqual(response.status_code, 404)
            error_data = json.loads(response.data)
            self.assertEqual(error_data["error"], "Summary not found")


if __name__ == "__main__":
    unittest.main()
