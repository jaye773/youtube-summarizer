import os
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

import app
from app import generate_summary, get_transcript

# Add the parent directory to the path so we can import the app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWebshareProxyConfiguration(unittest.TestCase):
    """Test suite for webshare proxy configuration functionality"""

    def setUp(self):
        """Set up test environment by clearing proxy-related environment variables"""
        self.original_env = {}
        proxy_env_vars = [
            "WEBSHARE_PROXY_ENABLED",
            "WEBSHARE_PROXY_HOST",
            "WEBSHARE_PROXY_PORT",
            "WEBSHARE_PROXY_USERNAME",
            "WEBSHARE_PROXY_PASSWORD",
        ]

        # Store original values and clear them
        for var in proxy_env_vars:
            self.original_env[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]

    def tearDown(self):
        """Restore original environment variables"""
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]

    def test_proxy_disabled_by_default(self):
        """Test that proxy is disabled by default"""
        # Reload the module to pick up environment changes
        import importlib

        importlib.reload(app)

        proxy_config = app.get_proxy_config()
        self.assertIsNone(proxy_config)

    def test_proxy_enabled_but_missing_config(self):
        """Test proxy enabled but missing required configuration"""
        os.environ["WEBSHARE_PROXY_ENABLED"] = "true"

        # Reload the module to pick up environment changes
        import importlib

        importlib.reload(app)

        with patch("builtins.print") as mock_print:
            proxy_config = app.get_proxy_config()
            self.assertIsNone(proxy_config)
            mock_print.assert_called_with(
                "⚠️ Webshare proxy is enabled but missing required configuration. "
                "Required: WEBSHARE_PROXY_HOST, WEBSHARE_PROXY_PORT, WEBSHARE_PROXY_USERNAME, WEBSHARE_PROXY_PASSWORD"
            )

    def test_proxy_fully_configured(self):
        """Test proxy with full valid configuration"""
        os.environ.update(
            {
                "WEBSHARE_PROXY_ENABLED": "true",
                "WEBSHARE_PROXY_HOST": "proxy.webshare.io",
                "WEBSHARE_PROXY_PORT": "8080",
                "WEBSHARE_PROXY_USERNAME": "testuser",
                "WEBSHARE_PROXY_PASSWORD": "testpass",
            }
        )

        # Reload the module to pick up environment changes
        import importlib

        importlib.reload(app)

        with patch("builtins.print") as mock_print:
            proxy_config = app.get_proxy_config()

            expected_proxy_url = "http://testuser:testpass@proxy.webshare.io:8080"
            expected_config = {"http": expected_proxy_url, "https": expected_proxy_url}

            self.assertEqual(proxy_config, expected_config)
            mock_print.assert_called_with("✅ Using webshare proxy: testuser@proxy.webshare.io:8080")

    def test_proxy_case_insensitive_enabled(self):
        """Test that WEBSHARE_PROXY_ENABLED is case-insensitive"""
        test_cases = ["TRUE", "True", "true", "TrUe"]

        for enabled_value in test_cases:
            with self.subTest(enabled_value=enabled_value):
                # Clear environment
                for var in [
                    "WEBSHARE_PROXY_ENABLED",
                    "WEBSHARE_PROXY_HOST",
                    "WEBSHARE_PROXY_PORT",
                    "WEBSHARE_PROXY_USERNAME",
                    "WEBSHARE_PROXY_PASSWORD",
                ]:
                    if var in os.environ:
                        del os.environ[var]

                os.environ.update(
                    {
                        "WEBSHARE_PROXY_ENABLED": enabled_value,
                        "WEBSHARE_PROXY_HOST": "proxy.webshare.io",
                        "WEBSHARE_PROXY_PORT": "8080",
                        "WEBSHARE_PROXY_USERNAME": "testuser",
                        "WEBSHARE_PROXY_PASSWORD": "testpass",
                    }
                )

                # Reload the module to pick up environment changes
                import importlib

                importlib.reload(app)

                proxy_config = app.get_proxy_config()
                self.assertIsNotNone(proxy_config)

    def test_proxy_disabled_values(self):
        """Test various values that should disable proxy"""
        test_cases = ["false", "FALSE", "False", "0", "no", "disabled", ""]

        for disabled_value in test_cases:
            with self.subTest(disabled_value=disabled_value):
                # Clear environment
                for var in [
                    "WEBSHARE_PROXY_ENABLED",
                    "WEBSHARE_PROXY_HOST",
                    "WEBSHARE_PROXY_PORT",
                    "WEBSHARE_PROXY_USERNAME",
                    "WEBSHARE_PROXY_PASSWORD",
                ]:
                    if var in os.environ:
                        del os.environ[var]

                os.environ.update(
                    {
                        "WEBSHARE_PROXY_ENABLED": disabled_value,
                        "WEBSHARE_PROXY_HOST": "proxy.webshare.io",
                        "WEBSHARE_PROXY_PORT": "8080",
                        "WEBSHARE_PROXY_USERNAME": "testuser",
                        "WEBSHARE_PROXY_PASSWORD": "testpass",
                    }
                )

                # Reload the module to pick up environment changes
                import importlib

                importlib.reload(app)

                proxy_config = app.get_proxy_config()
                self.assertIsNone(proxy_config)


class TestTranscriptWithProxy(unittest.TestCase):
    """Test suite for transcript fetching with proxy support"""

    def setUp(self):
        """Set up test environment"""
        self.original_env = {}
        proxy_env_vars = [
            "WEBSHARE_PROXY_ENABLED",
            "WEBSHARE_PROXY_HOST",
            "WEBSHARE_PROXY_PORT",
            "WEBSHARE_PROXY_USERNAME",
            "WEBSHARE_PROXY_PASSWORD",
        ]

        # Store original values and clear them
        for var in proxy_env_vars:
            self.original_env[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]

    def tearDown(self):
        """Restore original environment variables"""
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]

    @patch("app.YouTubeTranscriptApi.get_transcript")
    def test_get_transcript_without_proxy(self, mock_get_transcript):
        """Test get_transcript works without proxy configuration"""
        # Ensure proxy is disabled
        if "WEBSHARE_PROXY_ENABLED" in os.environ:
            del os.environ["WEBSHARE_PROXY_ENABLED"]

        # Reload the module to pick up environment changes
        import importlib

        importlib.reload(app)

        # Mock successful transcript response
        mock_get_transcript.return_value = [{"text": "Hello world", "start": 0.0}]

        transcript, error = app.get_transcript("test_video_id")

        self.assertEqual(transcript, "Hello world")
        self.assertIsNone(error)
        mock_get_transcript.assert_called_once_with("test_video_id", languages=["en", "en-US"], proxies=None)

    @patch("app.YouTubeTranscriptApi.get_transcript")
    def test_get_transcript_with_proxy(self, mock_get_transcript):
        """Test get_transcript works with proxy configuration"""
        # Configure proxy
        os.environ.update(
            {
                "WEBSHARE_PROXY_ENABLED": "true",
                "WEBSHARE_PROXY_HOST": "proxy.webshare.io",
                "WEBSHARE_PROXY_PORT": "8080",
                "WEBSHARE_PROXY_USERNAME": "testuser",
                "WEBSHARE_PROXY_PASSWORD": "testpass",
            }
        )

        # Reload the module to pick up environment changes
        import importlib

        importlib.reload(app)

        # Mock successful transcript response
        mock_get_transcript.return_value = [{"text": "Hello world", "start": 0.0}]

        expected_proxies = {
            "http": "http://testuser:testpass@proxy.webshare.io:8080",
            "https": "http://testuser:testpass@proxy.webshare.io:8080",
        }

        transcript, error = app.get_transcript("test_video_id")

        self.assertEqual(transcript, "Hello world")
        self.assertIsNone(error)
        mock_get_transcript.assert_called_once_with(
            "test_video_id", languages=["en", "en-US"], proxies=expected_proxies
        )

    @patch("app.YouTubeTranscriptApi.list_transcripts")
    @patch("app.YouTubeTranscriptApi.get_transcript")
    def test_get_transcript_fallback_with_proxy(self, mock_get_transcript, mock_list_transcripts):
        """Test get_transcript fallback mechanism works with proxy"""
        # Configure proxy
        os.environ.update(
            {
                "WEBSHARE_PROXY_ENABLED": "true",
                "WEBSHARE_PROXY_HOST": "proxy.webshare.io",
                "WEBSHARE_PROXY_PORT": "8080",
                "WEBSHARE_PROXY_USERNAME": "testuser",
                "WEBSHARE_PROXY_PASSWORD": "testpass",
            }
        )

        # Reload the module to pick up environment changes
        import importlib

        importlib.reload(app)

        # Mock first call to fail with NoTranscriptFound
        from youtube_transcript_api import NoTranscriptFound

        mock_get_transcript.side_effect = NoTranscriptFound("test_video_id", [], {})

        # Mock fallback to succeed
        mock_transcript = Mock()
        mock_transcript.fetch.return_value = [{"text": "Fallback transcript", "start": 0.0}]
        mock_list_result = Mock()
        mock_list_result.find_transcript.return_value = mock_transcript
        mock_list_transcripts.return_value = mock_list_result

        expected_proxies = {
            "http": "http://testuser:testpass@proxy.webshare.io:8080",
            "https": "http://testuser:testpass@proxy.webshare.io:8080",
        }

        transcript, error = app.get_transcript("test_video_id")

        self.assertEqual(transcript, "Fallback transcript")
        self.assertIsNone(error)
        mock_get_transcript.assert_called_once_with(
            "test_video_id", languages=["en", "en-US"], proxies=expected_proxies
        )
        mock_list_transcripts.assert_called_once_with("test_video_id", proxies=expected_proxies)

    def test_get_transcript_no_video_id(self):
        """Test get_transcript handles empty video ID"""
        transcript, error = app.get_transcript("")
        self.assertIsNone(transcript)
        self.assertEqual(error, "No video ID provided")

        transcript, error = app.get_transcript(None)
        self.assertIsNone(transcript)
        self.assertEqual(error, "No video ID provided")


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

        details = app.get_video_details(self.test_video_ids)

        self.assertEqual(len(details), 2)
        self.assertEqual(details["video1"]["title"], "Video 1 Title")
        self.assertEqual(details["video2"]["thumbnail_url"], "http://example.com/thumb2.jpg")

    def test_get_video_details_api_error(self):
        """Test video details retrieval when API fails"""
        # Since youtube is None in test mode, the function returns early
        details = app.get_video_details(self.test_video_ids)
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

        videos, error = app.get_videos_from_playlist(self.test_playlist_id)

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

        videos, error = app.get_videos_from_playlist(self.test_playlist_id)

        self.assertIsNotNone(videos)
        self.assertIsNone(error)
        self.assertEqual(len(videos), 2)

    @patch("app.youtube", None)
    def test_get_videos_from_playlist_error(self):
        """Test playlist retrieval when API fails"""
        # Since youtube is None in test mode, the function returns early
        videos, error = app.get_videos_from_playlist(self.test_playlist_id)

        self.assertIsNone(videos)
        self.assertEqual(error, "YouTube API client not initialized")


if __name__ == "__main__":
    unittest.main()
