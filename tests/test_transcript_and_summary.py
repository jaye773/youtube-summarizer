import os
import unittest
from unittest.mock import MagicMock, patch

from app import generate_summary, get_transcript, get_video_details, get_videos_from_playlist


class TestTranscriptAndSummary(unittest.TestCase):
    """Test suite for transcript and summary generation functions"""

    def setUp(self):
        """Set up test data"""
        # Set environment variable to bypass authentication during testing
        os.environ["TESTING"] = "true"
        self.test_video_id = "dQw4w9WgXcQ"
        self.test_transcript = "This is a test transcript with some content about testing."
        self.test_title = "Test Video Title"

    def tearDown(self):
        """Clean up after each test"""
        # Remove testing environment variable
        if "TESTING" in os.environ:
            del os.environ["TESTING"]

    @patch("app.YouTubeTranscriptApi")
    def test_get_transcript_success(self, mock_transcript_api):
        """Test successful transcript retrieval"""
        mock_transcript_api.get_transcript.return_value = [
            {"text": "This is a test"},
            {"text": "transcript with content"},
        ]

        transcript, error = get_transcript(self.test_video_id)

        self.assertIsNotNone(transcript)
        self.assertIsNone(error)
        self.assertEqual(transcript, "This is a test transcript with content")

    @patch("app.YouTubeTranscriptApi")
    def test_get_transcript_no_transcript_found(self, mock_transcript_api):
        """Test when no transcript is found"""
        mock_transcript_api.get_transcript.side_effect = Exception("NoTranscriptFound")

        transcript, error = get_transcript(self.test_video_id)

        self.assertIsNone(transcript)
        self.assertIsNotNone(error)

    def test_get_transcript_no_video_id(self):
        """Test get_transcript with no video ID"""
        transcript, error = get_transcript(None)

        self.assertIsNone(transcript)
        self.assertEqual(error, "No video ID provided")

    @patch("app.YouTubeTranscriptApi")
    def test_get_transcript_empty_transcript(self, mock_transcript_api):
        """Test when transcript is empty"""
        mock_transcript_api.get_transcript.return_value = [{"text": ""}, {"text": "   "}]

        transcript, error = get_transcript(self.test_video_id)

        self.assertIsNone(transcript)
        self.assertEqual(error, "Transcript was found but it is empty.")

    @patch("app.model")
    def test_generate_summary_success(self, mock_model):
        """Test successful summary generation"""
        mock_response = MagicMock()
        mock_response.text = "This is a generated summary of the video."
        mock_model.generate_content.return_value = mock_response

        summary, error = generate_summary(self.test_transcript, self.test_title)

        self.assertIsNotNone(summary)
        self.assertIsNone(error)
        self.assertEqual(summary, "This is a generated summary of the video.")

    def test_generate_summary_no_transcript(self):
        """Test summary generation with no transcript"""
        summary, error = generate_summary(None, self.test_title)

        self.assertIsNone(summary)
        self.assertEqual(error, "Cannot generate summary from empty transcript.")

    @patch("app.model")
    def test_generate_summary_api_error(self, mock_model):
        """Test summary generation when API fails"""
        mock_model.generate_content.side_effect = Exception("API Error")

        summary, error = generate_summary(self.test_transcript, self.test_title)

        self.assertIsNone(summary)
        self.assertIn("Error calling Gemini API", error)


class TestVideoDetails(unittest.TestCase):
    """Test suite for video details retrieval"""

    def setUp(self):
        """Set up test data"""
        self.test_video_ids = ["video1", "video2"]

    @patch("app.youtube")
    def test_get_video_details_success(self, mock_youtube):
        """Test successful video details retrieval"""
        mock_request = MagicMock()
        mock_response = {
            "items": [
                {
                    "id": "video1",
                    "snippet": {
                        "title": "Video 1 Title",
                        "thumbnails": {"medium": {"url": "http://example.com/thumb1.jpg"}},
                    },
                },
                {
                    "id": "video2",
                    "snippet": {
                        "title": "Video 2 Title",
                        "thumbnails": {"medium": {"url": "http://example.com/thumb2.jpg"}},
                    },
                },
            ]
        }
        mock_request.execute.return_value = mock_response
        mock_youtube.videos().list.return_value = mock_request

        details = get_video_details(self.test_video_ids)

        self.assertEqual(len(details), 2)
        self.assertEqual(details["video1"]["title"], "Video 1 Title")
        self.assertEqual(details["video2"]["thumbnail_url"], "http://example.com/thumb2.jpg")

    def test_get_video_details_api_error(self):
        """Test video details retrieval when API fails"""
        # Since youtube is None in test mode, the function returns early
        details = get_video_details(self.test_video_ids)
        self.assertEqual(details, {})


class TestPlaylistFunctions(unittest.TestCase):
    """Test suite for playlist-related functions"""

    def setUp(self):
        """Set up test data"""
        self.test_playlist_id = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"

    @patch("app.youtube")
    def test_get_videos_from_playlist_success(self, mock_youtube):
        """Test successful playlist video retrieval"""
        mock_request = MagicMock()
        mock_response = {
            "items": [
                {"contentDetails": {"videoId": "video1"}, "snippet": {"title": "Video 1"}},
                {"contentDetails": {"videoId": "video2"}, "snippet": {"title": "Video 2"}},
            ],
            "nextPageToken": None,
        }
        mock_request.execute.return_value = mock_response
        mock_youtube.playlistItems().list.return_value = mock_request

        videos, error = get_videos_from_playlist(self.test_playlist_id)

        self.assertIsNotNone(videos)
        self.assertIsNone(error)
        self.assertEqual(len(videos), 2)

    @patch("app.youtube")
    def test_get_videos_from_playlist_pagination(self, mock_youtube):
        """Test playlist retrieval with pagination"""
        mock_request = MagicMock()

        # First page response
        first_response = {"items": [{"contentDetails": {"videoId": "video1"}}], "nextPageToken": "token123"}

        # Second page response
        second_response = {"items": [{"contentDetails": {"videoId": "video2"}}], "nextPageToken": None}

        mock_request.execute.side_effect = [first_response, second_response]
        mock_youtube.playlistItems().list.return_value = mock_request

        videos, error = get_videos_from_playlist(self.test_playlist_id)

        self.assertIsNotNone(videos)
        self.assertIsNone(error)
        self.assertEqual(len(videos), 2)

    @patch("app.youtube", None)
    def test_get_videos_from_playlist_error(self):
        """Test playlist retrieval when API fails"""
        # Since youtube is None in test mode, the function returns early
        videos, error = get_videos_from_playlist(self.test_playlist_id)

        self.assertIsNone(videos)
        self.assertEqual(error, "YouTube API client not initialized")


if __name__ == "__main__":
    unittest.main()
