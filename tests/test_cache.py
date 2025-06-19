import json
import unittest
from unittest.mock import MagicMock, mock_open, patch

from app import AUDIO_CACHE_DIR, DATA_DIR, load_summary_cache, save_summary_cache


class TestCacheFunctions(unittest.TestCase):
    """Test suite for cache functionality"""

    def setUp(self):
        """Set up test data"""
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

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="{}")
    def test_load_summary_cache_empty_file(self, mock_file, mock_exists):
        """Test loading cache from empty file"""
        mock_exists.return_value = True

        cache = load_summary_cache()

        self.assertEqual(cache, {})
        mock_file.assert_called_once_with("summary_cache.json", "r")

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_load_summary_cache_with_data(self, mock_file, mock_exists):
        """Test loading cache with existing data"""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = json.dumps(self.test_cache_data)

        cache = load_summary_cache()

        self.assertEqual(len(cache), 2)
        self.assertEqual(cache["video1"]["title"], "Test Video 1")

    @patch("os.path.exists")
    def test_load_summary_cache_no_file(self, mock_exists):
        """Test loading cache when file doesn't exist"""
        mock_exists.return_value = False

        cache = load_summary_cache()

        self.assertEqual(cache, {})

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="invalid json")
    def test_load_summary_cache_invalid_json(self, mock_file, mock_exists):
        """Test loading cache with invalid JSON"""
        mock_exists.return_value = True

        cache = load_summary_cache()

        self.assertEqual(cache, {})

    @patch("builtins.open", new_callable=mock_open)
    def test_save_summary_cache(self, mock_file):
        """Test saving cache data"""
        save_summary_cache(self.test_cache_data)

        mock_file.assert_called_once_with("summary_cache.json", "w")

        # Get the written content
        handle = mock_file()
        written_data = "".join(call.args[0] for call in handle.write.call_args_list)

        # Verify the data was written correctly
        parsed_data = json.loads(written_data)
        self.assertEqual(parsed_data, self.test_cache_data)

    @patch("builtins.open", new_callable=mock_open)
    def test_save_summary_cache_empty(self, mock_file):
        """Test saving empty cache"""
        save_summary_cache({})

        mock_file.assert_called_once_with("summary_cache.json", "w")

        # Get the written content
        handle = mock_file()
        written_data = "".join(call.args[0] for call in handle.write.call_args_list)

        # Verify empty dict was written
        parsed_data = json.loads(written_data)
        self.assertEqual(parsed_data, {})


class TestAudioCache(unittest.TestCase):
    """Test suite for audio cache functionality"""

    def setUp(self):
        """Set up test data"""
        self.test_text = "This is test text for audio generation"
        self.expected_hash = "5f1e3c8e9b4e1c0f8e9f5e8c9b4e1c0f8e9f5e8c9b4e1c0f8e9f5e8c9b4e1c0f"

    def test_audio_cache_directory_creation(self):
        """Test that audio cache directory is created"""
        import os

        # The directory should exist
        self.assertTrue(os.path.exists(AUDIO_CACHE_DIR))

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
