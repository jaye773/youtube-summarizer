"""YouTube Data API errors must never expose the API key (it is a URL query parameter)."""

import unittest
from unittest.mock import MagicMock, patch

import httplib2
from googleapiclient.errors import HttpError

import youtube_helpers
from youtube_helpers import redact_api_key

SECRET = "AIzaSyTESTSECRET1234567890"


def http_error(status):
    resp = httplib2.Response({"status": status})
    uri = f"https://youtube.googleapis.com/youtube/v3/videos?part=snippet&id=abc&key={SECRET}&alt=json"
    return HttpError(resp, b'{"error": {"message": "API key not valid"}}', uri=uri)


class TestRedaction(unittest.TestCase):
    def test_redacts_key_query_parameter(self):
        text = redact_api_key(http_error(400))
        self.assertNotIn(SECRET, text)
        self.assertIn("key=<redacted>", text)
        self.assertIn("&alt=json", text)

    def test_leaves_other_text_alone(self):
        self.assertEqual(redact_api_key(ValueError("monkey=1 donkey")), "monkey=1 donkey")

    def test_playlist_error_returned_to_client_has_no_key(self):
        client = MagicMock()
        client.playlistItems.return_value.list.return_value.execute.side_effect = http_error(403)
        with patch.object(youtube_helpers, "youtube", client):
            items, error = youtube_helpers.get_videos_from_playlist("PL123")
        self.assertIsNone(items)
        self.assertNotIn(SECRET, error)

    def test_video_details_log_has_no_key(self):
        client = MagicMock()
        client.videos.return_value.list.return_value.execute.side_effect = http_error(400)
        with patch.object(youtube_helpers, "youtube", client), patch("builtins.print") as mock_print:
            self.assertEqual(youtube_helpers.get_video_details(["abc"]), {})
        logged = " ".join(str(a) for call in mock_print.call_args_list for a in call.args)
        self.assertIn("Error fetching video details", logged)
        self.assertNotIn(SECRET, logged)


if __name__ == "__main__":
    unittest.main()
