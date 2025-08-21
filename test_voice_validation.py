#!/usr/bin/env python3
"""
Comprehensive validation tests for voice model selection feature
Tests API endpoints, settings integration, UX flow, and edge cases
"""

import os
import sys
import json
import time
import hashlib
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Set testing mode before imports
os.environ["TESTING"] = "true"

# Import app components
import app
from voice_config import (
    AVAILABLE_VOICES, DEFAULT_VOICE, get_voice_config,
    get_voice_with_fallback, validate_voice_name, get_sample_text,
    get_optimized_cache_key, get_fallback_voice
)

class VoiceValidationTestCase(unittest.TestCase):
    """Base test case with app setup"""

    def setUp(self):
        """Set up test environment"""
        app.app.config['TESTING'] = True
        self.client = app.app.test_client()
        self.app_context = app.app.app_context()
        self.app_context.push()

        # Store original environment variables
        self.original_tts_voice = os.environ.get('TTS_VOICE')
        self.original_app_tts_voice = app.TTS_VOICE

        # Reset to default voice for each test
        os.environ['TTS_VOICE'] = DEFAULT_VOICE
        app.TTS_VOICE = DEFAULT_VOICE

        # Create temporary directories for testing
        self.temp_dir = tempfile.mkdtemp()
        self.audio_cache_dir = os.path.join(self.temp_dir, "audio_cache")
        os.makedirs(self.audio_cache_dir, exist_ok=True)

        # Override cache directory
        app.AUDIO_CACHE_DIR = self.audio_cache_dir

    def tearDown(self):
        """Clean up test environment"""
        # Restore original environment variables
        if self.original_tts_voice is not None:
            os.environ['TTS_VOICE'] = self.original_tts_voice
        elif 'TTS_VOICE' in os.environ:
            del os.environ['TTS_VOICE']

        app.TTS_VOICE = self.original_app_tts_voice

        self.app_context.pop()

        # Clean up temp files
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

class TestVoiceAPIEndpoints(VoiceValidationTestCase):
    """Test voice-related API endpoints"""

    def test_get_voices_endpoint(self):
        """Test /api/voices endpoint returns correct structure"""
        response = self.client.get('/api/voices')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        # Validate response structure
        self.assertIn('voices', data)
        self.assertIn('tiers', data)
        self.assertIn('current_voice', data)
        self.assertIn('default_voice', data)

        # Validate voices data
        self.assertEqual(len(data['voices']), 10)
        self.assertEqual(data['default_voice'], DEFAULT_VOICE)

        # Validate tier organization
        tiers = data['tiers']
        self.assertIn('chirp3-hd', tiers)
        self.assertIn('neural2', tiers)
        self.assertIn('studio', tiers)
        self.assertIn('wavenet', tiers)

        # Validate voice structure
        for voice_id, voice_data in data['voices'].items():
            required_fields = ['name', 'display_name', 'language_code', 'gender',
                             'accent', 'style', 'tier', 'description', 'quality']
            for field in required_fields:
                self.assertIn(field, voice_data, f"Voice {voice_id} missing {field}")

    @patch('app.tts_client')
    def test_preview_voice_endpoint(self, mock_tts_client):
        """Test /preview-voice endpoint with valid voice"""
        # Mock TTS response
        mock_response = Mock()
        mock_response.audio_content = b"fake_audio_data"
        mock_tts_client.synthesize_speech.return_value = mock_response

        payload = {
            'voice_id': 'en-US-Chirp3-HD-Zephyr',
            'text': 'Test preview text'
        }

        response = self.client.post('/preview-voice',
                                   data=json.dumps(payload),
                                   content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'audio/mpeg')
        self.assertEqual(response.data, b"fake_audio_data")

    def test_preview_voice_invalid_voice_id(self):
        """Test /preview-voice with invalid voice ID"""
        payload = {
            'voice_id': 'invalid-voice-id',
            'text': 'Test text'
        }

        response = self.client.post('/preview-voice',
                                   data=json.dumps(payload),
                                   content_type='application/json')

        # Should still work due to fallback mechanism
        # Check that it doesn't return 500 error
        self.assertNotEqual(response.status_code, 500)

    def test_preview_voice_missing_params(self):
        """Test /preview-voice with missing parameters"""
        # Missing voice_id
        response = self.client.post('/preview-voice',
                                   data=json.dumps({'text': 'Test'}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 400)

        # Missing text
        response = self.client.post('/preview-voice',
                                   data=json.dumps({'voice_id': 'test'}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_preview_voice_text_length_limit(self):
        """Test preview text is truncated at 500 characters"""
        long_text = "A" * 600  # 600 characters

        with patch('app.tts_client') as mock_tts_client:
            mock_response = Mock()
            mock_response.audio_content = b"fake_audio"
            mock_tts_client.synthesize_speech.return_value = mock_response

            payload = {
                'voice_id': 'en-US-Chirp3-HD-Zephyr',
                'text': long_text
            }

            response = self.client.post('/preview-voice',
                                       data=json.dumps(payload),
                                       content_type='application/json')

            # Should succeed (truncated)
            self.assertEqual(response.status_code, 200)

            # Verify truncation occurred in the call
            mock_tts_client.synthesize_speech.assert_called()
            call_args = mock_tts_client.synthesize_speech.call_args
            synthesis_input = call_args[1]['input']
            self.assertLessEqual(len(synthesis_input.text), 503)  # 500 + "..."

    @patch('app.tts_client')
    def test_speak_endpoint_with_voice_selection(self, mock_tts_client):
        """Test /speak endpoint respects voice selection"""
        mock_response = Mock()
        mock_response.audio_content = b"synthesized_audio"
        mock_tts_client.synthesize_speech.return_value = mock_response

        # Test with specific voice
        payload = {
            'text': 'Test summary text',
            'voice_id': 'en-US-Neural2-J'
        }

        response = self.client.post('/speak',
                                   data=json.dumps(payload),
                                   content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'audio/mpeg')

        # Verify correct voice was used
        mock_tts_client.synthesize_speech.assert_called()
        call_args = mock_tts_client.synthesize_speech.call_args
        voice_params = call_args[1]['voice']
        self.assertEqual(voice_params.name, 'en-US-Neural2-J')

    @patch('app.tts_client')
    def test_speak_endpoint_fallback_to_default(self, mock_tts_client):
        """Test /speak endpoint falls back when voice_id not provided"""
        mock_response = Mock()
        mock_response.audio_content = b"synthesized_audio"
        mock_tts_client.synthesize_speech.return_value = mock_response

        # Test without voice_id (should use TTS_VOICE)
        payload = {'text': 'Test summary text'}

        response = self.client.post('/speak',
                                   data=json.dumps(payload),
                                   content_type='application/json')

        self.assertEqual(response.status_code, 200)

        # Should use the configured TTS_VOICE
        mock_tts_client.synthesize_speech.assert_called()
        call_args = mock_tts_client.synthesize_speech.call_args
        voice_params = call_args[1]['voice']
        self.assertEqual(voice_params.name, app.TTS_VOICE)

class TestSettingsIntegration(VoiceValidationTestCase):
    """Test voice settings integration and persistence"""

    def test_settings_page_displays_current_voice(self):
        """Test settings page shows current voice selection"""
        response = self.client.get('/settings')
        self.assertEqual(response.status_code, 200)

        # Check that current voice is marked as selected
        html_content = response.data.decode('utf-8')
        self.assertIn('selected', html_content)
        self.assertIn(app.TTS_VOICE, html_content)

    def test_settings_update_voice_persistence(self):
        """Test voice selection persists after settings update"""
        new_voice = 'en-US-Neural2-J'

        payload = {
            'tts_voice': new_voice,
            'google_api_key': 'test_key'
        }

        response = self.client.post('/settings',
                                   data=json.dumps(payload),
                                   content_type='application/json')

        self.assertEqual(response.status_code, 200)

        # Check that environment variable was updated
        self.assertEqual(os.environ.get('TTS_VOICE'), new_voice)
        self.assertEqual(app.TTS_VOICE, new_voice)

    def test_settings_invalid_voice_fallback(self):
        """Test settings handles invalid voice gracefully"""
        invalid_voice = 'invalid-voice-id'

        payload = {
            'tts_voice': invalid_voice,
            'google_api_key': 'test_key'
        }

        response = self.client.post('/settings',
                                   data=json.dumps(payload),
                                   content_type='application/json')

        # Should succeed even with invalid voice
        self.assertEqual(response.status_code, 200)

        # Environment should be updated (validation happens at usage)
        self.assertEqual(os.environ.get('TTS_VOICE'), invalid_voice)

class TestUserExperienceFlow(VoiceValidationTestCase):
    """Test complete user experience flow"""

    def test_voice_selection_to_summary_playback(self):
        """Test complete flow: select voice → save → use in summaries"""
        # Step 1: Select new voice in settings
        new_voice = 'en-US-Neural2-F'
        settings_payload = {'tts_voice': new_voice}

        settings_response = self.client.post('/settings',
                                           data=json.dumps(settings_payload),
                                           content_type='application/json')
        self.assertEqual(settings_response.status_code, 200)

        # Step 2: Verify voice is updated
        voices_response = self.client.get('/api/voices')
        voices_data = json.loads(voices_response.data)
        self.assertEqual(voices_data['current_voice'], new_voice)

        # Step 3: Use voice in speak endpoint
        with patch('app.tts_client') as mock_tts_client:
            mock_response = Mock()
            mock_response.audio_content = b"audio_with_new_voice"
            mock_tts_client.synthesize_speech.return_value = mock_response

            speak_payload = {'text': 'Test summary'}
            speak_response = self.client.post('/speak',
                                            data=json.dumps(speak_payload),
                                            content_type='application/json')

            self.assertEqual(speak_response.status_code, 200)

            # Verify new voice was used
            call_args = mock_tts_client.synthesize_speech.call_args
            voice_params = call_args[1]['voice']
            self.assertEqual(voice_params.name, new_voice)

class TestEdgeCasesAndErrorHandling(VoiceValidationTestCase):
    """Test edge cases and error scenarios"""

    def test_missing_tts_client_graceful_failure(self):
        """Test graceful failure when TTS client is not available"""
        # Temporarily remove TTS client
        original_client = app.tts_client
        app.tts_client = None

        try:
            payload = {'text': 'Test text'}
            response = self.client.post('/speak',
                                       data=json.dumps(payload),
                                       content_type='application/json')

            self.assertEqual(response.status_code, 503)
            self.assertIn(b"Text-to-speech service not available", response.data)

        finally:
            app.tts_client = original_client

    def test_voice_fallback_chain(self):
        """Test voice fallback mechanism works correctly"""
        # Test with non-existent voice
        fallback_voice = get_voice_with_fallback('non-existent-voice')
        self.assertIsNotNone(fallback_voice)
        self.assertEqual(fallback_voice['name'], DEFAULT_VOICE)

        # Test with None input
        fallback_voice = get_voice_with_fallback(None)
        self.assertIsNotNone(fallback_voice)
        self.assertEqual(fallback_voice['name'], DEFAULT_VOICE)

    def test_cache_key_generation(self):
        """Test audio cache key generation is consistent"""
        voice_id = 'en-US-Chirp3-HD-Zephyr'
        text = 'Test cache text'

        key1 = get_optimized_cache_key(voice_id, text)
        key2 = get_optimized_cache_key(voice_id, text)

        self.assertEqual(key1, key2)
        self.assertIn(voice_id, key1)
        self.assertTrue(len(key1) > len(voice_id))  # Should include hash

    def test_empty_or_malformed_requests(self):
        """Test handling of empty or malformed requests"""
        # Empty JSON
        response = self.client.post('/preview-voice',
                                   data='{}',
                                   content_type='application/json')
        self.assertEqual(response.status_code, 400)

        # Malformed JSON
        response = self.client.post('/preview-voice',
                                   data='invalid json',
                                   content_type='application/json')
        self.assertEqual(response.status_code, 400)

        # No content type
        response = self.client.post('/preview-voice',
                                   data=json.dumps({'voice_id': 'test', 'text': 'test'}))
        # Should still work as Flask is permissive
        self.assertIn(response.status_code, [400, 415])  # Either is acceptable

    def test_very_long_text_handling(self):
        """Test handling of very long text inputs"""
        very_long_text = "A" * 10000  # 10KB of text

        with patch('app.tts_client') as mock_tts_client:
            mock_response = Mock()
            mock_response.audio_content = b"audio_data"
            mock_tts_client.synthesize_speech.return_value = mock_response

            # Preview should truncate
            preview_payload = {
                'voice_id': 'en-US-Chirp3-HD-Zephyr',
                'text': very_long_text
            }

            response = self.client.post('/preview-voice',
                                       data=json.dumps(preview_payload),
                                       content_type='application/json')

            self.assertEqual(response.status_code, 200)

            # Speak should handle full text
            speak_payload = {'text': very_long_text}
            response = self.client.post('/speak',
                                       data=json.dumps(speak_payload),
                                       content_type='application/json')

            self.assertEqual(response.status_code, 200)

class TestVoiceConfigurationModule(VoiceValidationTestCase):
    """Test voice_config.py module functions"""

    def test_voice_configuration_completeness(self):
        """Test all voices have complete configuration"""
        for voice_id, voice_data in AVAILABLE_VOICES.items():
            # Test required fields
            required_fields = ['name', 'display_name', 'language_code', 'gender',
                             'accent', 'style', 'tier', 'description', 'quality']

            for field in required_fields:
                self.assertIn(field, voice_data, f"Voice {voice_id} missing {field}")
                self.assertIsNotNone(voice_data[field], f"Voice {voice_id} has None {field}")
                self.assertNotEqual(voice_data[field], "", f"Voice {voice_id} has empty {field}")

            # Test specific validations
            self.assertIn(voice_data['gender'], ['male', 'female'])
            self.assertIn(voice_data['quality'], ['premium', 'high', 'standard'])
            self.assertIn(voice_data['tier'], ['chirp3-hd', 'neural2', 'studio', 'wavenet'])

    def test_fallback_voice_function(self):
        """Test get_fallback_voice function"""
        # Test with voice in fallback chain
        fallback = get_fallback_voice('en-US-Chirp3-HD-Zephyr')
        self.assertIsNotNone(fallback)
        self.assertNotEqual(fallback, 'en-US-Chirp3-HD-Zephyr')  # Should be different

        # Test with voice not in fallback chain
        fallback = get_fallback_voice('non-existent-voice')
        self.assertIsNotNone(fallback)

        # Should return a valid voice ID
        self.assertIn(fallback, AVAILABLE_VOICES)

    def test_sample_text_generation(self):
        """Test sample text for previews"""
        sample = get_sample_text()

        self.assertIsInstance(sample, str)
        self.assertGreater(len(sample), 50)  # Should be substantial
        self.assertLess(len(sample), 1000)   # But not too long

        # Should be suitable for TTS
        self.assertNotIn('\n', sample)  # Single paragraph
        self.assertNotIn('\t', sample)  # No tabs

class TestPerformanceAndReliability(VoiceValidationTestCase):
    """Test performance and reliability aspects"""

    def test_voice_endpoint_response_time(self):
        """Test API endpoints respond within reasonable time"""
        start_time = time.time()
        response = self.client.get('/api/voices')
        end_time = time.time()

        self.assertEqual(response.status_code, 200)
        self.assertLess(end_time - start_time, 1.0)  # Should respond in <1 second

    @patch('app.tts_client')
    def test_concurrent_voice_requests(self, mock_tts_client):
        """Test handling of concurrent voice requests"""
        mock_response = Mock()
        mock_response.audio_content = b"audio_data"
        mock_tts_client.synthesize_speech.return_value = mock_response

        import threading
        import time

        results = []

        def make_request():
            payload = {
                'voice_id': 'en-US-Chirp3-HD-Zephyr',
                'text': 'Concurrent test'
            }
            response = self.client.post('/preview-voice',
                                       data=json.dumps(payload),
                                       content_type='application/json')
            results.append(response.status_code)

        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # All should succeed
        self.assertEqual(len(results), 5)
        for status_code in results:
            self.assertEqual(status_code, 200)

def run_validation_suite():
    """Run the complete validation suite"""
    print("=" * 60)
    print("VOICE MODEL SELECTION - COMPREHENSIVE VALIDATION SUITE")
    print("=" * 60)

    # Create test suite
    test_classes = [
        TestVoiceAPIEndpoints,
        TestSettingsIntegration,
        TestUserExperienceFlow,
        TestEdgeCasesAndErrorHandling,
        TestVoiceConfigurationModule,
        TestPerformanceAndReliability
    ]

    suite = unittest.TestSuite()

    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suite.addTests(tests)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION RESULTS SUMMARY")
    print("=" * 60)

    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total_tests - failures - errors

    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed}")
    print(f"Failed: {failures}")
    print(f"Errors: {errors}")
    print(f"Success Rate: {(passed/total_tests)*100:.1f}%")

    if result.failures:
        print(f"\n❌ FAILURES ({len(result.failures)}):")
        for test, failure in result.failures:
            failure_msg = failure.split('AssertionError: ')[-1].split('\n')[0]
            print(f"  - {test}: {failure_msg}")

    if result.errors:
        print(f"\n🚨 ERRORS ({len(result.errors)}):")
        for test, error in result.errors:
            error_msg = error.split('\n')[-2] if '\n' in error else error
            print(f"  - {test}: {error_msg}")

    if passed == total_tests:
        print("\n✅ ALL TESTS PASSED - FEATURE IS PRODUCTION READY!")
        return 0
    else:
        print(f"\n❌ {failures + errors} ISSUES FOUND - REVIEW REQUIRED")
        return 1

if __name__ == "__main__":
    sys.exit(run_validation_suite())
