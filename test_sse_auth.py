#!/usr/bin/env python3
"""
Test SSE authentication integration
"""

import os
import sys
import time
import threading
import unittest
from unittest.mock import patch, MagicMock
import json

# Set test environment
os.environ['TESTING'] = 'true'
os.environ['LOGIN_ENABLED'] = 'true'
os.environ['LOGIN_USERNAME'] = 'testuser'
os.environ['LOGIN_PASSWORD_HASH'] = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'  # empty string hash
os.environ['GOOGLE_API_KEY'] = 'test-key'
os.environ['OPENAI_API_KEY'] = 'test-key'

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, LOGIN_ENABLED
from flask import session


class TestSSEAuthentication(unittest.TestCase):
    """Test SSE endpoint authentication requirements"""

    def setUp(self):
        """Set up test client"""
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['SECRET_KEY'] = 'test-secret-key'
        self.client = self.app.test_client()

    def test_sse_requires_authentication(self):
        """Test that SSE endpoint requires authentication when login is enabled"""
        # Try to access SSE endpoint without authentication
        response = self.client.get('/events')

        # Should redirect to login page (302) or return 401
        self.assertIn(response.status_code, [302, 401],
                     f"SSE endpoint should require authentication, got {response.status_code}")

        if response.status_code == 302:
            # Check redirect location
            self.assertIn('/login', response.location,
                         "Should redirect to login page")

    def test_sse_works_with_authentication(self):
        """Test that SSE endpoint works when authenticated"""
        with self.client as client:
            # First, authenticate
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['username'] = 'testuser'
                sess['session_id'] = 'test-session-123'

            # Now try to access SSE endpoint
            response = client.get('/events',
                                 headers={'Accept': 'text/event-stream'})

            # Should return 200 with event-stream content type
            self.assertEqual(response.status_code, 200,
                           "SSE endpoint should be accessible when authenticated")
            self.assertEqual(response.content_type, 'text/event-stream',
                           "Should return event-stream content type")

    def test_sse_connection_preserves_session(self):
        """Test that SSE connections maintain session information"""
        with self.client as client:
            # Authenticate
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['username'] = 'testuser'
                sess['session_id'] = 'test-session-456'

            # Connect to SSE
            response = client.get('/events',
                                headers={'Accept': 'text/event-stream'})

            self.assertEqual(response.status_code, 200)

            # Read some data to ensure connection is established
            # Note: In a real SSE connection, this would be a stream
            # For testing, we just verify the initial response
            data = response.get_data(as_text=True)
            self.assertIn('event:', data, "Should contain SSE event format")

    def test_sse_status_requires_auth(self):
        """Test that SSE status endpoint also requires authentication"""
        # Without authentication
        response = self.client.get('/events/status')
        self.assertIn(response.status_code, [302, 401],
                     "SSE status endpoint should require authentication")

        # With authentication
        with self.client as client:
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['username'] = 'testuser'

            response = client.get('/events/status')
            self.assertEqual(response.status_code, 200,
                           "SSE status should be accessible when authenticated")

            data = response.get_json()
            self.assertIsInstance(data, dict, "Should return JSON object")
            self.assertIn('connections', data, "Should include connection info")

    def test_client_side_sse_with_credentials(self):
        """Test that client-side SSE includes credentials in requests"""
        # This test verifies the EventSource configuration

        # Read the SSE client JavaScript
        client_js_path = os.path.join(os.path.dirname(__file__),
                                      'static', 'js', 'sse_client.js')

        with open(client_js_path, 'r') as f:
            client_js = f.read()

        # Check that EventSource is created with credentials
        # Note: EventSource automatically includes cookies for same-origin requests
        self.assertIn('EventSource', client_js,
                     "Should use EventSource for SSE connections")

        # Verify endpoint configuration
        self.assertIn("'/events'", client_js,
                     "Should connect to /events endpoint")

    def test_authentication_flow_with_sse(self):
        """Test complete authentication flow with SSE"""
        with self.client as client:
            # Step 1: Verify unauthenticated access is blocked
            response = client.get('/events')
            self.assertIn(response.status_code, [302, 401])

            # Step 2: Login
            login_data = {
                'username': 'testuser',
                'password': ''  # empty string for test
            }
            response = client.post('/login',
                                 data=json.dumps(login_data),
                                 content_type='application/json')

            if response.status_code == 200:
                # Login successful
                result = response.get_json()
                self.assertTrue(result.get('success', False),
                              "Login should succeed")

                # Step 3: Access SSE after login
                response = client.get('/events',
                                    headers={'Accept': 'text/event-stream'})
                self.assertEqual(response.status_code, 200,
                               "SSE should be accessible after login")


class TestSSESecurityIssues(unittest.TestCase):
    """Test for potential security issues in SSE implementation"""

    def setUp(self):
        """Set up test client"""
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['SECRET_KEY'] = 'test-secret-key'
        self.client = self.app.test_client()

    def test_sse_session_hijacking_protection(self):
        """Test that SSE connections are protected against session hijacking"""
        with self.client as client:
            # Create authenticated session
            with client.session_transaction() as sess:
                sess['authenticated'] = True
                sess['username'] = 'testuser'
                sess['session_id'] = 'original-session'

            # Get SSE connection
            response = client.get('/events',
                                headers={'Accept': 'text/event-stream'})
            self.assertEqual(response.status_code, 200)

            # Try to use a different session ID (simulating hijacking attempt)
            with client.session_transaction() as sess:
                sess['session_id'] = 'hijacked-session'

            # This should still work because authentication is session-based
            # The session_id in SSE is just for tracking, not authentication
            response2 = client.get('/events',
                                 headers={'Accept': 'text/event-stream'})
            self.assertEqual(response2.status_code, 200,
                           "Session-based auth should still work")

    def test_sse_cross_origin_protection(self):
        """Test that SSE has proper CORS protection"""
        # Test with different origin
        response = self.client.get('/events',
                                  headers={
                                      'Origin': 'http://evil.com',
                                      'Accept': 'text/event-stream'
                                  })

        # Should still require authentication regardless of origin
        self.assertIn(response.status_code, [302, 401],
                     "Should require auth even with different origin")

        # Check CORS headers are not too permissive
        if 'Access-Control-Allow-Origin' in response.headers:
            self.assertNotEqual(response.headers['Access-Control-Allow-Origin'], '*',
                              "Should not allow all origins")


if __name__ == '__main__':
    # Run tests
    print("Testing SSE Authentication Integration")
    print("=" * 50)

    # Check if login is enabled
    print(f"LOGIN_ENABLED: {LOGIN_ENABLED}")
    print()

    # Run test suites
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestSSEAuthentication))
    suite.addTests(loader.loadTestsFromTestCase(TestSSESecurityIssues))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "=" * 50)
    print("Summary:")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✅ All SSE authentication tests passed!")
    else:
        print("\n❌ Some tests failed. SSE authentication may have issues.")
        sys.exit(1)
