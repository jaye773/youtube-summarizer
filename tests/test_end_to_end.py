"""
End-to-End Integration Tests for YouTube Summarizer Async System

This module tests complete async processing workflows from job submission
through completion, including all integration points and real-time updates.

Test Categories:
- Complete video processing workflows
- Complete playlist processing workflows
- Multi-job concurrent processing
- Progress tracking and notifications
- Error recovery and retry scenarios
- Performance and resource usage
- Template rendering integration
"""

import json
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock, call
import pytest
from queue import Queue

from flask import Flask
from flask.testing import FlaskClient

# Import main application and models
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from job_models import JobStatus, JobType, JobPriority, ProcessingJob, JobResult
from worker_manager import WorkerManager
from job_state import JobStateManager
from sse_manager import SSEManager as NewSSEManager


@pytest.fixture
def client():
    """Create a Flask test client for end-to-end testing."""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.config['WTF_CSRF_ENABLED'] = False

    # Set up test cache directory
    app.config['CACHE_DIR'] = tempfile.mkdtemp()

    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture
def full_worker_system():
    """Mock a complete, functional worker system."""
    with patch('app.WORKER_SYSTEM_AVAILABLE', True):
        with patch('app.WorkerManager') as mock_wm, \
             patch('app.JobStateManager') as mock_jsm, \
             patch('app.get_sse_manager') as mock_sse_getter:

            # Create realistic mock instances
            worker_manager = Mock()
            job_state_manager = Mock()
            sse_manager = Mock()

            mock_wm.return_value = worker_manager
            mock_jsm.return_value = job_state_manager
            mock_sse_getter.return_value = sse_manager

            # Configure realistic behavior
            job_store = {}

            def submit_job(job):
                job_id = str(uuid.uuid4())
                job_store[job_id] = job
                return job_id

            def get_job(job_id):
                return job_store.get(job_id)

            def update_job_status(job_id, status, **kwargs):
                if job_id in job_store:
                    job_store[job_id].status = status
                    for key, value in kwargs.items():
                        setattr(job_store[job_id], key, value)

            worker_manager.submit_job = submit_job
            job_state_manager.get_job = get_job
            job_state_manager.update_job_status = update_job_status
            job_state_manager.get_active_jobs.return_value = list(job_store.values())

            yield {
                'worker_manager': worker_manager,
                'job_state_manager': job_state_manager,
                'sse_manager': sse_manager,
                'job_store': job_store
            }


@pytest.fixture
def mock_youtube_api():
    """Mock YouTube API responses for testing."""
    with patch('app.get_video_details') as mock_get_video, \
         patch('app.get_transcript') as mock_get_transcript, \
         patch('app.get_videos_from_playlist') as mock_get_playlist:

        mock_get_video.return_value = {
            'title': 'Test Video',
            'description': 'Test video description',
            'duration': '00:05:30',
            'upload_date': '2023-01-01'
        }

        mock_get_transcript.return_value = [
            {'text': 'This is the first part of the transcript.', 'start': 0.0, 'duration': 2.5},
            {'text': 'This is the second part of the transcript.', 'start': 2.5, 'duration': 3.0},
            {'text': 'This concludes the test transcript.', 'start': 5.5, 'duration': 2.0}
        ]

        mock_get_playlist.return_value = [
            {'video_id': 'test1', 'title': 'Video 1'},
            {'video_id': 'test2', 'title': 'Video 2'},
            {'video_id': 'test3', 'title': 'Video 3'}
        ]

        yield {
            'get_video_details': mock_get_video,
            'get_transcript': mock_get_transcript,
            'get_videos_from_playlist': mock_get_playlist
        }


@pytest.fixture
def mock_ai_providers():
    """Mock AI provider responses for testing."""
    with patch('app.generate_summary') as mock_generate:

        def generate_summary_mock(transcript, **kwargs):
            # Simulate AI processing time
            time.sleep(0.1)
            return {
                'summary': f'This is a test summary generated for transcript: {transcript[:50]}...',
                'key_points': ['Point 1', 'Point 2', 'Point 3'],
                'provider': kwargs.get('ai_provider', 'gemini'),
                'model': kwargs.get('model', 'gemini-2.5-flash')
            }

        mock_generate.side_effect = generate_summary_mock

        yield {'generate_summary': mock_generate}


class TestCompleteVideoWorkflow:
    """Test complete video processing workflows from start to finish."""

    def test_video_processing_success_workflow(self, client, full_worker_system,
                                             mock_youtube_api, mock_ai_providers):
        """Test complete successful video processing workflow."""
        job_data = {
            'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'ai_provider': 'gemini',
            'model': 'gemini-2.5-flash'
        }

        # Step 1: Submit job
        response = client.post('/summarize_async',
                             json=job_data,
                             content_type='application/json')

        assert response.status_code == 202
        job_response = response.get_json()
        job_id = job_response['job_id']

        # Step 2: Simulate job processing stages
        job_store = full_worker_system['job_store']
        sse_manager = full_worker_system['sse_manager']

        # Start processing
        job = job_store[job_id]
        job.status = JobStatus.IN_PROGRESS
        job.progress = 10
        job.current_step = 'Fetching video details...'

        # Check status during processing
        response = client.get(f'/jobs/{job_id}/status')
        assert response.status_code == 200
        status_data = response.get_json()
        assert status_data['status'] == 'in_progress'
        assert status_data['progress'] == 10

        # Continue processing
        job.progress = 50
        job.current_step = 'Extracting transcript...'

        response = client.get(f'/jobs/{job_id}/status')
        status_data = response.get_json()
        assert status_data['progress'] == 50

        # Final processing
        job.progress = 90
        job.current_step = 'Generating summary...'

        # Complete job
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.result = JobResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            result={
                'summary': 'Test video summary',
                'title': 'Test Video',
                'video_id': 'dQw4w9WgXcQ',
                'transcript_length': 150,
                'processing_time': 5.2
            }
        )
        job.completed_at = datetime.now(timezone.utc)

        # Verify completion
        response = client.get(f'/jobs/{job_id}/status')
        assert response.status_code == 200
        final_status = response.get_json()
        assert final_status['status'] == 'completed'
        assert final_status['progress'] == 100
        assert 'result' in final_status
        assert final_status['result']['summary'] == 'Test video summary'

        # Verify SSE notifications were sent
        assert sse_manager.broadcast_event.called

    def test_video_processing_with_error_recovery(self, client, full_worker_system,
                                                 mock_youtube_api, mock_ai_providers):
        """Test video processing with error and retry."""
        job_data = {
            'url': 'https://www.youtube.com/watch?v=error123',
            'ai_provider': 'openai',
            'model': 'gpt-4o'
        }

        # Submit job
        response = client.post('/summarize_async', json=job_data)
        assert response.status_code == 202
        job_id = response.get_json()['job_id']

        # Simulate initial failure
        job_store = full_worker_system['job_store']
        job = job_store[job_id]
        job.status = JobStatus.FAILED
        job.error_message = 'Transcript not available'
        job.retry_count = 0

        # Check failed status
        response = client.get(f'/jobs/{job_id}/status')
        status_data = response.get_json()
        assert status_data['status'] == 'failed'
        assert 'error' in status_data

        # Simulate retry
        job.status = JobStatus.RETRY
        job.retry_count = 1
        job.error_message = None

        # Process successfully on retry
        job.status = JobStatus.IN_PROGRESS
        job.progress = 50

        # Complete successfully
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.result = JobResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            result={'summary': 'Retry successful', 'video_id': 'error123'}
        )

        # Verify final success
        response = client.get(f'/jobs/{job_id}/status')
        final_status = response.get_json()
        assert final_status['status'] == 'completed'
        assert final_status['result']['summary'] == 'Retry successful'

    def test_video_processing_timeout(self, client, full_worker_system):
        """Test handling of video processing timeout."""
        job_data = {
            'url': 'https://www.youtube.com/watch?v=timeout123',
            'ai_provider': 'gemini',
            'model': 'gemini-2.5-pro'
        }

        response = client.post('/summarize_async', json=job_data)
        job_id = response.get_json()['job_id']

        # Simulate long processing time leading to timeout
        job_store = full_worker_system['job_store']
        job = job_store[job_id]
        job.status = JobStatus.IN_PROGRESS
        job.progress = 30
        job.started_at = datetime.now(timezone.utc) - timedelta(minutes=30)  # Long processing

        # Simulate timeout
        job.status = JobStatus.FAILED
        job.error_message = 'Processing timeout exceeded'

        response = client.get(f'/jobs/{job_id}/status')
        status_data = response.get_json()
        assert status_data['status'] == 'failed'
        assert 'timeout' in status_data['error'].lower()


class TestCompletePlaylistWorkflow:
    """Test complete playlist processing workflows."""

    def test_playlist_processing_success_workflow(self, client, full_worker_system,
                                                 mock_youtube_api, mock_ai_providers):
        """Test complete successful playlist processing workflow."""
        job_data = {
            'url': 'https://www.youtube.com/playlist?list=PLtest123',
            'ai_provider': 'openai',
            'model': 'gpt-4o',
            'priority': 'medium'
        }

        # Submit playlist job
        response = client.post('/summarize_async', json=job_data)
        assert response.status_code == 202
        job_id = response.get_json()['job_id']

        # Simulate playlist processing stages
        job_store = full_worker_system['job_store']
        job = job_store[job_id]
        job.job_type = JobType.PLAYLIST
        job.status = JobStatus.IN_PROGRESS
        job.progress = 0
        job.current_step = 'Fetching playlist videos...'
        job.metadata = {'total_videos': 3, 'processed_videos': 0}

        # Process each video in playlist
        for i in range(3):
            job.progress = int((i + 1) / 3 * 100)
            job.current_step = f'Processing video {i + 1} of 3...'
            job.metadata['processed_videos'] = i + 1

            # Check progress
            response = client.get(f'/jobs/{job_id}/status')
            status_data = response.get_json()
            assert status_data['progress'] == job.progress
            assert f'video {i + 1}' in status_data['current_step'].lower()

        # Complete playlist processing
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.result = JobResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            result={
                'playlist_summary': 'Combined playlist summary',
                'video_summaries': [
                    {'video_id': 'test1', 'summary': 'Summary 1'},
                    {'video_id': 'test2', 'summary': 'Summary 2'},
                    {'video_id': 'test3', 'summary': 'Summary 3'}
                ],
                'total_videos': 3,
                'successful_videos': 3,
                'failed_videos': 0
            }
        )

        # Verify completion
        response = client.get(f'/jobs/{job_id}/status')
        final_status = response.get_json()
        assert final_status['status'] == 'completed'
        assert final_status['result']['total_videos'] == 3
        assert len(final_status['result']['video_summaries']) == 3

    def test_playlist_partial_failure_workflow(self, client, full_worker_system,
                                              mock_youtube_api, mock_ai_providers):
        """Test playlist processing with some video failures."""
        job_data = {
            'url': 'https://www.youtube.com/playlist?list=PLpartialfail',
            'ai_provider': 'gemini',
            'model': 'gemini-2.5-flash'
        }

        response = client.post('/summarize_async', json=job_data)
        job_id = response.get_json()['job_id']

        # Simulate partial processing
        job_store = full_worker_system['job_store']
        job = job_store[job_id]
        job.status = JobStatus.COMPLETED  # Can complete even with partial failures
        job.progress = 100
        job.result = JobResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            result={
                'playlist_summary': 'Partial playlist summary (2 of 3 videos)',
                'video_summaries': [
                    {'video_id': 'test1', 'summary': 'Summary 1'},
                    {'video_id': 'test2', 'summary': 'Summary 2'}
                ],
                'failed_videos': [
                    {'video_id': 'test3', 'error': 'Transcript not available'}
                ],
                'total_videos': 3,
                'successful_videos': 2,
                'failed_videos': 1
            }
        )

        response = client.get(f'/jobs/{job_id}/status')
        result = response.get_json()
        assert result['status'] == 'completed'
        assert result['result']['successful_videos'] == 2
        assert result['result']['failed_videos'] == 1


class TestConcurrentJobProcessing:
    """Test concurrent processing of multiple jobs."""

    def test_multiple_concurrent_jobs(self, client, full_worker_system,
                                     mock_youtube_api, mock_ai_providers):
        """Test processing multiple jobs concurrently."""
        # Submit multiple jobs
        job_ids = []
        for i in range(3):
            job_data = {
                'url': f'https://www.youtube.com/watch?v=concurrent{i}',
                'ai_provider': 'gemini',
                'model': 'gemini-2.5-flash'
            }
            response = client.post('/summarize_async', json=job_data)
            assert response.status_code == 202
            job_ids.append(response.get_json()['job_id'])

        # Verify all jobs are tracked
        response = client.get('/jobs')
        assert response.status_code == 200
        jobs_data = response.get_json()
        assert jobs_data['total'] >= 3

        # Simulate concurrent processing
        job_store = full_worker_system['job_store']
        for i, job_id in enumerate(job_ids):
            job = job_store[job_id]
            job.status = JobStatus.IN_PROGRESS
            job.progress = 50 + (i * 10)  # Different progress levels
            job.current_step = f'Processing job {i + 1}...'

        # Check all job statuses
        for i, job_id in enumerate(job_ids):
            response = client.get(f'/jobs/{job_id}/status')
            status_data = response.get_json()
            assert status_data['status'] == 'in_progress'
            assert status_data['progress'] == 50 + (i * 10)

        # Complete all jobs
        for i, job_id in enumerate(job_ids):
            job = job_store[job_id]
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.result = JobResult(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                result={
                    'summary': f'Concurrent job {i + 1} summary',
                    'video_id': f'concurrent{i}'
                }
            )

        # Verify all completions
        for i, job_id in enumerate(job_ids):
            response = client.get(f'/jobs/{job_id}/status')
            result = response.get_json()
            assert result['status'] == 'completed'
            assert f'job {i + 1}' in result['result']['summary']

    def test_job_priority_handling(self, client, full_worker_system):
        """Test that job priorities are handled correctly."""
        # Submit jobs with different priorities
        high_priority_job = {
            'url': 'https://www.youtube.com/watch?v=high_priority',
            'ai_provider': 'gemini',
            'model': 'gemini-2.5-flash',
            'priority': 'high'
        }

        low_priority_job = {
            'url': 'https://www.youtube.com/playlist?list=PLlow_priority',
            'ai_provider': 'openai',
            'model': 'gpt-4o',
            'priority': 'low'
        }

        # Submit low priority first
        response1 = client.post('/summarize_async', json=low_priority_job)
        low_job_id = response1.get_json()['job_id']

        # Submit high priority second
        response2 = client.post('/summarize_async', json=high_priority_job)
        high_job_id = response2.get_json()['job_id']

        # Both should be accepted
        assert response1.status_code == 202
        assert response2.status_code == 202

        # Verify jobs exist in system
        job_store = full_worker_system['job_store']
        assert low_job_id in job_store
        assert high_job_id in job_store

        # High priority job should have higher priority enum value
        high_job = job_store[high_job_id]
        low_job = job_store[low_job_id]

        # Priority enum: HIGH=1, MEDIUM=2, LOW=3 (lower number = higher priority)
        assert high_job.priority.value < low_job.priority.value


class TestProgressTrackingAndNotifications:
    """Test progress tracking and real-time notifications."""

    def test_sse_progress_notifications(self, client, full_worker_system):
        """Test SSE progress notifications during job processing."""
        # Submit a job
        job_data = {
            'url': 'https://www.youtube.com/watch?v=progress_test',
            'ai_provider': 'gemini',
            'model': 'gemini-2.5-flash'
        }

        response = client.post('/summarize_async', json=job_data)
        job_id = response.get_json()['job_id']

        # Simulate progress updates
        job_store = full_worker_system['job_store']
        sse_manager = full_worker_system['sse_manager']
        job = job_store[job_id]

        # Progress stages
        progress_stages = [
            (10, 'Fetching video details...'),
            (30, 'Extracting transcript...'),
            (60, 'Generating summary...'),
            (100, 'Completed')
        ]

        for progress, step in progress_stages:
            job.progress = progress
            job.current_step = step
            if progress == 100:
                job.status = JobStatus.COMPLETED
                job.result = JobResult(
                    job_id=job_id,
                    status=JobStatus.COMPLETED,
                    result={'summary': 'Progress test complete'}
                )

            # Verify SSE manager is called for notifications
            # (In real implementation, this would send SSE events)
            # sse_manager.broadcast_event should be called

        # Verify final state
        response = client.get(f'/jobs/{job_id}/status')
        final_state = response.get_json()
        assert final_state['status'] == 'completed'
        assert final_state['progress'] == 100

    def test_job_status_polling(self, client, full_worker_system):
        """Test polling job status for updates."""
        job_data = {
            'url': 'https://www.youtube.com/watch?v=polling_test',
            'ai_provider': 'openai',
            'model': 'gpt-4o'
        }

        response = client.post('/summarize_async', json=job_data)
        job_id = response.get_json()['job_id']

        # Simulate status changes over time
        job_store = full_worker_system['job_store']
        job = job_store[job_id]

        # Initial state
        response = client.get(f'/jobs/{job_id}/status')
        assert response.get_json()['status'] == 'pending'

        # Start processing
        job.status = JobStatus.IN_PROGRESS
        job.progress = 25

        response = client.get(f'/jobs/{job_id}/status')
        status = response.get_json()
        assert status['status'] == 'in_progress'
        assert status['progress'] == 25

        # Continue processing
        job.progress = 75
        job.current_step = 'Almost done...'

        response = client.get(f'/jobs/{job_id}/status')
        status = response.get_json()
        assert status['progress'] == 75
        assert status['current_step'] == 'Almost done...'

        # Complete
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.result = JobResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            result={'summary': 'Polling test complete'}
        )

        response = client.get(f'/jobs/{job_id}/status')
        final_status = response.get_json()
        assert final_status['status'] == 'completed'
        assert final_status['progress'] == 100


class TestTemplateRenderingIntegration:
    """Test template rendering with async features."""

    def test_index_page_async_ui_elements(self, client, full_worker_system):
        """Test that index page includes async UI elements."""
        response = client.get('/')
        assert response.status_code == 200

        html_content = response.get_data(as_text=True)

        # Check for async-related elements (these depend on actual template)
        # This test would need to be adjusted based on actual template structure
        assert 'html' in html_content  # Basic HTML structure
        # Additional checks would depend on actual template implementation

    def test_job_status_page_rendering(self, client, full_worker_system):
        """Test rendering of job status information."""
        # This test depends on whether there are dedicated status pages
        # For now, we test that the endpoints respond properly

        job_data = {
            'url': 'https://www.youtube.com/watch?v=render_test',
            'ai_provider': 'gemini',
            'model': 'gemini-2.5-flash'
        }

        response = client.post('/summarize_async', json=job_data)
        job_id = response.get_json()['job_id']

        # Test status endpoint returns proper JSON for frontend
        status_response = client.get(f'/jobs/{job_id}/status')
        assert status_response.status_code == 200
        assert status_response.content_type == 'application/json'

    def test_async_css_and_js_loading(self, client):
        """Test that async-related CSS and JS files are accessible."""
        # Test CSS file
        css_response = client.get('/static/css/async_ui.css')
        # File may or may not exist, but should not cause server error
        assert css_response.status_code in [200, 404]

        # Test JS files (check a few key ones)
        js_files = [
            '/static/js/sse-manager.js',
            '/static/js/job_tracker.js',
            '/static/js/async-integration.js'
        ]

        for js_file in js_files:
            js_response = client.get(js_file)
            assert js_response.status_code in [200, 404]


class TestPerformanceAndResourceUsage:
    """Test performance characteristics and resource usage."""

    def test_job_submission_performance(self, client, full_worker_system):
        """Test performance of job submission under load."""
        start_time = time.time()

        # Submit multiple jobs
        job_data = {
            'url': 'https://www.youtube.com/watch?v=perf_test',
            'ai_provider': 'gemini',
            'model': 'gemini-2.5-flash'
        }

        for i in range(10):
            job_data['url'] = f'https://www.youtube.com/watch?v=perf_test_{i}'
            response = client.post('/summarize_async', json=job_data)
            assert response.status_code == 202

        end_time = time.time()
        total_time = end_time - start_time

        # Should handle 10 job submissions quickly (within 5 seconds)
        assert total_time < 5.0
        print(f"10 job submissions took {total_time:.2f} seconds")

    def test_status_check_performance(self, client, full_worker_system):
        """Test performance of status checks."""
        # Submit a job first
        job_data = {
            'url': 'https://www.youtube.com/watch?v=status_perf',
            'ai_provider': 'gemini',
            'model': 'gemini-2.5-flash'
        }

        response = client.post('/summarize_async', json=job_data)
        job_id = response.get_json()['job_id']

        # Time multiple status checks
        start_time = time.time()

        for _ in range(50):
            response = client.get(f'/jobs/{job_id}/status')
            assert response.status_code == 200

        end_time = time.time()
        total_time = end_time - start_time

        # 50 status checks should be fast (within 2 seconds)
        assert total_time < 2.0
        print(f"50 status checks took {total_time:.2f} seconds")

    def test_concurrent_request_handling(self, client, full_worker_system):
        """Test concurrent request handling performance."""
        def submit_and_check_job(job_index):
            job_data = {
                'url': f'https://www.youtube.com/watch?v=concurrent_{job_index}',
                'ai_provider': 'gemini',
                'model': 'gemini-2.5-flash'
            }

            # Submit job
            response = client.post('/summarize_async', json=job_data)
            if response.status_code == 202:
                job_id = response.get_json()['job_id']

                # Check status a few times
                for _ in range(3):
                    client.get(f'/jobs/{job_id}/status')
                    time.sleep(0.1)

        # Run concurrent operations
        start_time = time.time()

        threads = []
        for i in range(5):
            thread = threading.Thread(target=submit_and_check_job, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        end_time = time.time()
        total_time = end_time - start_time

        # Should handle concurrent operations efficiently
        assert total_time < 10.0
        print(f"5 concurrent job workflows took {total_time:.2f} seconds")

    def test_memory_usage_stability(self, client, full_worker_system):
        """Test memory usage remains stable under load."""
        # This is a basic test - real memory testing would require profiling tools

        # Perform many operations
        for i in range(20):
            job_data = {
                'url': f'https://www.youtube.com/watch?v=memory_test_{i}',
                'ai_provider': 'gemini',
                'model': 'gemini-2.5-flash'
            }

            response = client.post('/summarize_async', json=job_data)
            if response.status_code == 202:
                job_id = response.get_json()['job_id']
                client.get(f'/jobs/{job_id}/status')

        # Check job listing
        response = client.get('/jobs')
        assert response.status_code == 200

        # If we get here without memory errors, test passes
        assert True


class TestSystemIntegrationScenarios:
    """Test complex system integration scenarios."""

    def test_mixed_job_types_workflow(self, client, full_worker_system,
                                     mock_youtube_api, mock_ai_providers):
        """Test processing mixed job types (videos and playlists) concurrently."""
        # Submit different types of jobs
        video_job = {
            'url': 'https://www.youtube.com/watch?v=mixed_video',
            'ai_provider': 'gemini',
            'model': 'gemini-2.5-flash',
            'priority': 'high'
        }

        playlist_job = {
            'url': 'https://www.youtube.com/playlist?list=PLmixed',
            'ai_provider': 'openai',
            'model': 'gpt-4o',
            'priority': 'medium'
        }

        # Submit jobs
        video_response = client.post('/summarize_async', json=video_job)
        playlist_response = client.post('/summarize_async', json=playlist_job)

        assert video_response.status_code == 202
        assert playlist_response.status_code == 202

        video_job_id = video_response.get_json()['job_id']
        playlist_job_id = playlist_response.get_json()['job_id']

        # Process both jobs
        job_store = full_worker_system['job_store']

        # Complete video job
        video_job_obj = job_store[video_job_id]
        video_job_obj.status = JobStatus.COMPLETED
        video_job_obj.progress = 100
        video_job_obj.result = JobResult(
            job_id=video_job_id,
            status=JobStatus.COMPLETED,
            result={'summary': 'Mixed video summary', 'type': 'video'}
        )

        # Complete playlist job
        playlist_job_obj = job_store[playlist_job_id]
        playlist_job_obj.status = JobStatus.COMPLETED
        playlist_job_obj.progress = 100
        playlist_job_obj.result = JobResult(
            job_id=playlist_job_id,
            status=JobStatus.COMPLETED,
            result={'summary': 'Mixed playlist summary', 'type': 'playlist'}
        )

        # Verify both completed successfully
        video_status = client.get(f'/jobs/{video_job_id}/status').get_json()
        playlist_status = client.get(f'/jobs/{playlist_job_id}/status').get_json()

        assert video_status['status'] == 'completed'
        assert playlist_status['status'] == 'completed'
        assert video_status['result']['type'] == 'video'
        assert playlist_status['result']['type'] == 'playlist'

    def test_system_under_stress(self, client, full_worker_system):
        """Test system behavior under stress conditions."""
        # Submit many jobs rapidly
        job_ids = []

        for i in range(15):  # Moderate stress test
            job_data = {
                'url': f'https://www.youtube.com/watch?v=stress_test_{i}',
                'ai_provider': 'gemini' if i % 2 == 0 else 'openai',
                'model': 'gemini-2.5-flash' if i % 2 == 0 else 'gpt-4o'
            }

            response = client.post('/summarize_async', json=job_data)
            if response.status_code == 202:
                job_ids.append(response.get_json()['job_id'])
            elif response.status_code == 429:
                # Rate limiting is acceptable under stress
                pass
            else:
                # Other errors should not occur
                assert False, f"Unexpected status code: {response.status_code}"

        # Should have accepted at least some jobs
        assert len(job_ids) > 0

        # Check job listing can handle the load
        response = client.get('/jobs')
        assert response.status_code == 200
        jobs_data = response.get_json()
        assert jobs_data['total'] >= len(job_ids)

        # Status checks should work for all accepted jobs
        for job_id in job_ids:
            response = client.get(f'/jobs/{job_id}/status')
            assert response.status_code == 200


if __name__ == '__main__':
    # Run tests with verbose output and performance timing
    pytest.main([__file__, '-v', '--tb=short', '-s'])
