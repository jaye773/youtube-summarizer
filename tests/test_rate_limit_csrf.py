"""Tests for per-IP rate limiting and CSRF protections (JSON-only state changes, cookie flags)."""

import json
import os
import unittest
from unittest.mock import patch

import app as app_module
from app import app, limiter


class RateLimitTestCase(unittest.TestCase):
    """Base class: rate limiting switched on with a clean in-memory store."""

    def setUp(self):
        os.environ["TESTING"] = "true"
        app.config["TESTING"] = True
        app.config["RATE_LIMIT_ENABLED"] = True
        limiter.reset()
        self.client = app.test_client()

    def tearDown(self):
        app.config["RATE_LIMIT_ENABLED"] = False
        limiter.reset()

    def post_json(self, path, payload, ip="10.0.0.1", headers=None):
        return self.client.post(path, json=payload, environ_base={"REMOTE_ADDR": ip}, headers=headers or {})


class TestRateLimiting(RateLimitTestCase):
    @patch("app.RATE_LIMIT_SUMMARIZE", "2 per minute")
    def test_summarize_returns_json_429_after_limit(self):
        # Empty URL list is rejected (400) without calling any API, but still counts
        for _ in range(2):
            self.assertEqual(self.post_json("/summarize", {"urls": []}).status_code, 400)

        response = self.post_json("/summarize", {"urls": []})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.content_type, "application/json")
        data = response.get_json()
        self.assertIn("Too many requests", data["error"])
        self.assertIn("2 per 1 minute", data["limit"])
        self.assertIn("Retry-After", response.headers)

    @patch("app.RATE_LIMIT_SUMMARIZE", "2 per minute")
    def test_different_ips_are_counted_separately(self):
        for _ in range(2):
            self.post_json("/summarize", {"urls": []}, ip="10.0.0.1")
        self.assertEqual(self.post_json("/summarize", {"urls": []}, ip="10.0.0.1").status_code, 429)
        self.assertEqual(self.post_json("/summarize", {"urls": []}, ip="10.0.0.2").status_code, 400)

    @patch("app.RATE_LIMIT_SUMMARIZE", "2 per minute")
    def test_spoofed_x_forwarded_for_does_not_bypass_limit(self):
        """Without TRUST_PROXY_HOPS, X-Forwarded-For is ignored, so rotating it doesn't reset the limit."""
        for i in range(2):
            self.post_json("/summarize", {"urls": []}, headers={"X-Forwarded-For": f"203.0.113.{i}"})
        response = self.post_json("/summarize", {"urls": []}, headers={"X-Forwarded-For": "203.0.113.99"})
        self.assertEqual(response.status_code, 429)

    @patch("app.RATE_LIMIT_TTS", "2 per minute")
    def test_speak_and_preview_voice_share_tts_budget(self):
        self.assertEqual(self.post_json("/speak", {}).status_code, 400)
        self.assertEqual(self.post_json("/preview-voice", {}).status_code, 400)
        response = self.post_json("/preview-voice", {"voice_id": "x", "text": "hi"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(self.post_json("/speak", {}).status_code, 429)

    @patch("app.RATE_LIMIT_TTS", "2 per minute")
    @patch("app.RATE_LIMIT_SUMMARIZE", "2 per minute")
    def test_summarize_and_tts_budgets_are_independent(self):
        for _ in range(2):
            self.post_json("/summarize", {"urls": []})
        self.assertEqual(self.post_json("/summarize", {"urls": []}).status_code, 429)
        self.assertEqual(self.post_json("/speak", {}).status_code, 400)

    @patch("app.RATE_LIMIT_LOGIN", "2 per minute")
    def test_login_post_is_rate_limited(self):
        with patch("app.LOGIN_ENABLED", True), patch("app.LOGIN_CODE", "secret"):
            for _ in range(2):
                self.assertEqual(self.post_json("/login", {"passcode": "wrong"}).status_code, 401)
            response = self.post_json("/login", {"passcode": "secret"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.content_type, "application/json")

    @patch("app.RATE_LIMIT_SUMMARIZE", "")
    def test_empty_limit_string_disables_that_limit(self):
        for _ in range(15):
            self.assertEqual(self.post_json("/summarize", {"urls": []}).status_code, 400)

    @patch("app.RATE_LIMIT_SUMMARIZE", "1 per minute")
    def test_rate_limit_enabled_false_disables_limiting(self):
        app.config["RATE_LIMIT_ENABLED"] = False
        for _ in range(5):
            self.assertEqual(self.post_json("/summarize", {"urls": []}).status_code, 400)

    @patch("app.RATE_LIMIT_SUMMARIZE", "1 per minute")
    def test_unlimited_endpoints_are_not_affected(self):
        self.post_json("/summarize", {"urls": []})
        self.assertEqual(self.post_json("/summarize", {"urls": []}).status_code, 429)
        response = self.client.get("/api_status", environ_base={"REMOTE_ADDR": "10.0.0.1"})
        self.assertEqual(response.status_code, 200)

    def test_invalid_limit_string_falls_back_to_default(self):
        with patch.dict(os.environ, {"RATE_LIMIT_TTS": "lots please"}):
            self.assertEqual(
                app_module._read_rate_limit("RATE_LIMIT_TTS"), app_module.RATE_LIMIT_DEFAULTS["RATE_LIMIT_TTS"]
            )
        with patch.dict(os.environ, {"RATE_LIMIT_TTS": "  "}):
            self.assertEqual(app_module._read_rate_limit("RATE_LIMIT_TTS"), "")
        with patch.dict(os.environ, {"RATE_LIMIT_TTS": "5/second"}):
            self.assertEqual(app_module._read_rate_limit("RATE_LIMIT_TTS"), "5/second")


class TestCsrfProtection(unittest.TestCase):
    """State-changing endpoints must reject non-JSON bodies, which is all a cross-site form can send."""

    def setUp(self):
        os.environ["TESTING"] = "true"
        app.config["TESTING"] = True
        self.client = app.test_client()

    def login_enabled_session(self):
        """Simulate a logged-in user with real auth enforcement (no TESTING bypass)."""
        os.environ.pop("TESTING", None)
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True

    def tearDown(self):
        os.environ.pop("TESTING", None)

    @patch("app.save_env_to_file")
    def test_cross_site_text_plain_settings_post_is_rejected(self, mock_save):
        """<form enctype="text/plain"> can produce a JSON-looking body; it must not be parsed."""
        with patch("app.LOGIN_ENABLED", True):
            self.login_enabled_session()
            response = self.client.post(
                "/settings",
                data='{"login_code": "attacker", "x": "="}',
                content_type="text/plain",
                headers={"Origin": "https://evil.example"},
            )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.get_json()["error"], "Content-Type must be application/json")
        mock_save.assert_not_called()

    def test_cross_site_text_plain_delete_summary_is_rejected(self):
        cache = {"vid1": {"title": "t", "summary": "s"}}
        with patch("app.LOGIN_ENABLED", True), patch("app.summary_cache", cache), patch("app.save_summary_cache"):
            self.login_enabled_session()
            response = self.client.delete("/delete_summary", data='{"video_id": "vid1"}', content_type="text/plain")
            self.assertEqual(response.status_code, 415)
            self.assertIn("vid1", cache)

    def test_form_encoded_posts_are_rejected(self):
        for path in ("/summarize", "/speak", "/preview-voice", "/settings", "/login", "/api/cache/cleanup"):
            response = self.client.post(path, data={"urls": "https://youtu.be/dQw4w9WgXcQ"})
            self.assertEqual(response.status_code, 415, path)
            self.assertEqual(response.content_type, "application/json", path)

    def test_logout_requires_json_content_type(self):
        with patch("app.LOGIN_ENABLED", True):
            self.login_enabled_session()
            # Bodyless cross-site POST (form or no-cors fetch) is rejected; session survives
            self.assertEqual(self.client.post("/logout").status_code, 415)
            with self.client.session_transaction() as sess:
                self.assertTrue(sess.get("authenticated"))
            # The app's own JSON request works
            response = self.client.post("/logout", json={})
            self.assertEqual(response.status_code, 200)
            with self.client.session_transaction() as sess:
                self.assertFalse(sess.get("authenticated"))

    @patch("app.save_env_to_file", return_value=True)
    def test_json_settings_post_still_works(self, _mock_save):
        with patch("app.LOGIN_ENABLED", True), patch("app.configure_auth"), patch.dict(os.environ, {}, clear=False):
            self.login_enabled_session()
            response = self.client.post("/settings", data=json.dumps({"max_login_attempts": "6"}),
                                        content_type="application/json")
        self.assertEqual(response.status_code, 200)

    def test_malformed_json_is_400_not_500(self):
        for path in ("/summarize", "/speak", "/preview-voice", "/settings"):
            response = self.client.post(path, data="{not json", content_type="application/json")
            self.assertEqual(response.status_code, 400, path)
            self.assertEqual(response.get_json()["error"], "Invalid JSON in request body", path)

    def test_get_requests_are_unaffected(self):
        self.assertEqual(self.client.get("/api_status").status_code, 200)

    def test_session_cookie_flags(self):
        self.assertEqual(app.config["SESSION_COOKIE_SAMESITE"], "Lax")
        self.assertTrue(app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertFalse(app.config["SESSION_COOKIE_SECURE"])  # opt-in via SESSION_COOKIE_SECURE
        response = self.client.get("/api_status")
        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)


if __name__ == "__main__":
    unittest.main()
