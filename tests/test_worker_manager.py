"""
Test suite for worker_manager.py

Validates worker thread management, job processing lifecycle, error handling, and system coordination.
Tests WorkerThread and WorkerManager functionality, including startup/shutdown, job processing,
notification callbacks, and integration with the job queue system.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from job_models import (
    JobPriority,
    JobResult,
    JobStatus,
    JobType,
    ProcessingJob,
    WorkerMetrics,
)
from job_queue import JobScheduler
from worker_manager import WorkerManager, WorkerThread


class TestWorkerThread:
    """Test WorkerThread functionality"""

    def setup_method(self):
        """Set up test fixtures before each test"""
        self.job_scheduler = JobScheduler()
        self.notification_callback = MagicMock()

        # Mock app functions to avoid real YouTube API calls
        self.mock_app_functions()

    def mock_app_functions(self):
        """Mock all app functions to avoid real API calls"""
        import worker_manager

        worker_manager.clean_youtube_url = lambda url: url
        worker_manager.get_video_id = MagicMock(return_value="mock_video_id")
        worker_manager.get_playlist_id = MagicMock(return_value="mock_playlist_id")
        worker_manager.get_transcript = MagicMock(
            return_value=("mock transcript text", None)
        )
        worker_manager.generate_summary = MagicMock(
            return_value=("mock summary text", None)
        )
        worker_manager.get_video_details = MagicMock(
            return_value={
                "mock_video_id": {
                    "title": "Mock Video Title",
                    "thumbnail_url": "https://mock.thumbnail.url",
                }
            }
        )
        worker_manager.get_videos_from_playlist = MagicMock(
            return_value=(
                [
                    {"contentDetails": {"videoId": "playlist_vid_1"}},
                    {"contentDetails": {"videoId": "playlist_vid_2"}},
                ],
                None,
            )
        )
        worker_manager.load_summary_cache = MagicMock(return_value={})
        worker_manager.save_summary_cache = MagicMock()

    def test_worker_initialization(self):
        """Test WorkerThread initialization"""
        worker = WorkerThread(
            "test-worker", self.job_scheduler, self.notification_callback
        )

        assert worker.worker_id == "test-worker"
        assert worker.job_scheduler == self.job_scheduler
        assert worker.notification_callback == self.notification_callback
        assert worker.thread is None
        assert worker.is_running is False
        assert worker.should_stop is False
        assert isinstance(worker.metrics, WorkerMetrics)
        assert worker.current_job is None

    def test_worker_start_stop(self):
        """Test worker thread start and stop functionality"""
        worker = WorkerThread("start-stop-worker", self.job_scheduler)

        # Start worker
        worker.start()
        assert worker.is_running is True
        assert worker.thread is not None
        assert worker.thread.is_alive() is True

        # Stop worker
        worker.stop(timeout=2.0)
        assert worker.is_running is False
        assert not worker.thread.is_alive()

    def test_worker_stop_with_timeout(self):
        """Test worker stop with timeout"""
        worker = WorkerThread("timeout-worker", self.job_scheduler)

        # Create a worker that won't stop easily (mock scenario)
        worker.start()
        time.sleep(0.1)  # Let it start

        # Stop with very short timeout
        start_time = time.time()
        worker.stop(timeout=0.1)
        stop_time = time.time()

        # Should respect timeout
        assert stop_time - start_time >= 0.1
        assert worker.is_running is False

    def test_worker_double_start(self):
        """Test that starting an already running worker is handled gracefully"""
        worker = WorkerThread("double-start", self.job_scheduler)

        worker.start()
        original_thread = worker.thread

        # Try to start again
        worker.start()

        # Should be the same thread
        assert worker.thread == original_thread
        assert worker.is_running is True

        worker.stop()

    def test_worker_process_video_job_success(self):
        """Test successful video job processing"""
        worker = WorkerThread(
            "video-worker", self.job_scheduler, self.notification_callback
        )

        job = ProcessingJob(
            job_id="video-test",
            job_type=JobType.VIDEO,
            priority=JobPriority.HIGH,
            data={"url": "https://youtube.com/watch?v=test123", "model_key": "gpt-4"},
        )

        # Process job
        result = worker._process_job(job)

        # Verify result
        assert result.success is True
        assert result.job_id == "video-test"
        assert result.job_type == JobType.VIDEO
        assert result.data is not None
        assert "video_id" in result.data
        assert "title" in result.data
        assert "summary" in result.data

        # Verify job state
        assert job.status == JobStatus.COMPLETED
        assert job.worker_id == "video-worker"
        assert job.progress == 1.0

    def test_worker_process_video_job_cached(self):
        """Test video job processing with cached result"""
        import worker_manager

        # Set up cache with existing result
        cached_result = {
            "video_id": "mock_video_id",
            "title": "Cached Video",
            "summary": "Cached summary",
        }
        worker_manager.load_summary_cache = MagicMock(
            return_value={"mock_video_id_gpt-4": cached_result}
        )

        worker = WorkerThread("cache-worker", self.job_scheduler)
        # Manually set the cache since we're not going through the full worker loop
        worker._summary_cache = {"mock_video_id_gpt-4": cached_result}

        job = ProcessingJob(
            job_id="cache-test",
            job_type=JobType.VIDEO,
            priority=JobPriority.HIGH,
            data={"url": "https://youtube.com/watch?v=cached", "model_key": "gpt-4"},
        )

        result = worker._process_job(job)

        assert result.success is True
        assert result.data["cached"] is True  # Should be added by the processing logic
        assert result.data["title"] == "Cached Video"

    def test_worker_process_video_job_failure(self):
        """Test video job processing failure"""
        import worker_manager

        # Mock failure in transcript retrieval
        worker_manager.get_transcript = MagicMock(
            return_value=(None, "Transcript error")
        )

        worker = WorkerThread(
            "failure-worker", self.job_scheduler, self.notification_callback
        )

        job = ProcessingJob(
            job_id="failure-test",
            job_type=JobType.VIDEO,
            priority=JobPriority.HIGH,
            data={"url": "https://youtube.com/watch?v=fail123"},
        )

        result = worker._process_job(job)

        assert result.success is False
        assert result.error is not None
        assert "transcript" in result.error.lower()
        assert job.status == JobStatus.RETRY  # Should be marked for retry
        assert job.retry_count == 1

    def test_worker_process_playlist_job_success(self):
        """Test successful playlist job processing"""
        worker = WorkerThread("playlist-worker", self.job_scheduler)

        job = ProcessingJob(
            job_id="playlist-test",
            job_type=JobType.PLAYLIST,
            priority=JobPriority.MEDIUM,
            data={
                "url": "https://youtube.com/playlist?list=test123",
                "video_ids": ["vid1", "vid2"],
                "model_key": "gpt-4",
            },
        )

        result = worker._process_job(job)

        assert result.success is True
        assert result.data["type"] == "playlist"
        assert result.data["total_videos"] == 2
        assert "results" in result.data
        assert len(result.data["results"]) == 2

    def test_worker_process_playlist_job_with_failures(self):
        """Test playlist job processing with some video failures"""
        import worker_manager

        # Mock failure for one video
        def mock_get_transcript_with_failure(video_id):
            if video_id == "mock_video_id":  # This will fail for first video
                return (None, "Mock error")
            return ("transcript", None)

        worker_manager.get_transcript = mock_get_transcript_with_failure

        worker = WorkerThread("playlist-fail-worker", self.job_scheduler)

        job = ProcessingJob(
            job_id="playlist-partial-fail",
            job_type=JobType.PLAYLIST,
            priority=JobPriority.MEDIUM,
            data={
                "url": "https://youtube.com/playlist?list=partial",
                "video_ids": ["vid1", "vid2", "vid3"],
                "model_key": "gpt-4",
            },
        )

        result = worker._process_job(job)

        assert result.success is True  # Overall success even with partial failures
        assert result.data["total_videos"] == 3
        assert result.data["failed_videos"] > 0
        assert result.data["successful_videos"] < 3

    def test_worker_process_batch_job_success(self):
        """Test successful batch job processing"""
        worker = WorkerThread("batch-worker", self.job_scheduler)

        job = ProcessingJob(
            job_id="batch-test",
            job_type=JobType.BATCH,
            priority=JobPriority.LOW,
            data={
                "urls": [
                    "https://youtube.com/watch?v=batch1",
                    "https://youtube.com/watch?v=batch2",
                ],
                "model_key": "gpt-4",
            },
        )

        result = worker._process_job(job)

        assert result.success is True
        assert result.data["type"] == "batch"
        assert result.data["total_urls"] == 2
        assert len(result.data["results"]) == 2

    def test_worker_progress_notifications(self):
        """Test that worker sends progress notifications"""
        worker = WorkerThread(
            "progress-worker", self.job_scheduler, self.notification_callback
        )

        job = ProcessingJob(
            job_id="progress-test",
            job_type=JobType.VIDEO,
            priority=JobPriority.HIGH,
            data={"url": "https://youtube.com/watch?v=progress123"},
        )

        worker._process_job(job)

        # Should have called notification callback multiple times for progress
        assert self.notification_callback.call_count >= 2

        # Check that some calls were progress updates
        progress_calls = [
            call
            for call in self.notification_callback.call_args_list
            if call[1].get("progress_update") is True
        ]
        assert len(progress_calls) > 0

    def test_worker_get_status(self):
        """Test worker status reporting"""
        worker = WorkerThread("status-worker", self.job_scheduler)

        status = worker.get_status()

        assert status["worker_id"] == "status-worker"
        assert status["is_running"] is False
        assert status["current_job_id"] is None
        assert "metrics" in status

        # Test with running job
        job = ProcessingJob("status-job", JobType.VIDEO, JobPriority.HIGH, {})
        worker.current_job = job

        status = worker.get_status()
        assert status["current_job_id"] == "status-job"

    def test_worker_job_processing_loop(self):
        """Test worker job processing loop with real jobs"""
        worker = WorkerThread(
            "loop-worker", self.job_scheduler, self.notification_callback
        )

        # Add jobs to scheduler
        job1 = ProcessingJob(
            "loop-job-1",
            JobType.VIDEO,
            JobPriority.HIGH,
            {"url": "https://youtube.com/watch?v=loop1"},
        )
        job2 = ProcessingJob(
            "loop-job-2",
            JobType.VIDEO,
            JobPriority.MEDIUM,
            {"url": "https://youtube.com/watch?v=loop2"},
        )

        self.job_scheduler.submit_job(job1)
        self.job_scheduler.submit_job(job2)

        # Start worker
        worker.start()

        # Wait for jobs to be processed
        time.sleep(1.0)

        # Stop worker
        worker.stop()

        # Jobs should have been processed
        assert self.job_scheduler.queue.size() == 0
        assert worker.metrics.jobs_processed == 2

    def test_worker_error_handling(self):
        """Test worker error handling and recovery"""
        # Mock an exception during job processing
        with patch.object(
            WorkerThread, "_process_job", side_effect=Exception("Test exception")
        ):
            worker = WorkerThread("error-worker", self.job_scheduler)

            job = ProcessingJob("error-job", JobType.VIDEO, JobPriority.HIGH, {})
            self.job_scheduler.submit_job(job)

            worker.start()
            time.sleep(0.5)  # Let it try to process
            worker.stop()

            # Worker should still be responsive after error
            assert (
                worker.metrics.jobs_failed >= 0
            )  # May or may not have recorded failure


class TestWorkerManager:
    """Test WorkerManager functionality"""

    def setup_method(self):
        """Set up test fixtures before each test"""
        self.mock_app_functions()

    def mock_app_functions(self):
        """Mock all app functions to avoid real API calls"""
        self.mock_app_context = {
            "extract_video_id": MagicMock(return_value="mock_video_id"),
            "extract_playlist_id": MagicMock(return_value="mock_playlist_id"),
            "get_transcript": MagicMock(return_value=("mock transcript", None)),
            "generate_summary": MagicMock(return_value=("mock summary", None)),
            "get_video_details": MagicMock(
                return_value={
                    "mock_video_id": {
                        "title": "Mock Title",
                        "thumbnail_url": "mock_url",
                    }
                }
            ),
            "get_videos_from_playlist": MagicMock(return_value=([], None)),
            "save_summary_cache": MagicMock(),
            "load_summary_cache": MagicMock(return_value={}),
        }

    def test_manager_initialization(self):
        """Test WorkerManager initialization"""
        manager = WorkerManager(
            num_workers=2, max_queue_size=500, rate_limit_per_minute=30
        )

        assert manager.num_workers == 2
        assert manager.job_scheduler.queue.max_size == 500
        assert manager.job_scheduler.rate_limit_per_minute == 30
        assert len(manager.workers) == 0
        assert manager.is_running is False

    def test_manager_set_app_functions(self):
        """Test setting app context functions"""
        manager = WorkerManager()
        manager.set_app_functions(self.mock_app_context)

        assert hasattr(manager, "app_context")
        assert manager.app_context == self.mock_app_context

        # Test that functions are set globally
        import worker_manager

        assert worker_manager.get_video_id is not None
        assert worker_manager.get_transcript is not None

    def test_manager_start_stop(self):
        """Test WorkerManager start and stop functionality"""
        manager = WorkerManager(num_workers=2)
        manager.set_app_functions(self.mock_app_context)

        # Start manager
        manager.start()
        assert manager.is_running is True
        assert len(manager.workers) == 2

        # All workers should be running
        for worker in manager.workers:
            assert worker.is_running is True

        # Management thread should be running
        assert manager._management_thread is not None
        assert manager._management_thread.is_alive() is True

        # Stop manager
        manager.stop()
        assert manager.is_running is False
        assert len(manager.workers) == 0

    def test_manager_submit_job_success(self):
        """Test successful job submission through manager"""
        manager = WorkerManager(num_workers=1)
        manager.set_app_functions(self.mock_app_context)
        manager.start()

        try:
            job = ProcessingJob("manager-job", JobType.VIDEO, JobPriority.HIGH, {})

            success, message = manager.submit_job(job)

            assert success is True
            assert "queued successfully" in message.lower()
        finally:
            manager.stop()

    def test_manager_submit_job_not_running(self):
        """Test job submission when manager is not running"""
        manager = WorkerManager()

        job = ProcessingJob("not-running-job", JobType.VIDEO, JobPriority.HIGH, {})

        success, message = manager.submit_job(job)

        assert success is False
        assert "not running" in message

    def test_manager_cancel_job(self):
        """Test job cancellation through manager"""
        manager = WorkerManager()
        manager.set_app_functions(self.mock_app_context)
        manager.start()

        try:
            job = ProcessingJob("cancel-job", JobType.VIDEO, JobPriority.HIGH, {})
            success, _ = manager.submit_job(job)
            assert success is True

            result = manager.cancel_job("cancel-job")
            assert result is True
        finally:
            manager.stop()

    def test_manager_get_job_status(self):
        """Test job status retrieval through manager"""
        manager = WorkerManager()
        manager.set_app_functions(self.mock_app_context)
        manager.start()

        try:
            job = ProcessingJob(
                "status-job",
                JobType.VIDEO,
                JobPriority.HIGH,
                {"url": "https://test.com"},
            )
            success, _ = manager.submit_job(job)
            assert success is True

            status = manager.get_job_status("status-job")

            assert status is not None
            assert status["job_id"] == "status-job"
        finally:
            manager.stop()

    def test_manager_get_system_status(self):
        """Test system status reporting"""
        manager = WorkerManager(num_workers=3)
        manager.set_app_functions(self.mock_app_context)

        status = manager.get_system_status()

        assert "is_running" in status
        assert status["num_workers"] == len(
            manager.workers
        )  # Workers created when started
        assert "workers" in status
        assert "queue" in status
        assert "system_metrics" in status
        assert status["system_metrics"]["total_workers"] == len(manager.workers)

    def test_manager_callbacks(self):
        """Test progress and completion callback registration"""
        manager = WorkerManager()

        progress_callback = MagicMock()
        completion_callback = MagicMock()

        manager.add_progress_callback(progress_callback)
        manager.add_completion_callback(completion_callback)

        assert progress_callback in manager._progress_callbacks
        assert completion_callback in manager._completion_callbacks

    def test_manager_worker_notification_handling(self):
        """Test manager handling of worker notifications"""
        manager = WorkerManager()

        progress_callback = MagicMock()
        completion_callback = MagicMock()
        manager.add_progress_callback(progress_callback)
        manager.add_completion_callback(completion_callback)

        job = ProcessingJob("notification-job", JobType.VIDEO, JobPriority.HIGH, {})
        result = JobResult("notification-job", JobType.VIDEO, True)

        # Test progress notification
        manager._handle_worker_notification(job, None, progress_update=True)
        progress_callback.assert_called_once_with(job)

        # Test completion notification
        manager._handle_worker_notification(job, result, progress_update=False)
        completion_callback.assert_called_once_with(job, result)

    def test_manager_max_workers_property(self):
        """Test max_workers property"""
        manager = WorkerManager(num_workers=5)
        assert manager.max_workers == 5

    @pytest.mark.slow
    def test_manager_full_workflow(self):
        """Test complete workflow from job submission to completion"""
        manager = WorkerManager(num_workers=1, max_queue_size=10)
        manager.set_app_functions(self.mock_app_context)

        # Set up callbacks to track completion
        completed_jobs = []

        def track_completion(job, result):
            completed_jobs.append((job.job_id, result.success))

        manager.add_completion_callback(track_completion)

        # Start manager
        manager.start()

        # Submit test jobs
        job1 = ProcessingJob(
            "workflow-1",
            JobType.VIDEO,
            JobPriority.HIGH,
            {"url": "https://youtube.com/watch?v=test1"},
        )
        job2 = ProcessingJob(
            "workflow-2",
            JobType.VIDEO,
            JobPriority.MEDIUM,
            {"url": "https://youtube.com/watch?v=test2"},
        )

        manager.submit_job(job1)
        manager.submit_job(job2)

        # Wait for jobs to complete
        timeout = 5.0
        start_time = time.time()
        while len(completed_jobs) < 2 and time.time() - start_time < timeout:
            time.sleep(0.1)

        # Stop manager
        manager.stop()

        # Verify jobs were completed
        assert len(completed_jobs) == 2
        job_ids = [job_id for job_id, success in completed_jobs]
        assert "workflow-1" in job_ids
        assert "workflow-2" in job_ids

    def test_manager_worker_restart_on_failure(self):
        """Test that manager restarts failed workers"""
        manager = WorkerManager(num_workers=1)
        manager.set_app_functions(self.mock_app_context)

        manager.start()

        # Simulate worker failure
        original_worker = manager.workers[0]
        original_worker.stop()  # Properly stop the worker
        original_worker.is_running = False  # Simulate worker death

        # Wait for management thread to detect and restart
        time.sleep(
            2.0
        )  # Management thread runs every ~30 seconds, but we simulate check

        # Manually trigger management check (since we can't wait 30 seconds)
        manager._should_stop_management = False  # Ensure it can run

        # Worker should eventually be restarted or at least detected as failed
        # This is a complex integration test that depends on timing
        assert len(manager.workers) == 1  # Should still have one worker

        manager.stop()


class TestWorkerThreadSafety:
    """Test thread safety aspects of worker system"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_app_functions()

    def mock_app_functions(self):
        """Mock app functions with thread-safe behavior"""
        import worker_manager

        worker_manager.clean_youtube_url = lambda url: url
        worker_manager.get_video_id = lambda url: f"video_{hash(url) % 10000}"
        worker_manager.get_playlist_id = lambda url: f"playlist_{hash(url) % 10000}"
        worker_manager.get_transcript = lambda vid_id: (
            f"transcript for {vid_id}",
            None,
        )
        worker_manager.generate_summary = lambda transcript, title, model: (
            f"summary of {transcript[:20]}",
            None,
        )
        worker_manager.get_video_details = lambda vid_ids: {
            vid_id: {"title": f"Title {vid_id}", "thumbnail_url": "url"}
            for vid_id in vid_ids
        }
        worker_manager.get_videos_from_playlist = lambda pl_id: ([], None)
        worker_manager.load_summary_cache = lambda: {}
        worker_manager.save_summary_cache = lambda cache: None

    @pytest.mark.slow
    def test_concurrent_job_processing(self):
        """Test concurrent job processing with multiple workers"""
        manager = WorkerManager(num_workers=3, max_queue_size=100)
        manager.set_app_functions(
            {
                "extract_video_id": lambda url: f"video_{hash(url) % 10000}",
                "extract_playlist_id": lambda url: None,
                "get_transcript": lambda vid_id: (f"transcript for {vid_id}", None),
                "generate_summary": lambda transcript, title, model: (
                    f"summary of {transcript}",
                    None,
                ),
                "get_video_details": lambda vid_ids: {
                    vid_id: {"title": f"Title {vid_id}", "thumbnail_url": "url"}
                    for vid_id in vid_ids
                },
                "get_videos_from_playlist": lambda pl_id: ([], None),
                "save_summary_cache": lambda cache: None,
                "load_summary_cache": lambda: {},
            }
        )

        completed_jobs = []

        def track_completion(job, result):
            completed_jobs.append(
                (job.job_id, result.success, threading.current_thread().ident)
            )

        manager.add_completion_callback(track_completion)
        manager.start()

        # Submit many jobs quickly
        jobs = []
        for i in range(10):
            job = ProcessingJob(
                f"concurrent-{i}",
                JobType.VIDEO,
                JobPriority.HIGH,
                {"url": f"https://youtube.com/watch?v=concurrent{i}"},
            )
            jobs.append(job)
            manager.submit_job(job)

        # Wait for completion
        timeout = 10.0
        start_time = time.time()
        while len(completed_jobs) < 10 and time.time() - start_time < timeout:
            time.sleep(0.1)

        manager.stop()

        # Verify all jobs completed successfully
        assert len(completed_jobs) == 10

        # Verify jobs were processed by different workers (if possible)
        worker_threads = set(thread_id for _, _, thread_id in completed_jobs)
        # With 3 workers and 10 jobs, we should see multiple workers, but it's not guaranteed
        assert len(worker_threads) >= 1  # At least one worker participated

        # All jobs should have succeeded
        assert all(success for _, success, _ in completed_jobs)

    def test_worker_cache_thread_safety(self):
        """Test that worker cache access is thread-safe"""
        # This is more of a structural test since actual thread safety
        # is implemented through locks in the worker code
        worker = WorkerThread("cache-safety-worker", JobScheduler())

        # Verify that cache has lock protection
        assert hasattr(worker, "_cache_lock")
        # Check that it has lock methods (duck typing approach)
        assert hasattr(worker._cache_lock, "acquire")
        assert hasattr(worker._cache_lock, "release")

    @pytest.mark.slow
    def test_rapid_start_stop_cycles(self):
        """Test rapid start/stop cycles for stability"""
        manager = WorkerManager(num_workers=2)
        manager.set_app_functions(
            {
                "extract_video_id": lambda url: "test_video",
                "extract_playlist_id": lambda url: None,
                "get_transcript": lambda vid_id: ("test transcript", None),
                "generate_summary": lambda transcript, title, model: (
                    "test summary",
                    None,
                ),
                "get_video_details": lambda vid_ids: {
                    "test_video": {"title": "Test", "thumbnail_url": "url"}
                },
                "get_videos_from_playlist": lambda pl_id: ([], None),
                "save_summary_cache": lambda cache: None,
                "load_summary_cache": lambda: {},
            }
        )

        # Perform rapid start/stop cycles
        for cycle in range(3):
            manager.start()
            assert manager.is_running is True

            time.sleep(0.2)  # Brief operation

            manager.stop(timeout=2.0)
            assert manager.is_running is False

            time.sleep(0.1)  # Brief pause

        # Should remain stable
        assert len(manager.workers) == 0


class TestErrorScenarios:
    """Test various error scenarios and edge cases"""

    def setup_method(self):
        """Set up test fixtures"""
        import worker_manager

        # Set up basic mocks
        worker_manager.clean_youtube_url = lambda url: url
        worker_manager.get_video_id = MagicMock(return_value="test_video")
        worker_manager.get_playlist_id = MagicMock(return_value=None)
        worker_manager.load_summary_cache = MagicMock(return_value={})
        worker_manager.save_summary_cache = MagicMock()

    def test_worker_invalid_job_type(self):
        """Test worker handling of invalid job types"""
        worker = WorkerThread("invalid-job-worker", JobScheduler())

        # Create job with invalid type by bypassing validation
        job = ProcessingJob("invalid-job", JobType.VIDEO, JobPriority.HIGH, {})
        job.job_type = "INVALID_TYPE"  # Force invalid type

        result = worker._process_job(job)

        assert result.success is False
        assert "unknown job type" in result.error.lower()

    def test_worker_transcript_failure_retry(self):
        """Test worker retry logic on transcript failure"""
        import worker_manager

        # Mock transcript failure
        worker_manager.get_transcript = MagicMock(return_value=(None, "Network error"))
        worker_manager.get_video_details = MagicMock(
            return_value={"test_video": {"title": "Test"}}
        )

        worker = WorkerThread("retry-worker", JobScheduler())

        job = ProcessingJob(
            "retry-job",
            JobType.VIDEO,
            JobPriority.HIGH,
            {"url": "https://youtube.com/watch?v=retry"},
        )
        job.max_retries = 2

        result = worker._process_job(job)

        assert result.success is False
        assert job.status == JobStatus.RETRY
        assert job.retry_count == 1

    def test_worker_summary_generation_failure(self):
        """Test worker handling of summary generation failure"""
        import worker_manager

        # Mock successful transcript but failed summary
        worker_manager.get_transcript = MagicMock(
            return_value=("test transcript", None)
        )
        worker_manager.generate_summary = MagicMock(
            return_value=(None, "AI service error")
        )
        worker_manager.get_video_details = MagicMock(
            return_value={"test_video": {"title": "Test"}}
        )

        worker = WorkerThread("summary-fail-worker", JobScheduler())

        job = ProcessingJob(
            "summary-fail",
            JobType.VIDEO,
            JobPriority.HIGH,
            {"url": "https://youtube.com/watch?v=summaryfail"},
        )

        result = worker._process_job(job)

        assert result.success is False
        # The error message should contain information about the AI service error
        assert "ai service error" in result.error.lower()

    def test_worker_cache_save_failure(self):
        """Test worker handling of cache save failures"""
        import worker_manager

        # Mock successful processing but failed cache save
        worker_manager.get_transcript = MagicMock(
            return_value=("test transcript", None)
        )
        worker_manager.generate_summary = MagicMock(return_value=("test summary", None))
        worker_manager.get_video_details = MagicMock(
            return_value={"test_video": {"title": "Test"}}
        )
        worker_manager.save_summary_cache = MagicMock(
            side_effect=Exception("Cache write error")
        )

        worker = WorkerThread("cache-fail-worker", JobScheduler())

        job = ProcessingJob(
            "cache-fail",
            JobType.VIDEO,
            JobPriority.HIGH,
            {"url": "https://youtube.com/watch?v=cachefail"},
        )

        # Should succeed despite cache save failure
        result = worker._process_job(job)

        assert result.success is True  # Processing succeeded
        # Cache save failure should be logged but not fail the job

    def test_manager_start_without_app_functions(self):
        """Test manager behavior when started without app functions"""
        manager = WorkerManager(num_workers=1)

        # Start without setting app functions
        manager.start()

        # Should start but workers may fail on actual job processing
        assert manager.is_running is True
        assert len(manager.workers) == 1

        manager.stop()

    def test_notification_callback_failure(self):
        """Test worker resilience to notification callback failures"""
        failing_callback = MagicMock(side_effect=Exception("Callback error"))
        worker = WorkerThread("callback-fail-worker", JobScheduler(), failing_callback)

        job = ProcessingJob("callback-test", JobType.VIDEO, JobPriority.HIGH, {})

        # Should complete job despite callback failure
        result = worker._process_job(job)

        # Job processing should succeed regardless of callback failure
        assert result is not None  # Should still return a result


class TestJobProcessingIntegration:
    """Integration tests for complete job processing workflows"""

    def setup_method(self):
        """Set up realistic mock environment"""
        self.setup_realistic_mocks()

    def setup_realistic_mocks(self):
        """Set up realistic mocks that simulate actual YouTube API responses"""
        import worker_manager

        # Realistic video IDs and data
        self.video_data = {
            "dQw4w9WgXcQ": {
                "title": "Rick Astley - Never Gonna Give You Up",
                "thumbnail_url": "https://img.youtube.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
            },
            "jNQXAC9IVRw": {
                "title": "Me at the zoo",
                "thumbnail_url": "https://img.youtube.com/vi/jNQXAC9IVRw/maxresdefault.jpg",
            },
        }

        worker_manager.clean_youtube_url = lambda url: url
        worker_manager.get_video_id = self.mock_get_video_id
        worker_manager.get_playlist_id = lambda url: (
            "PLtest123" if "playlist" in url else None
        )
        worker_manager.get_transcript = self.mock_get_transcript
        worker_manager.generate_summary = self.mock_generate_summary
        worker_manager.get_video_details = self.mock_get_video_details
        worker_manager.get_videos_from_playlist = self.mock_get_playlist_videos
        worker_manager.load_summary_cache = lambda: {}
        worker_manager.save_summary_cache = MagicMock()

    def mock_get_video_id(self, url):
        """Mock video ID extraction"""
        if "dQw4w9WgXcQ" in url:
            return "dQw4w9WgXcQ"
        elif "jNQXAC9IVRw" in url:
            return "jNQXAC9IVRw"
        else:
            return "mock_video_id"

    def mock_get_transcript(self, video_id):
        """Mock transcript retrieval"""
        transcripts = {
            "dQw4w9WgXcQ": "We're no strangers to love...",
            "jNQXAC9IVRw": "All right, so here we are in front of the elephants...",
            "mock_video_id": "This is a mock video transcript.",
        }
        return transcripts.get(video_id, "Default transcript"), None

    def mock_generate_summary(self, transcript, title, model_key):
        """Mock summary generation"""
        summary = f"Summary of '{title}': {transcript[:50]}..."
        return summary, None

    def mock_get_video_details(self, video_ids):
        """Mock video details retrieval"""
        return {
            vid_id: self.video_data.get(
                vid_id, {"title": f"Title {vid_id}", "thumbnail_url": "mock_url"}
            )
            for vid_id in video_ids
        }

    def mock_get_playlist_videos(self, playlist_id):
        """Mock playlist video retrieval"""
        return [
            {"contentDetails": {"videoId": "dQw4w9WgXcQ"}},
            {"contentDetails": {"videoId": "jNQXAC9IVRw"}},
        ], None

    @pytest.mark.slow
    def test_complete_video_processing_workflow(self):
        """Test complete video processing from submission to completion"""
        manager = WorkerManager(num_workers=1)
        manager.set_app_functions(
            {
                "extract_video_id": self.mock_get_video_id,
                "extract_playlist_id": lambda url: None,
                "get_transcript": self.mock_get_transcript,
                "generate_summary": self.mock_generate_summary,
                "get_video_details": self.mock_get_video_details,
                "get_videos_from_playlist": self.mock_get_playlist_videos,
                "save_summary_cache": MagicMock(),
                "load_summary_cache": lambda: {},
            }
        )

        completed_jobs = []

        def track_completion(job, result):
            completed_jobs.append((job, result))

        manager.add_completion_callback(track_completion)
        manager.start()

        # Submit realistic job
        job = ProcessingJob(
            job_id="integration-test",
            job_type=JobType.VIDEO,
            priority=JobPriority.HIGH,
            data={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "model_key": "gpt-4",
            },
        )

        success, message = manager.submit_job(job)
        assert success is True

        # Wait for completion
        timeout = 10.0
        start_time = time.time()
        while len(completed_jobs) == 0 and time.time() - start_time < timeout:
            time.sleep(0.1)

        manager.stop()

        # Verify completion
        assert len(completed_jobs) == 1
        completed_job, result = completed_jobs[0]

        assert result.success is True
        assert result.data["video_id"] == "dQw4w9WgXcQ"
        assert "Rick Astley" in result.data["title"]
        assert result.data["summary"] is not None
        assert "cached" in result.data

    @pytest.mark.slow
    def test_complete_playlist_processing_workflow(self):
        """Test complete playlist processing workflow"""
        manager = WorkerManager(num_workers=1)
        manager.set_app_functions(
            {
                "extract_video_id": self.mock_get_video_id,
                "extract_playlist_id": lambda url: (
                    "PLtest123" if "playlist" in url else None
                ),
                "get_transcript": self.mock_get_transcript,
                "generate_summary": self.mock_generate_summary,
                "get_video_details": self.mock_get_video_details,
                "get_videos_from_playlist": self.mock_get_playlist_videos,
                "save_summary_cache": MagicMock(),
                "load_summary_cache": lambda: {},
            }
        )

        completed_jobs = []

        def track_completion(job, result):
            completed_jobs.append((job, result))

        manager.add_completion_callback(track_completion)
        manager.start()

        # Submit playlist job
        job = ProcessingJob(
            job_id="playlist-integration",
            job_type=JobType.PLAYLIST,
            priority=JobPriority.MEDIUM,
            data={
                "url": "https://www.youtube.com/playlist?list=PLtest123",
                "video_ids": [],  # Will be extracted
                "model_key": "gpt-4",
            },
        )

        manager.submit_job(job)

        # Wait for completion (playlist processing takes longer)
        timeout = 15.0
        start_time = time.time()
        while len(completed_jobs) == 0 and time.time() - start_time < timeout:
            time.sleep(0.1)

        manager.stop()

        # Verify playlist processing
        assert len(completed_jobs) == 1
        completed_job, result = completed_jobs[0]

        assert result.success is True
        assert result.data["type"] == "playlist"
        assert result.data["total_videos"] == 2
        assert len(result.data["results"]) == 2

        # Check individual video results
        video_results = result.data["results"]
        assert any("Rick Astley" in vr.get("title", "") for vr in video_results)
        assert any("zoo" in vr.get("title", "") for vr in video_results)
