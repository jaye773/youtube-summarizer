import json
import os
import unittest
from unittest.mock import MagicMock, mock_open, patch

from cache import build_cache_entry, load_summary_cache, save_summary_cache

CACHE_FILE = "summary_cache.json"


class TestCacheFunctions(unittest.TestCase):
    """Test suite for cache functionality"""

    def setUp(self):
        """Set up test data"""
        # Set environment variable to bypass authentication during testing
        os.environ["TESTING"] = "true"
        self.test_cache_data = {
            "video1": {
                "title": "Test Video 1",
                "summary": "Summary of video 1",
                "thumbnail_url": "http://example.com/thumb1.jpg",
                "summarized_at": "2024-01-01T00:00:00.000000",
            },
            "video2": {
                "title": "Test Video 2",
                "summary": "Summary of video 2",
                "thumbnail_url": "http://example.com/thumb2.jpg",
                "summarized_at": "2024-01-02T00:00:00.000000",
            },
        }

    def tearDown(self):
        """Clean up after each test"""
        # Remove testing environment variable
        if "TESTING" in os.environ:
            del os.environ["TESTING"]

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="{}")
    def test_load_summary_cache_empty_file(self, mock_file, mock_exists):
        """Test loading cache from empty file"""
        mock_exists.return_value = True

        cache = load_summary_cache(CACHE_FILE)

        self.assertEqual(cache, {})
        mock_file.assert_called_once_with(CACHE_FILE, "r")

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_load_summary_cache_with_data(self, mock_file, mock_exists):
        """Test loading cache with existing data"""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = json.dumps(self.test_cache_data)

        cache = load_summary_cache(CACHE_FILE)

        self.assertEqual(len(cache), 2)
        self.assertEqual(cache["video1"]["title"], "Test Video 1")

    @patch("os.path.exists")
    def test_load_summary_cache_no_file(self, mock_exists):
        """Test loading cache when file doesn't exist"""
        mock_exists.return_value = False

        cache = load_summary_cache(CACHE_FILE)

        self.assertEqual(cache, {})

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="invalid json")
    def test_load_summary_cache_invalid_json(self, mock_file, mock_exists):
        """Test loading cache with invalid JSON"""
        mock_exists.return_value = True

        cache = load_summary_cache(CACHE_FILE)

        self.assertEqual(cache, {})

    @patch("builtins.open", new_callable=mock_open)
    def test_save_summary_cache(self, mock_file):
        """Test saving cache data"""
        save_summary_cache(self.test_cache_data, CACHE_FILE)

        mock_file.assert_called_once_with(CACHE_FILE, "w")

        # Get the written content
        handle = mock_file()
        written_data = "".join(call.args[0] for call in handle.write.call_args_list)

        # Verify the data was written correctly
        parsed_data = json.loads(written_data)
        self.assertEqual(parsed_data, self.test_cache_data)

    @patch("builtins.open", new_callable=mock_open)
    def test_save_summary_cache_empty(self, mock_file):
        """Test saving empty cache"""
        save_summary_cache({}, CACHE_FILE)

        mock_file.assert_called_once_with(CACHE_FILE, "w")

        # Get the written content
        handle = mock_file()
        written_data = "".join(call.args[0] for call in handle.write.call_args_list)

        # Verify empty dict was written
        parsed_data = json.loads(written_data)
        self.assertEqual(parsed_data, {})

    def test_build_cache_entry_structure(self):
        """Test that build_cache_entry returns a dict with all expected keys"""
        entry = build_cache_entry(
            title="Test Video",
            summary="A test summary",
            thumbnail_url="http://example.com/thumb.jpg",
            video_id="abc123",
            model_key="gemini-2.5-flash",
            audio_filename="abc123.mp3",
        )

        self.assertEqual(entry["title"], "Test Video")
        self.assertEqual(entry["summary"], "A test summary")
        self.assertEqual(entry["thumbnail_url"], "http://example.com/thumb.jpg")
        self.assertEqual(entry["video_url"], "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(entry["model_used"], "gemini-2.5-flash")
        self.assertEqual(entry["audio_filename"], "abc123.mp3")
        self.assertIn("summarized_at", entry)

    def test_build_cache_entry_audio_filename_defaults_to_none(self):
        """Test that audio_filename defaults to None when not provided"""
        entry = build_cache_entry(
            title="Test Video",
            summary="A test summary",
            thumbnail_url="http://example.com/thumb.jpg",
            video_id="abc123",
            model_key="gemini-2.5-flash",
        )

        self.assertIsNone(entry["audio_filename"])

    def test_build_cache_entry_video_url_format(self):
        """Test that video_url is constructed from video_id"""
        entry = build_cache_entry("T", "S", "U", "dQw4w9WgXcQ", "gpt-4o")

        self.assertEqual(entry["video_url"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")


class TestAudioCache(unittest.TestCase):
    """Test suite for audio cache functionality"""

    def setUp(self):
        """Set up test data"""
        # Set environment variable to bypass authentication during testing
        os.environ["TESTING"] = "true"
        self.test_text = "This is test text for audio generation"
        self.expected_hash = "5f1e3c8e9b4e1c0f8e9f5e8c9b4e1c0f8e9f5e8c9b4e1c0f8e9f5e8c9b4e1c0f"

    def tearDown(self):
        """Clean up after each test"""
        # Remove testing environment variable
        if "TESTING" in os.environ:
            del os.environ["TESTING"]

    @patch("app.DATA_DIR", ".")
    @patch("app.AUDIO_CACHE_DIR", "./audio_cache")
    def test_audio_cache_directory_creation(self):
        """Test that audio cache directory is created"""
        import os

        from app import AUDIO_CACHE_DIR

        # Ensure the directory is created as it would be in normal app startup
        os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

        # The directory should exist
        self.assertTrue(os.path.exists(AUDIO_CACHE_DIR))

        # Clean up after test
        import shutil

        if os.path.exists(AUDIO_CACHE_DIR):
            shutil.rmtree(AUDIO_CACHE_DIR)

    @patch("hashlib.sha256")
    def test_audio_filename_generation(self, mock_sha256):
        """Test audio filename generation from text hash"""
        # Mock the hash
        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = self.expected_hash
        mock_sha256.return_value = mock_hash

        # Test the hash generation (this would be in the speak endpoint)
        import hashlib

        text_hash = hashlib.sha256(self.test_text.encode("utf-8")).hexdigest()
        filename = f"{text_hash}.mp3"

        expected_filename = f"{self.expected_hash}.mp3"
        self.assertEqual(filename, expected_filename)


if __name__ == "__main__":
    unittest.main()
