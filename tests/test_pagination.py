import json
import os
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from app import app


class TestPagination(unittest.TestCase):
    """Test suite for pagination functionality in YouTube Summarizer"""

    def setUp(self):
        """Set up test client and test data"""
        self.app = app
        self.client = self.app.test_client()
        self.app.config["TESTING"] = True
        # Set environment variable to bypass authentication during testing
        os.environ["TESTING"] = "true"

        # Create mock cache with multiple videos for pagination testing
        self.mock_cache = {}
        for i in range(1, 26):  # Create 25 videos for testing
            timestamp = datetime(2024, 1, i, 12, 0, 0, tzinfo=timezone.utc).isoformat()
            self.mock_cache[f"video{i:02d}"] = {
                "title": f"Video {i:02d}",
                "thumbnail_url": f"http://example.com/thumb{i:02d}.jpg",
                "summary": f"This is a summary for video {i:02d}",
                "summarized_at": timestamp,
                "video_url": f"https://www.youtube.com/watch?v=video{i:02d}",
            }

    def tearDown(self):
        """Clean up after each test"""
        if "TESTING" in os.environ:
            del os.environ["TESTING"]

    def test_pagination_default_parameters(self):
        """Test pagination with default parameters (page=1, per_page=10)"""
        with patch("app.summary_cache", self.mock_cache):
            response = self.client.get("/get_cached_summaries?page=1&per_page=10")
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertIsInstance(data, dict)
            self.assertEqual(data["page"], 1)
            self.assertEqual(data["per_page"], 10)
            self.assertEqual(data["total"], 25)
            self.assertEqual(data["total_pages"], 3)
            self.assertEqual(len(data["summaries"]), 10)
            
            # Should be sorted by date (most recent first)
            self.assertEqual(data["summaries"][0]["title"], "Video 25")
            self.assertEqual(data["summaries"][9]["title"], "Video 16")

    def test_pagination_second_page(self):
        """Test pagination second page"""
        with patch("app.summary_cache", self.mock_cache):
            response = self.client.get("/get_cached_summaries?page=2&per_page=10")
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertEqual(data["page"], 2)
            self.assertEqual(data["per_page"], 10)
            self.assertEqual(data["total"], 25)
            self.assertEqual(data["total_pages"], 3)
            self.assertEqual(len(data["summaries"]), 10)
            
            # Second page should have videos 15-6
            self.assertEqual(data["summaries"][0]["title"], "Video 15")
            self.assertEqual(data["summaries"][9]["title"], "Video 06")

    def test_pagination_last_page_partial(self):
        """Test pagination last page with partial results"""
        with patch("app.summary_cache", self.mock_cache):
            response = self.client.get("/get_cached_summaries?page=3&per_page=10")
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertEqual(data["page"], 3)
            self.assertEqual(data["per_page"], 10)
            self.assertEqual(data["total"], 25)
            self.assertEqual(data["total_pages"], 3)
            self.assertEqual(len(data["summaries"]), 5)  # Only 5 items on last page
            
            # Last page should have videos 5-1
            self.assertEqual(data["summaries"][0]["title"], "Video 05")
            self.assertEqual(data["summaries"][4]["title"], "Video 01")

    def test_pagination_different_page_sizes(self):
        """Test pagination with different page sizes"""
        with patch("app.summary_cache", self.mock_cache):
            # Test with page size 20
            response = self.client.get("/get_cached_summaries?page=1&per_page=20")
            data = json.loads(response.data)
            self.assertEqual(data["per_page"], 20)
            self.assertEqual(data["total_pages"], 2)  # 25 items / 20 per page = 2 pages
            self.assertEqual(len(data["summaries"]), 20)
            
            # Test with page size 50
            response = self.client.get("/get_cached_summaries?page=1&per_page=50")
            data = json.loads(response.data)
            self.assertEqual(data["per_page"], 50)
            self.assertEqual(data["total_pages"], 1)  # All items fit on one page
            self.assertEqual(len(data["summaries"]), 25)
            
            # Test with page size 100
            response = self.client.get("/get_cached_summaries?page=1&per_page=100")
            data = json.loads(response.data)
            self.assertEqual(data["per_page"], 100)
            self.assertEqual(data["total_pages"], 1)
            self.assertEqual(len(data["summaries"]), 25)

    def test_pagination_page_size_limits(self):
        """Test pagination page size validation and limits"""
        with patch("app.summary_cache", self.mock_cache):
            # Test page size over limit (should be capped at 100)
            response = self.client.get("/get_cached_summaries?page=1&per_page=150")
            data = json.loads(response.data)
            self.assertEqual(data["per_page"], 100)  # Should be capped
            
            # Test invalid page size (should default to 10)
            response = self.client.get("/get_cached_summaries?page=1&per_page=0")
            data = json.loads(response.data)
            self.assertEqual(data["per_page"], 10)  # Should default
            
            # Test negative page size (should default to 10)
            response = self.client.get("/get_cached_summaries?page=1&per_page=-5")
            data = json.loads(response.data)
            self.assertEqual(data["per_page"], 10)  # Should default

    def test_pagination_invalid_page_numbers(self):
        """Test pagination with invalid page numbers"""
        with patch("app.summary_cache", self.mock_cache):
            # Test page 0 (should default to 1)
            response = self.client.get("/get_cached_summaries?page=0&per_page=10")
            data = json.loads(response.data)
            self.assertEqual(data["page"], 1)  # Should default to 1
            
            # Test negative page (should default to 1)
            response = self.client.get("/get_cached_summaries?page=-1&per_page=10")
            data = json.loads(response.data)
            self.assertEqual(data["page"], 1)  # Should default to 1
            
            # Test page beyond available pages (should still work, just return empty)
            response = self.client.get("/get_cached_summaries?page=10&per_page=10")
            data = json.loads(response.data)
            self.assertEqual(data["page"], 10)
            self.assertEqual(len(data["summaries"]), 0)  # No items on this page

    def test_backward_compatibility_with_limit(self):
        """Test that old limit parameter still works (backward compatibility)"""
        with patch("app.summary_cache", self.mock_cache):
            # Test with limit parameter (old format)
            response = self.client.get("/get_cached_summaries?limit=5")
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            # Should return old array format, not pagination object
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 5)
            
            # Should be sorted by date (most recent first)
            self.assertEqual(data[0]["title"], "Video 25")
            self.assertEqual(data[4]["title"], "Video 21")

    def test_backward_compatibility_limit_zero(self):
        """Test backward compatibility with limit=0"""
        with patch("app.summary_cache", self.mock_cache):
            response = self.client.get("/get_cached_summaries?limit=0")
            data = json.loads(response.data)
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 0)

    def test_pagination_empty_cache(self):
        """Test pagination with empty cache"""
        with patch("app.summary_cache", {}):
            response = self.client.get("/get_cached_summaries?page=1&per_page=10")
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertEqual(data["summaries"], [])
            self.assertEqual(data["total"], 0)
            self.assertEqual(data["page"], 1)
            self.assertEqual(data["per_page"], 10)
            self.assertEqual(data["total_pages"], 0)

    def test_pagination_response_structure(self):
        """Test that pagination response has correct structure"""
        with patch("app.summary_cache", self.mock_cache):
            response = self.client.get("/get_cached_summaries?page=1&per_page=10")
            data = json.loads(response.data)

            # Check required fields
            required_fields = ["summaries", "total", "page", "per_page", "total_pages"]
            for field in required_fields:
                self.assertIn(field, data)

            # Check data types
            self.assertIsInstance(data["summaries"], list)
            self.assertIsInstance(data["total"], int)
            self.assertIsInstance(data["page"], int)
            self.assertIsInstance(data["per_page"], int)
            self.assertIsInstance(data["total_pages"], int)

            # Check summary structure
            if data["summaries"]:
                summary = data["summaries"][0]
                required_summary_fields = ["type", "video_id", "title", "thumbnail_url",
                                         "summary", "summarized_at", "video_url", "error"]
                for field in required_summary_fields:
                    self.assertIn(field, summary)

    def test_pagination_integration_with_frontend_expectations(self):
        """Test that pagination API meets frontend JavaScript expectations"""
        with patch("app.summary_cache", self.mock_cache):
            # Test what frontend loadPaginatedSummaries function expects
            response = self.client.get("/get_cached_summaries?page=1&per_page=10")
            self.assertEqual(response.status_code, 200)

            data = json.loads(response.data)

            # Frontend expects these exact fields for updatePaginationUI
            self.assertIn("total", data)
            self.assertIn("page", data)
            self.assertIn("total_pages", data)
            self.assertIn("summaries", data)

            # Frontend expects summaries to be an array that can be passed to displayResults
            self.assertIsInstance(data["summaries"], list)

            # Test edge case: empty page
            response = self.client.get("/get_cached_summaries?page=10&per_page=10")
            data = json.loads(response.data)
            self.assertEqual(data["page"], 10)
            self.assertEqual(len(data["summaries"]), 0)
            self.assertEqual(data["total"], 25)  # Total should still be correct

    def test_pagination_math_accuracy(self):
        """Test that pagination calculations are mathematically correct"""
        with patch("app.summary_cache", self.mock_cache):
            # Test various page sizes and verify math
            test_cases = [
                {"per_page": 10, "expected_pages": 3},  # 25 items / 10 = 3 pages
                {"per_page": 20, "expected_pages": 2},  # 25 items / 20 = 2 pages
                {"per_page": 25, "expected_pages": 1},  # 25 items / 25 = 1 page
                {"per_page": 50, "expected_pages": 1},  # 25 items / 50 = 1 page
            ]

            for case in test_cases:
                response = self.client.get(f"/get_cached_summaries?page=1&per_page={case['per_page']}")
                data = json.loads(response.data)
                self.assertEqual(data["total_pages"], case["expected_pages"],
                               f"Failed for per_page={case['per_page']}")
                self.assertEqual(data["total"], 25)

                # Test that all pages combined contain all items
                all_items = []
                for page in range(1, data["total_pages"] + 1):
                    page_response = self.client.get(f"/get_cached_summaries?page={page}&per_page={case['per_page']}")
                    page_data = json.loads(page_response.data)
                    all_items.extend(page_data["summaries"])

                self.assertEqual(len(all_items), 25, f"Total items mismatch for per_page={case['per_page']}")


if __name__ == "__main__":
    unittest.main()
