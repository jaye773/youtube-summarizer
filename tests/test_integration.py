import json
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

    @patch("app.youtube")
    @patch("app.YouTubeTranscriptApi")
    @patch("app.model")
    @patch("app.summary_cache", {})
    def test_full_video_summarization_flow(self, mock_model, mock_transcript_api, mock_youtube):
        """Test complete flow: URL -> Transcript -> Summary -> Cache"""
        video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        video_id = "dQw4w9WgXcQ"

        # Mock video details
        mock_request = MagicMock()
        mock_request.execute.return_value = {
            "items": [
                {
                    "id": video_id,
                    "snippet": {
                        "title": "Never Gonna Give You Up",
                        "thumbnails": {"medium": {"url": "http://example.com/thumb.jpg"}},
                    },
                }
            ]
        }
        mock_youtube.videos().list.return_value = mock_request

        # Mock transcript
        mock_transcript_api.get_transcript.return_value = [
            {"text": "Never gonna give you up"},
            {"text": "Never gonna let you down"},
        ]

        # Mock summary generation
        mock_response = MagicMock()
        mock_response.text = "This is a summary of Rick Astley's famous song."
        mock_model.generate_content.return_value = mock_response

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
        mock_youtube.playlists().list().execute.return_value = {"items": [{"snippet": {"title": "Test Playlist"}}]}

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
        mock_generate_summary.side_effect = lambda x, y: ("Cached summary for video 1", None)

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
            self.assertEqual(call_args[1]["voice"].name, "en-US-Studio-O")

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


if __name__ == "__main__":
    unittest.main()
