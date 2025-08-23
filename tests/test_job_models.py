"""
Test suite for job_models.py

Validates job data structures, status transitions, factory functions, and metrics.
Tests all JobStatus transitions, ProcessingJob lifecycle, WorkerMetrics tracking,
and factory function behavior with various inputs.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from job_models import (
    JobPriority,
    JobResult,
    JobStatus,
    JobType,
    ProcessingJob,
    WorkerMetrics,
    create_batch_job,
    create_playlist_job,
    create_video_job,
)


class TestJobEnums:
    """Test job enumeration values and properties"""

    def test_job_status_values(self):
        """Validate all JobStatus enum values"""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.IN_PROGRESS.value == "in_progress"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.RETRY.value == "retry"

    def test_job_priority_ordering(self):
        """Test that JobPriority values maintain correct ordering (lower = higher priority)"""
        assert JobPriority.HIGH.value == 1
        assert JobPriority.MEDIUM.value == 2
        assert JobPriority.LOW.value == 3

        # Verify ordering
        assert JobPriority.HIGH.value < JobPriority.MEDIUM.value < JobPriority.LOW.value

    def test_job_type_values(self):
        """Validate all JobType enum values"""
        assert JobType.VIDEO.value == "video"
        assert JobType.PLAYLIST.value == "playlist"
        assert JobType.BATCH.value == "batch"


class TestProcessingJob:
    """Test ProcessingJob data model and lifecycle methods"""

    def test_job_creation_with_defaults(self):
        """Test ProcessingJob creation with default values"""
        job = ProcessingJob(
            job_id="test-123",
            job_type=JobType.VIDEO,
            priority=JobPriority.HIGH,
            data={"url": "https://youtube.com/watch?v=test"},
        )

        assert job.job_id == "test-123"
        assert job.job_type == JobType.VIDEO
        assert job.priority == JobPriority.HIGH
        assert job.status == JobStatus.PENDING
        assert job.progress == 0.0
        assert job.retry_count == 0
        assert job.max_retries == 3
        assert job.total_steps == 3  # Video jobs have 3 steps
        assert isinstance(job.created_at, datetime)
        assert job.started_at is None
        assert job.completed_at is None
        assert job.error_message is None
        assert job.result is None
        assert job.worker_id is None

    def test_job_auto_id_generation(self):
        """Test automatic job ID generation when not provided"""
        job = ProcessingJob(job_id="", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        # Should generate a UUID
        assert job.job_id != ""
        assert len(job.job_id) == 36  # UUID length
        # Validate UUID format
        uuid.UUID(job.job_id)

    def test_total_steps_calculation_video(self):
        """Test total_steps calculation for video jobs"""
        job = ProcessingJob(job_id="test-video", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        assert job.total_steps == 3

    def test_total_steps_calculation_playlist(self):
        """Test total_steps calculation for playlist jobs"""
        job = ProcessingJob(
            job_id="test-playlist",
            job_type=JobType.PLAYLIST,
            priority=JobPriority.MEDIUM,
            data={"video_ids": ["vid1", "vid2", "vid3", "vid4", "vid5"]},
        )

        # 5 videos + 2 overhead steps
        assert job.total_steps == 7

    def test_total_steps_calculation_batch(self):
        """Test total_steps calculation for batch jobs"""
        job = ProcessingJob(
            job_id="test-batch",
            job_type=JobType.BATCH,
            priority=JobPriority.LOW,
            data={"urls": ["url1", "url2", "url3"]},
        )

        assert job.total_steps == 3

    def test_update_progress_basic(self):
        """Test basic progress update functionality"""
        job = ProcessingJob(job_id="test-progress", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        job.update_progress(0.5, "Halfway done")

        assert job.progress == 0.5
        assert job.current_step == "Halfway done"

    def test_update_progress_with_increment(self):
        """Test progress update with step increment"""
        job = ProcessingJob(job_id="test-increment", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})
        job.total_steps = 4

        job.update_progress(0.25, "First step", increment=True)
        assert job.progress == 0.25
        assert job.current_step == "First step"

        job.update_progress(0.75, increment=True)
        assert job.progress == 0.75
        # Step calculation: int(0.75 * 4) + 1 = int(3.0) + 1 = 4
        assert "Step 4 of 4" in job.current_step

    def test_update_progress_bounds(self):
        """Test progress update bounds checking (0.0 to 1.0)"""
        job = ProcessingJob(job_id="test-bounds", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        # Test upper bound
        job.update_progress(1.5)
        assert job.progress == 1.0

        # Test lower bound
        job.update_progress(-0.5)
        assert job.progress == 0.0

    def test_start_processing(self):
        """Test job start processing workflow"""
        job = ProcessingJob(job_id="test-start", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        start_time_before = datetime.now(timezone.utc)
        job.start_processing("worker-1")
        start_time_after = datetime.now(timezone.utc)

        assert job.status == JobStatus.IN_PROGRESS
        assert job.worker_id == "worker-1"
        assert job.progress == 0.0
        assert job.current_step == "Starting processing..."
        assert start_time_before <= job.started_at <= start_time_after

    def test_complete_successfully(self):
        """Test successful job completion"""
        job = ProcessingJob(job_id="test-complete", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        job.start_processing("worker-1")

        result_data = {"summary": "Test summary", "video_id": "test123"}
        completion_time_before = datetime.now(timezone.utc)
        job.complete_successfully(result_data)
        completion_time_after = datetime.now(timezone.utc)

        assert job.status == JobStatus.COMPLETED
        assert job.result == result_data
        assert job.progress == 1.0
        assert job.current_step == "Completed"
        assert completion_time_before <= job.completed_at <= completion_time_after

    def test_fail_with_error_no_retry(self):
        """Test job failure without retry option"""
        job = ProcessingJob(job_id="test-fail-no-retry", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        job.start_processing("worker-1")

        error_message = "Network error occurred"
        job.fail_with_error(error_message, can_retry=False)

        assert job.status == JobStatus.FAILED
        assert job.error_message == error_message
        assert job.retry_count == 0
        assert job.completed_at is not None

    def test_fail_with_error_with_retry(self):
        """Test job failure with retry option"""
        job = ProcessingJob(job_id="test-fail-retry", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        job.start_processing("worker-1")

        error_message = "Temporary network error"
        job.fail_with_error(error_message, can_retry=True)

        assert job.status == JobStatus.RETRY
        assert job.error_message == error_message
        assert job.retry_count == 1
        assert job.completed_at is None
        assert "Retrying (attempt 2/4)" in job.current_step

    def test_fail_with_error_max_retries_reached(self):
        """Test job failure when max retries are reached"""
        job = ProcessingJob(job_id="test-max-retries", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})
        job.max_retries = 2
        job.retry_count = 2  # Already at max retries

        job.start_processing("worker-1")
        job.fail_with_error("Still failing", can_retry=True)

        assert job.status == JobStatus.FAILED
        assert job.retry_count == 2  # No increment
        assert job.completed_at is not None

    def test_reset_for_retry(self):
        """Test job reset for retry functionality"""
        job = ProcessingJob(job_id="test-reset", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        # Simulate job processing and failure
        job.start_processing("worker-1")
        job.update_progress(0.5, "Halfway done")
        job.fail_with_error("Temporary error", can_retry=True)

        # Reset for retry
        job.reset_for_retry()

        assert job.status == JobStatus.PENDING
        assert job.started_at is None
        assert job.worker_id is None
        assert job.progress == 0.0
        assert job.current_step == "Waiting for retry..."

    def test_get_processing_time_completed(self):
        """Test processing time calculation for completed jobs"""
        job = ProcessingJob(job_id="test-timing", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        # Mock specific times
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(seconds=30)

        job.started_at = start_time
        job.completed_at = end_time

        processing_time = job.get_processing_time()
        assert processing_time == 30.0

    def test_get_processing_time_not_completed(self):
        """Test processing time for jobs that haven't completed"""
        job = ProcessingJob(job_id="test-no-timing", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        assert job.get_processing_time() is None

        job.start_processing("worker-1")
        assert job.get_processing_time() is None

    def test_get_wait_time(self):
        """Test wait time calculation"""
        job = ProcessingJob(job_id="test-wait", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        # Mock creation time to 10 seconds ago
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        job.created_at = past_time

        wait_time = job.get_wait_time()
        assert 9 <= wait_time <= 11  # Allow for small timing variations

    def test_to_dict_serialization(self):
        """Test job serialization to dictionary"""
        job = ProcessingJob(
            job_id="test-serialize",
            job_type=JobType.VIDEO,
            priority=JobPriority.HIGH,
            data={"url": "https://test.com"},
            client_id="client-123",
            session_id="session-456",
        )

        job_dict = job.to_dict()

        assert job_dict["job_id"] == "test-serialize"
        assert job_dict["job_type"] == "video"
        assert job_dict["priority"] == 1
        assert job_dict["status"] == "pending"
        assert job_dict["data"] == {"url": "https://test.com"}
        assert job_dict["client_id"] == "client-123"
        assert job_dict["session_id"] == "session-456"
        assert job_dict["progress"] == 0.0
        assert job_dict["retry_count"] == 0
        assert job_dict["max_retries"] == 3
        assert "created_at" in job_dict
        assert job_dict["started_at"] is None
        assert job_dict["completed_at"] is None

    def test_from_dict_deserialization(self):
        """Test job creation from dictionary"""
        job_data = {
            "job_id": "test-deserialize",
            "job_type": "video",
            "priority": 1,
            "status": "pending",
            "data": {"url": "https://test.com"},
            "created_at": "2024-01-01T12:00:00+00:00",
            "started_at": None,
            "completed_at": None,
            "progress": 0.0,
            "current_step": "",
            "total_steps": 3,
            "retry_count": 0,
            "max_retries": 3,
            "error_message": None,
            "result": None,
            "worker_id": None,
            "client_id": "client-123",
            "session_id": "session-456",
        }

        job = ProcessingJob.from_dict(job_data)

        assert job.job_id == "test-deserialize"
        assert job.job_type == JobType.VIDEO
        assert job.priority == JobPriority.HIGH
        assert job.status == JobStatus.PENDING
        assert job.data == {"url": "https://test.com"}
        assert job.client_id == "client-123"
        assert job.session_id == "session-456"
        assert isinstance(job.created_at, datetime)

    def test_serialization_roundtrip(self):
        """Test that serialization and deserialization preserve job data"""
        original_job = ProcessingJob(
            job_id="roundtrip-test",
            job_type=JobType.PLAYLIST,
            priority=JobPriority.MEDIUM,
            data={"url": "https://test.com", "video_ids": ["1", "2", "3"]},
            client_id="client-roundtrip",
            session_id="session-roundtrip",
        )

        # Start and complete processing
        original_job.start_processing("worker-test")
        original_job.update_progress(0.8, "Almost done")
        original_job.complete_successfully({"result": "success"})

        # Serialize and deserialize
        job_dict = original_job.to_dict()
        restored_job = ProcessingJob.from_dict(job_dict)

        # Verify all important fields match
        assert restored_job.job_id == original_job.job_id
        assert restored_job.job_type == original_job.job_type
        assert restored_job.priority == original_job.priority
        assert restored_job.status == original_job.status
        assert restored_job.data == original_job.data
        assert restored_job.progress == original_job.progress
        assert restored_job.current_step == original_job.current_step
        assert restored_job.result == original_job.result
        assert restored_job.worker_id == original_job.worker_id


class TestJobResult:
    """Test JobResult data model"""

    def test_job_result_creation_success(self):
        """Test creating successful JobResult"""
        result = JobResult(
            job_id="test-result-123",
            job_type=JobType.VIDEO,
            success=True,
            data={"summary": "Test summary"},
            processing_time=30.5,
        )

        assert result.job_id == "test-result-123"
        assert result.job_type == JobType.VIDEO
        assert result.success is True
        assert result.data == {"summary": "Test summary"}
        assert result.error is None
        assert result.processing_time == 30.5

    def test_job_result_creation_failure(self):
        """Test creating failed JobResult"""
        result = JobResult(
            job_id="test-fail-result",
            job_type=JobType.PLAYLIST,
            success=False,
            error="Network timeout",
            processing_time=15.2,
        )

        assert result.job_id == "test-fail-result"
        assert result.job_type == JobType.PLAYLIST
        assert result.success is False
        assert result.data is None
        assert result.error == "Network timeout"
        assert result.processing_time == 15.2

    def test_job_result_to_dict(self):
        """Test JobResult serialization"""
        result = JobResult(
            job_id="dict-test", job_type=JobType.BATCH, success=True, data={"results": [1, 2, 3]}, processing_time=45.7
        )

        result_dict = result.to_dict()

        assert result_dict["job_id"] == "dict-test"
        assert result_dict["job_type"] == "batch"
        assert result_dict["success"] is True
        assert result_dict["data"] == {"results": [1, 2, 3]}
        assert result_dict["error"] is None
        assert result_dict["processing_time"] == 45.7


class TestWorkerMetrics:
    """Test WorkerMetrics tracking functionality"""

    def test_metrics_initialization(self):
        """Test WorkerMetrics initialization"""
        metrics = WorkerMetrics()

        assert metrics.jobs_processed == 0
        assert metrics.jobs_failed == 0
        assert metrics.total_processing_time == 0.0
        assert isinstance(metrics.created_at, datetime)
        assert metrics.last_job_at is None

    def test_record_job_completion_success(self):
        """Test recording successful job completion"""
        metrics = WorkerMetrics()

        before_time = datetime.now(timezone.utc)
        metrics.record_job_completion(25.5, success=True)
        after_time = datetime.now(timezone.utc)

        assert metrics.jobs_processed == 1
        assert metrics.jobs_failed == 0
        assert metrics.total_processing_time == 25.5
        assert before_time <= metrics.last_job_at <= after_time

    def test_record_job_completion_failure(self):
        """Test recording failed job completion"""
        metrics = WorkerMetrics()

        metrics.record_job_completion(15.0, success=False)

        assert metrics.jobs_processed == 1
        assert metrics.jobs_failed == 1
        assert metrics.total_processing_time == 15.0
        assert metrics.last_job_at is not None

    def test_multiple_job_completions(self):
        """Test recording multiple job completions"""
        metrics = WorkerMetrics()

        metrics.record_job_completion(10.0, success=True)
        metrics.record_job_completion(20.0, success=False)
        metrics.record_job_completion(15.0, success=True)

        assert metrics.jobs_processed == 3
        assert metrics.jobs_failed == 1
        assert metrics.total_processing_time == 45.0

    def test_get_success_rate_no_jobs(self):
        """Test success rate calculation with no jobs"""
        metrics = WorkerMetrics()
        assert metrics.get_success_rate() == 0.0

    def test_get_success_rate_with_jobs(self):
        """Test success rate calculation with mixed results"""
        metrics = WorkerMetrics()

        # Record 3 successful, 1 failed
        metrics.record_job_completion(10.0, success=True)
        metrics.record_job_completion(10.0, success=True)
        metrics.record_job_completion(10.0, success=False)
        metrics.record_job_completion(10.0, success=True)

        success_rate = metrics.get_success_rate()
        assert success_rate == 75.0  # 3/4 = 75%

    def test_get_average_processing_time_no_jobs(self):
        """Test average processing time with no jobs"""
        metrics = WorkerMetrics()
        assert metrics.get_average_processing_time() == 0.0

    def test_get_average_processing_time_with_jobs(self):
        """Test average processing time calculation"""
        metrics = WorkerMetrics()

        metrics.record_job_completion(10.0, success=True)
        metrics.record_job_completion(20.0, success=True)
        metrics.record_job_completion(30.0, success=False)

        avg_time = metrics.get_average_processing_time()
        assert avg_time == 20.0  # (10 + 20 + 30) / 3

    def test_metrics_to_dict(self):
        """Test WorkerMetrics serialization"""
        metrics = WorkerMetrics()
        metrics.record_job_completion(25.0, success=True)
        metrics.record_job_completion(15.0, success=False)

        metrics_dict = metrics.to_dict()

        assert metrics_dict["jobs_processed"] == 2
        assert metrics_dict["jobs_failed"] == 1
        assert metrics_dict["success_rate"] == 50.0
        assert metrics_dict["average_processing_time"] == 20.0
        assert metrics_dict["total_processing_time"] == 40.0
        assert "created_at" in metrics_dict
        assert "last_job_at" in metrics_dict


class TestFactoryFunctions:
    """Test job factory functions for creating different job types"""

    def test_create_video_job_basic(self):
        """Test basic video job creation"""
        url = "https://www.youtube.com/watch?v=test123"
        job = create_video_job(url)

        assert job.job_type == JobType.VIDEO
        assert job.priority == JobPriority.HIGH
        assert job.data["url"] == url
        assert job.data["type"] == "video"
        assert job.data["model_key"] is None
        assert job.client_id is None
        assert job.session_id is None
        assert len(job.job_id) == 36  # UUID length

    def test_create_video_job_with_options(self):
        """Test video job creation with all options"""
        url = "https://www.youtube.com/watch?v=test456"
        model_key = "gpt-4"
        client_id = "client-test"
        session_id = "session-test"

        job = create_video_job(url, model_key, client_id, session_id)

        assert job.job_type == JobType.VIDEO
        assert job.priority == JobPriority.HIGH
        assert job.data["url"] == url
        assert job.data["model_key"] == model_key
        assert job.data["type"] == "video"
        assert job.client_id == client_id
        assert job.session_id == session_id

    def test_create_playlist_job_small(self):
        """Test playlist job creation with small playlist (<=10 videos)"""
        url = "https://www.youtube.com/playlist?list=test123"
        video_ids = ["vid1", "vid2", "vid3", "vid4", "vid5"]

        job = create_playlist_job(url, video_ids)

        assert job.job_type == JobType.PLAYLIST
        assert job.priority == JobPriority.MEDIUM  # <=10 videos
        assert job.data["url"] == url
        assert job.data["video_ids"] == video_ids
        assert job.data["type"] == "playlist"
        assert job.total_steps == 7  # 5 videos + 2 overhead

    def test_create_playlist_job_large(self):
        """Test playlist job creation with large playlist (>10 videos)"""
        url = "https://www.youtube.com/playlist?list=large123"
        video_ids = [f"vid{i}" for i in range(15)]  # 15 videos

        job = create_playlist_job(url, video_ids)

        assert job.job_type == JobType.PLAYLIST
        assert job.priority == JobPriority.LOW  # >10 videos
        assert job.data["video_ids"] == video_ids
        assert job.total_steps == 17  # 15 videos + 2 overhead

    def test_create_playlist_job_with_options(self):
        """Test playlist job creation with all options"""
        url = "https://www.youtube.com/playlist?list=options123"
        video_ids = ["vid1", "vid2"]
        model_key = "gemini-pro"
        client_id = "playlist-client"
        session_id = "playlist-session"

        job = create_playlist_job(url, video_ids, model_key, client_id, session_id)

        assert job.data["model_key"] == model_key
        assert job.client_id == client_id
        assert job.session_id == session_id

    def test_create_batch_job_single_url(self):
        """Test batch job creation with single URL (HIGH priority)"""
        urls = ["https://www.youtube.com/watch?v=single123"]

        job = create_batch_job(urls)

        assert job.job_type == JobType.BATCH
        assert job.priority == JobPriority.HIGH  # Single URL
        assert job.data["urls"] == urls
        assert job.data["type"] == "batch"
        assert job.total_steps == 1

    def test_create_batch_job_medium_batch(self):
        """Test batch job creation with medium batch (2-10 URLs)"""
        urls = [f"https://www.youtube.com/watch?v=test{i}" for i in range(5)]

        job = create_batch_job(urls)

        assert job.job_type == JobType.BATCH
        assert job.priority == JobPriority.MEDIUM  # 2-10 URLs
        assert job.data["urls"] == urls
        assert job.total_steps == 5

    def test_create_batch_job_large_batch(self):
        """Test batch job creation with large batch (>10 URLs)"""
        urls = [f"https://www.youtube.com/watch?v=test{i}" for i in range(15)]

        job = create_batch_job(urls)

        assert job.job_type == JobType.BATCH
        assert job.priority == JobPriority.LOW  # >10 URLs
        assert job.data["urls"] == urls
        assert job.total_steps == 15

    def test_create_batch_job_with_options(self):
        """Test batch job creation with all options"""
        urls = ["https://www.youtube.com/watch?v=batch1", "https://www.youtube.com/watch?v=batch2"]
        model_key = "claude-3"
        client_id = "batch-client"
        session_id = "batch-session"

        job = create_batch_job(urls, model_key, client_id, session_id)

        assert job.data["model_key"] == model_key
        assert job.client_id == client_id
        assert job.session_id == session_id


class TestJobStatusTransitions:
    """Test valid and invalid job status transitions"""

    def test_complete_workflow_success(self):
        """Test complete successful job workflow"""
        job = ProcessingJob(job_id="workflow-success", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        # Initial state
        assert job.status == JobStatus.PENDING

        # Start processing
        job.start_processing("worker-1")
        assert job.status == JobStatus.IN_PROGRESS

        # Complete successfully
        job.complete_successfully({"result": "success"})
        assert job.status == JobStatus.COMPLETED

    def test_complete_workflow_with_retry(self):
        """Test complete workflow with retry"""
        job = ProcessingJob(job_id="workflow-retry", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        # Initial state
        assert job.status == JobStatus.PENDING

        # Start processing
        job.start_processing("worker-1")
        assert job.status == JobStatus.IN_PROGRESS

        # Fail with retry
        job.fail_with_error("Temporary error", can_retry=True)
        assert job.status == JobStatus.RETRY
        assert job.retry_count == 1

        # Reset for retry
        job.reset_for_retry()
        assert job.status == JobStatus.PENDING

        # Process again
        job.start_processing("worker-2")
        assert job.status == JobStatus.IN_PROGRESS

        # Complete successfully
        job.complete_successfully({"result": "success"})
        assert job.status == JobStatus.COMPLETED

    def test_complete_workflow_final_failure(self):
        """Test workflow ending in final failure"""
        job = ProcessingJob(job_id="workflow-fail", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})
        job.max_retries = 1  # Lower for testing

        # Process and fail twice
        for attempt in range(2):
            if attempt > 0:
                job.reset_for_retry()

            job.start_processing(f"worker-{attempt + 1}")
            assert job.status == JobStatus.IN_PROGRESS

            job.fail_with_error(f"Error attempt {attempt + 1}", can_retry=True)

            if attempt == 0:
                assert job.status == JobStatus.RETRY
            else:
                assert job.status == JobStatus.FAILED  # Max retries reached

    def test_edge_case_transitions(self):
        """Test edge cases and boundary conditions"""
        job = ProcessingJob(job_id="edge-cases", job_type=JobType.VIDEO, priority=JobPriority.HIGH, data={})

        # Test multiple progress updates
        job.start_processing("worker-1")
        job.update_progress(0.2, "Step 1")
        job.update_progress(0.4, "Step 2")
        job.update_progress(0.6, "Step 3")
        assert job.progress == 0.6

        # Test completion after progress updates
        job.complete_successfully({"final": True})
        assert job.status == JobStatus.COMPLETED
        assert job.progress == 1.0
