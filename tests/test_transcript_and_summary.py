import os
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

import requests
from youtube_transcript_api import (
    AgeRestricted,
    FetchedTranscript,
    FetchedTranscriptSnippet,
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeDataUnparsable,
    YouTubeRequestFailed,
)
from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig

import app
import youtube_helpers
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

    def _reload_with(self, env):
        os.environ.update(env)
        import importlib

        importlib.reload(app)

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
                "Required: WEBSHARE_PROXY_USERNAME, WEBSHARE_PROXY_PASSWORD, plus both WEBSHARE_PROXY_HOST and "
                "WEBSHARE_PROXY_PORT for a fixed proxy server (leave both unset for Webshare rotating residential "
                "proxies)"
            )

    def test_proxy_host_without_port_is_rejected(self):
        """A host without a port (or vice versa) is a misconfiguration, not a rotating setup"""
        self._reload_with(
            {
                "WEBSHARE_PROXY_ENABLED": "true",
                "WEBSHARE_PROXY_HOST": "proxy.webshare.io",
                "WEBSHARE_PROXY_USERNAME": "testuser",
                "WEBSHARE_PROXY_PASSWORD": "testpass",
            }
        )
        with patch("builtins.print"):
            self.assertIsNone(app.get_proxy_config())

    def test_proxy_fully_configured(self):
        """Host/port/credentials produce a GenericProxyConfig for that proxy server"""
        self._reload_with(
            {
                "WEBSHARE_PROXY_ENABLED": "true",
                "WEBSHARE_PROXY_HOST": "proxy.webshare.io",
                "WEBSHARE_PROXY_PORT": "8080",
                "WEBSHARE_PROXY_USERNAME": "testuser",
                "WEBSHARE_PROXY_PASSWORD": "testpass",
            }
        )

        with patch("builtins.print") as mock_print:
            proxy_config = app.get_proxy_config()

            expected_proxy_url = "http://testuser:testpass@proxy.webshare.io:8080"
            self.assertIsInstance(proxy_config, GenericProxyConfig)
            self.assertNotIsInstance(proxy_config, WebshareProxyConfig)
            self.assertEqual(proxy_config.to_requests_dict(), {"http": expected_proxy_url, "https": expected_proxy_url})
            mock_print.assert_called_with("✅ Using webshare proxy: testuser@proxy.webshare.io:8080")

    def test_proxy_credentials_are_url_encoded(self):
        """Special characters in proxy credentials must not corrupt the proxy URL"""
        self._reload_with(
            {
                "WEBSHARE_PROXY_ENABLED": "true",
                "WEBSHARE_PROXY_HOST": "proxy.webshare.io",
                "WEBSHARE_PROXY_PORT": "8080",
                "WEBSHARE_PROXY_USERNAME": "user@corp",
                "WEBSHARE_PROXY_PASSWORD": "p:ss/w@rd",
            }
        )
        with patch("builtins.print"):
            proxy_config = app.get_proxy_config()
        expected = "http://user%40corp:p%3Ass%2Fw%40rd@proxy.webshare.io:8080"
        self.assertEqual(proxy_config.to_requests_dict()["https"], expected)

    def test_proxy_rotating_residential_when_host_unset(self):
        """Credentials without host/port use Webshare's rotating residential endpoint"""
        self._reload_with(
            {
                "WEBSHARE_PROXY_ENABLED": "true",
                "WEBSHARE_PROXY_USERNAME": "testuser",
                "WEBSHARE_PROXY_PASSWORD": "testpass",
            }
        )

        with patch("builtins.print") as mock_print:
            proxy_config = app.get_proxy_config()

        self.assertIsInstance(proxy_config, WebshareProxyConfig)
        self.assertEqual(proxy_config.url, "http://testuser-rotate:testpass@p.webshare.io:80/")
        self.assertGreater(proxy_config.retries_when_blocked, 0)
        mock_print.assert_called_once_with("✅ Using webshare rotating residential proxies as testuser")

    def test_proxy_config_logs_only_once(self):
        """get_proxy_config runs on every transcript fetch; it should not log every time"""
        self._reload_with(
            {
                "WEBSHARE_PROXY_ENABLED": "true",
                "WEBSHARE_PROXY_HOST": "proxy.webshare.io",
                "WEBSHARE_PROXY_PORT": "8080",
                "WEBSHARE_PROXY_USERNAME": "testuser",
                "WEBSHARE_PROXY_PASSWORD": "testpass",
            }
        )

        with patch("builtins.print") as mock_print:
            for _ in range(5):
                self.assertIsNotNone(app.get_proxy_config())
            self.assertEqual(mock_print.call_count, 1)

            # A changed configuration is logged again
            with patch.object(app, "WEBSHARE_PROXY_PORT", "9090"):
                app.get_proxy_config()
            self.assertEqual(mock_print.call_count, 2)
            mock_print.assert_called_with("✅ Using webshare proxy: testuser@proxy.webshare.io:9090")

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


def _fetched(*texts, language_code="en", is_generated=False):
    """Build a real youtube-transcript-api FetchedTranscript from snippet texts."""
    return FetchedTranscript(
        snippets=[FetchedTranscriptSnippet(text=t, start=float(i), duration=1.0) for i, t in enumerate(texts)],
        video_id="vid",
        language="English",
        language_code=language_code,
        is_generated=is_generated,
    )


def _transcript(language_code, *texts, is_generated=False):
    """A stand-in for youtube_transcript_api.Transcript whose fetch() returns the given texts."""
    transcript = Mock()
    transcript.language_code = language_code
    transcript.is_generated = is_generated
    transcript.fetch.return_value = _fetched(*texts, language_code=language_code, is_generated=is_generated)
    return transcript


class _FakeTranscriptList:
    """Mimics TranscriptList: find_transcript() by priority, iteration yields manual before generated."""

    def __init__(self, *transcripts):
        self._transcripts = list(transcripts)

    def __iter__(self):
        manual = [t for t in self._transcripts if not t.is_generated]
        generated = [t for t in self._transcripts if t.is_generated]
        return iter(manual + generated)

    def find_transcript(self, language_codes):
        for code in language_codes:
            for transcript in self:
                if transcript.language_code == code:
                    return transcript
        raise NoTranscriptFound("vid", language_codes, self)

    def __str__(self):
        return ", ".join(t.language_code for t in self._transcripts)


class TestTranscriptWithProxy(unittest.TestCase):
    """Test suite for transcript fetching (youtube-transcript-api instance API) with proxy support"""

    def setUp(self):
        """Set up test environment"""
        self.original_env = {}
        proxy_env_vars = [
            "WEBSHARE_PROXY_ENABLED",
            "WEBSHARE_PROXY_HOST",
            "WEBSHARE_PROXY_PORT",
            "WEBSHARE_PROXY_USERNAME",
            "WEBSHARE_PROXY_PASSWORD",
            "NETWORK_TIMEOUT",
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

    def _reload_app(self, env=None):
        os.environ.update(env or {})
        import importlib

        importlib.reload(app)

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_get_transcript_without_proxy(self, mock_api_cls):
        """No proxy: the API is built without a proxy config and with a timeout-applying session"""
        self._reload_app()
        mock_api_cls.return_value.list.return_value = _FakeTranscriptList(_transcript("en", "Hello", "world"))

        transcript, error = app.get_transcript("test_video_id")

        self.assertEqual(transcript, "Hello world")
        self.assertIsNone(error)
        mock_api_cls.return_value.list.assert_called_once_with("test_video_id")
        kwargs = mock_api_cls.call_args.kwargs
        self.assertIsNone(kwargs["proxy_config"])
        self.assertIsInstance(kwargs["http_client"], youtube_helpers._TimeoutSession)

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_get_transcript_with_proxy(self, mock_api_cls):
        """The configured proxy is passed to the API as a GenericProxyConfig"""
        with patch("builtins.print"):
            self._reload_app(
                {
                    "WEBSHARE_PROXY_ENABLED": "true",
                    "WEBSHARE_PROXY_HOST": "proxy.webshare.io",
                    "WEBSHARE_PROXY_PORT": "8080",
                    "WEBSHARE_PROXY_USERNAME": "testuser",
                    "WEBSHARE_PROXY_PASSWORD": "testpass",
                }
            )
            mock_api_cls.return_value.list.return_value = _FakeTranscriptList(_transcript("en", "Hello world"))

            transcript, error = app.get_transcript("test_video_id")

        self.assertEqual(transcript, "Hello world")
        self.assertIsNone(error)
        proxy_config = mock_api_cls.call_args.kwargs["proxy_config"]
        self.assertIsInstance(proxy_config, GenericProxyConfig)
        expected_url = "http://testuser:testpass@proxy.webshare.io:8080"
        self.assertEqual(proxy_config.to_requests_dict(), {"http": expected_url, "https": expected_url})

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_legacy_dict_proxy_config_is_converted(self, mock_api_cls):
        """A requests-style proxies dict from an injected config function still works"""
        mock_api_cls.return_value.list.return_value = _FakeTranscriptList(_transcript("en", "Hi"))
        legacy = {"http": "http://u:p@h:1", "https": "http://u:p@h:1"}

        with patch.object(youtube_helpers, "_get_proxy_config", lambda: legacy):
            transcript, error = youtube_helpers.get_transcript("vid")

        self.assertEqual(transcript, "Hi")
        proxy_config = mock_api_cls.call_args.kwargs["proxy_config"]
        self.assertIsInstance(proxy_config, GenericProxyConfig)
        self.assertEqual(proxy_config.to_requests_dict(), legacy)

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_prefers_en_over_other_english_variants(self, mock_api_cls):
        mock_api_cls.return_value.list.return_value = _FakeTranscriptList(
            _transcript("en-GB", "British"),
            _transcript("en", "Auto English", is_generated=True),
        )

        transcript, error = app.get_transcript("vid")

        self.assertEqual(transcript, "Auto English")
        self.assertIsNone(error)

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_fallback_to_other_english_variant(self, mock_api_cls):
        """When en/en-US are missing, any English transcript is used, manual before generated"""
        mock_api_cls.return_value.list.return_value = _FakeTranscriptList(
            _transcript("de", "Hallo"),
            _transcript("en-AU", "Generated Aussie", is_generated=True),
            _transcript("en-GB", "Manual British"),
        )

        transcript, error = app.get_transcript("vid")

        self.assertEqual(transcript, "Manual British")
        self.assertIsNone(error)

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_fallback_to_generated_english_variant(self, mock_api_cls):
        mock_api_cls.return_value.list.return_value = _FakeTranscriptList(
            _transcript("fr", "Bonjour"),
            _transcript("en-GB", "Generated British", is_generated=True),
        )

        transcript, error = app.get_transcript("vid")

        self.assertEqual(transcript, "Generated British")
        self.assertIsNone(error)

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_no_english_transcript(self, mock_api_cls):
        mock_api_cls.return_value.list.return_value = _FakeTranscriptList(_transcript("de", "Hallo"))

        transcript, error = app.get_transcript("vid")

        self.assertIsNone(transcript)
        self.assertEqual(error, "No transcripts are available for this video.")

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_fallback_transcript_empty(self, mock_api_cls):
        mock_api_cls.return_value.list.return_value = _FakeTranscriptList(_transcript("en-GB", "", "  "))

        transcript, error = app.get_transcript("vid")

        self.assertIsNone(transcript)
        self.assertEqual(error, "A transcript was found, but it is empty.")

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_library_errors_map_to_clear_messages(self, mock_api_cls):
        cases = [
            (TranscriptsDisabled("vid"), "Transcripts are disabled for this video."),
            (NoTranscriptFound("vid", ["en"], "none"), "No transcripts are available for this video."),
            (RequestBlocked("vid"), youtube_helpers.BLOCKED_MESSAGE),
            (IpBlocked("vid"), youtube_helpers.BLOCKED_MESSAGE),
            (InvalidVideoId("vid"), "Invalid YouTube video ID."),
            (
                VideoUnavailable("vid"),
                "This video is unavailable (it may be private, deleted, or region-restricted).",
            ),
            (AgeRestricted("vid"), "This video is age-restricted, so its transcript cannot be fetched."),
            (
                VideoUnplayable("vid", "Members only", []),
                "This video cannot be played, so its transcript is unavailable: Members only",
            ),
            (
                PoTokenRequired("vid"),
                "YouTube currently requires extra verification for this video's transcript. Try again later.",
            ),
            (
                requests.exceptions.ReadTimeout("read timed out"),
                "Timed out fetching the transcript after 60 seconds. Try again later.",
            ),
        ]
        for exc, expected in cases:
            with self.subTest(exc=type(exc).__name__):
                mock_api_cls.return_value.list.side_effect = exc
                transcript, error = app.get_transcript("vid")
                self.assertIsNone(transcript)
                self.assertEqual(error, expected)

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_request_failed_and_unexpected_errors(self, mock_api_cls):
        http_error = requests.exceptions.HTTPError("429 Client Error: Too Many Requests")
        mock_api_cls.return_value.list.side_effect = YouTubeRequestFailed("vid", http_error)
        _, error = app.get_transcript("vid")
        self.assertEqual(
            error,
            "The request to YouTube failed while fetching the transcript (429 Client Error: Too Many Requests).",
        )

        mock_api_cls.return_value.list.side_effect = YouTubeDataUnparsable("vid")
        _, error = app.get_transcript("vid")
        self.assertTrue(error.startswith("Could not retrieve the transcript: The data required"))

        mock_api_cls.return_value.list.side_effect = RuntimeError("boom")
        _, error = app.get_transcript("vid")
        self.assertIn("An unexpected error occurred", error)
        self.assertIn("boom", error)

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_network_timeout_env_sets_session_timeout(self, mock_api_cls):
        mock_api_cls.return_value.list.return_value = _FakeTranscriptList(_transcript("en", "x"))
        with patch.dict(os.environ, {"NETWORK_TIMEOUT": "7"}):
            app.get_transcript("vid")
        self.assertEqual(mock_api_cls.call_args.kwargs["http_client"]._default_timeout, 7)

    def test_timeout_session_applies_default_timeout(self):
        session = youtube_helpers._TimeoutSession(12)
        with patch("requests.Session.request") as mock_request:
            session.get("https://www.youtube.com/watch?v=vid")
            self.assertEqual(mock_request.call_args.kwargs["timeout"], 12)

            # An explicit timeout from the caller is kept
            session.post("https://www.youtube.com/youtubei/v1/player", timeout=3)
            self.assertEqual(mock_request.call_args.kwargs["timeout"], 3)
        session.close()

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

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_get_transcript_success(self, mock_transcript_api):
        """Test successful transcript retrieval"""
        mock_transcript_api.return_value.list.return_value = _FakeTranscriptList(
            _transcript("en", "This is a test", "transcript with content")
        )

        transcript, error = get_transcript(self.test_video_id)

        self.assertIsNotNone(transcript)
        self.assertIsNone(error)
        self.assertEqual(transcript, "This is a test transcript with content")

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_get_transcript_no_transcript_found(self, mock_transcript_api):
        """Test when no transcript is found"""
        mock_transcript_api.return_value.list.side_effect = NoTranscriptFound(self.test_video_id, ["en"], "none")

        transcript, error = get_transcript(self.test_video_id)

        self.assertIsNone(transcript)
        self.assertEqual(error, "No transcripts are available for this video.")

    def test_get_transcript_no_video_id(self):
        """Test get_transcript with no video ID"""
        transcript, error = get_transcript(None)

        self.assertIsNone(transcript)
        self.assertEqual(error, "No video ID provided")

    @patch("youtube_helpers.YouTubeTranscriptApi")
    def test_get_transcript_empty_transcript(self, mock_transcript_api):
        """Test when transcript is empty"""
        mock_transcript_api.return_value.list.return_value = _FakeTranscriptList(_transcript("en", "", "   "))

        transcript, error = get_transcript(self.test_video_id)

        self.assertIsNone(transcript)
        self.assertEqual(error, "Transcript was found but it is empty.")

    @patch("ai_models.gemini_client")
    def test_generate_summary_gemini_success(self, mock_gemini_model):
        """Test successful summary generation with Gemini"""
        mock_response = MagicMock()
        mock_response.text = "This is a generated summary of the video using Gemini."
        mock_gemini_model.models.generate_content.return_value = mock_response

        summary, error = generate_summary(self.test_transcript, self.test_title, "gemini-2.5-flash")

        self.assertIsNotNone(summary)
        self.assertIsNone(error)
        self.assertEqual(summary, "This is a generated summary of the video using Gemini.")

    @patch("ai_models.gemini_client")
    def test_generate_summary_gemini_uses_selected_model(self, mock_client):
        """The configured model id for the selected key is passed to the API"""
        mock_client.models.generate_content.return_value = MagicMock(text="ok")

        generate_summary(self.test_transcript, self.test_title, "gemini-2.5-pro")

        _, kwargs = mock_client.models.generate_content.call_args
        self.assertEqual(kwargs["model"], "gemini-2.5-pro")

    @patch("ai_models.openai_client")
    def test_generate_summary_openai_success(self, mock_openai_client):
        """Test successful summary generation with OpenAI"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is a generated summary of the video using OpenAI."
        mock_openai_client.chat.completions.create.return_value = mock_response

        summary, error = generate_summary(self.test_transcript, self.test_title, "gpt-4o")

        self.assertIsNotNone(summary)
        self.assertIsNone(error)
        self.assertEqual(summary, "This is a generated summary of the video using OpenAI.")

    def test_generate_summary_no_transcript(self):
        """Test summary generation with no transcript"""
        summary, error = generate_summary(None, self.test_title)

        self.assertIsNone(summary)
        self.assertEqual(error, "Cannot generate summary from empty transcript.")

    def test_generate_summary_invalid_model(self):
        """Test summary generation with invalid model"""
        summary, error = generate_summary(self.test_transcript, self.test_title, "invalid-model")

        self.assertIsNone(summary)
        self.assertIn("Unsupported model: invalid-model", error)

    @patch("ai_models.gemini_client")
    def test_generate_summary_gemini_api_error(self, mock_gemini_model):
        """Test summary generation when Gemini API fails"""
        mock_gemini_model.models.generate_content.side_effect = Exception("Gemini API Error")

        summary, error = generate_summary(self.test_transcript, self.test_title, "gemini-2.5-flash")

        self.assertIsNone(summary)
        self.assertIn("Error calling Gemini API", error)

    @patch("ai_models.openai_client")
    def test_generate_summary_openai_api_error(self, mock_openai_client):
        """Test summary generation when OpenAI API fails"""
        mock_openai_client.chat.completions.create.side_effect = Exception("OpenAI API Error")

        summary, error = generate_summary(self.test_transcript, self.test_title, "gpt-4o")

        self.assertIsNone(summary)
        self.assertIn("Error calling OpenAI API", error)

    def test_generate_summary_default_model(self):
        """Test that default model is used when none specified"""
        with patch("ai_models.gemini_client") as mock_gemini_model:
            mock_response = MagicMock()
            mock_response.text = "Default model summary"
            mock_gemini_model.models.generate_content.return_value = mock_response

            summary, error = generate_summary(self.test_transcript, self.test_title)

            self.assertIsNotNone(summary)
            self.assertIsNone(error)
            self.assertEqual(summary, "Default model summary")


class TestVideoDetails(unittest.TestCase):
    """Test suite for video details retrieval"""

    def setUp(self):
        """Set up test data"""
        self.test_video_ids = ["video1", "video2"]

    @patch("youtube_helpers.youtube")
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

    @patch("youtube_helpers.youtube")
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

    @patch("youtube_helpers.youtube")
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

    @patch("youtube_helpers.youtube", None)
    def test_get_videos_from_playlist_error(self):
        """Test playlist retrieval when API fails"""
        # Since youtube is None in test mode, the function returns early
        videos, error = app.get_videos_from_playlist(self.test_playlist_id)

        self.assertIsNone(videos)
        self.assertEqual(error, "YouTube API client not initialized")


if __name__ == "__main__":
    unittest.main()
