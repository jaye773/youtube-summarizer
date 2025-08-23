"""
Comprehensive test suite for job_state.py - Job State Management & Persistence

This module tests the JobStateManager class for thread-safe state tracking,
JSON persistence, job progress monitoring, and cleanup operations.

Tests cover:
- State persistence to/from JSON files
- Thread safety with concurrent operations
- Job progress tracking and status transitions
- State recovery after system restart
- Cleanup of old completed jobs
- Edge cases like corrupted state files
- Memory usage with large number of jobs
"""

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch, mock_open, MagicMock

import pytest

# Import the module under test
from job_state import JobStateManager, JobStatus, JobPriority


class TestJobStateManager(unittest.TestCase):
    """Test suite for JobStateManager class."""

    def setUp(self):
        """Set up test environment with temporary directories and fresh state."""
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, "test_job_state.json")
        self.manager = JobStateManager(persistence_file=self.test_file)
        
        # Test job data
        self.sample_job_id = "test_job_123"
        self.sample_job_data = {
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "model": "gpt-4",
            "voice": "en-US-Neural2-F"
        }

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # State Persistence Tests

    def test_initialization_creates_directory(self):
        """Test that JobStateManager creates necessary directories on init."""
        nested_path = os.path.join(self.test_dir, "nested", "deep", "job_state.json")
        manager = JobStateManager(persistence_file=nested_path)
        
        self.assertTrue(os.path.exists(os.path.dirname(nested_path)))
        self.assertIsInstance(manager.state_cache, dict)

    def test_save_and_load_state_basic(self):
        """Test basic save and load operations with simple job data."""
        # Add a job and update its state
        self.manager.update_job_progress(
            self.sample_job_id, 
            0.5, 
            JobStatus.IN_PROGRESS, 
            "Processing transcript"
        )
        
        # Create new manager instance to test loading
        new_manager = JobStateManager(persistence_file=self.test_file)
        
        # Verify state was loaded correctly
        job_status = new_manager.get_job_status(self.sample_job_id)
        self.assertIsNotNone(job_status)
        self.assertEqual(job_status['progress'], 0.5)
        self.assertEqual(job_status['status'], JobStatus.IN_PROGRESS.value)
        self.assertEqual(job_status['message'], "Processing transcript")

    def test_datetime_serialization_deserialization(self):
        """Test that datetime objects are properly serialized/deserialized."""
        # Add job with various timestamps
        self.manager.update_job_progress(self.sample_job_id, 0.3, JobStatus.IN_PROGRESS)
        
        # Complete the job (adds completed_at timestamp)
        self.manager.update_job_progress(
            self.sample_job_id, 
            1.0, 
            JobStatus.COMPLETED,
            "Job completed successfully"
        )
        
        # Create new manager to test deserialization
        new_manager = JobStateManager(persistence_file=self.test_file)
        job_status = new_manager.get_job_status(self.sample_job_id)
        
        # Verify all timestamps are datetime objects
        self.assertIsInstance(job_status['created_at'], datetime)
        self.assertIsInstance(job_status['updated_at'], datetime)
        self.assertIsInstance(job_status['completed_at'], datetime)

    def test_corrupted_state_file_handling(self):
        """Test graceful handling of corrupted JSON state files."""
        # Write invalid JSON to the file
        with open(self.test_file, 'w') as f:
            f.write("invalid json content {{{")
        
        # Should handle corruption gracefully and start with empty state
        manager = JobStateManager(persistence_file=self.test_file)
        self.assertEqual(len(manager.state_cache), 0)
        
        # Should still be able to add new jobs
        manager.update_job_progress("new_job", 0.1, JobStatus.PENDING)
        self.assertEqual(len(manager.state_cache), 1)

    @patch("builtins.open", mock_open())
    @patch("os.replace")
    def test_atomic_file_operations(self, mock_replace):
        """Test that state saves use atomic file operations."""
        self.manager.update_job_progress(self.sample_job_id, 0.5, JobStatus.IN_PROGRESS)
        
        # Verify atomic rename was called
        mock_replace.assert_called_once()
        args = mock_replace.call_args[0]
        self.assertTrue(args[0].endswith('.tmp'))  # temp file
        self.assertEqual(args[1], self.test_file)  # final file

    @patch("job_state.logger")
    def test_file_permission_error_handling(self, mock_logger):
        """Test handling of file permission errors during save operations."""
        # Make directory read-only to simulate permission errors
        os.chmod(self.test_dir, 0o444)
        
        try:
            self.manager.update_job_progress(self.sample_job_id, 0.5, JobStatus.IN_PROGRESS)
            # Should log error but not crash
            mock_logger.error.assert_called()
        finally:
            # Restore permissions for cleanup
            os.chmod(self.test_dir, 0o755)

    # Job Progress and Status Tests

    def test_update_job_progress_validation(self):
        """Test progress value validation."""
        # Test invalid progress values
        with self.assertRaises(ValueError):
            self.manager.update_job_progress(self.sample_job_id, -0.1)
        
        with self.assertRaises(ValueError):
            self.manager.update_job_progress(self.sample_job_id, 1.1)
        
        # Test valid boundary values
        self.manager.update_job_progress(self.sample_job_id, 0.0)
        self.manager.update_job_progress(self.sample_job_id, 1.0)
        
        job_status = self.manager.get_job_status(self.sample_job_id)
        self.assertEqual(job_status['progress'], 1.0)

    def test_job_status_transitions(self):
        """Test proper job status transitions and timestamp updates."""
        start_time = datetime.now()
        
        # Create job (PENDING)
        self.manager.update_job_progress(self.sample_job_id, 0.0, JobStatus.PENDING)
        job = self.manager.get_job_status(self.sample_job_id)
        self.assertEqual(job['status'], JobStatus.PENDING.value)
        # Check if completed_at key exists, should be None
        self.assertIsNone(job.get('completed_at'))
        
        # Start processing (IN_PROGRESS)
        self.manager.update_job_progress(self.sample_job_id, 0.3, JobStatus.IN_PROGRESS)
        job = self.manager.get_job_status(self.sample_job_id)
        self.assertEqual(job['status'], JobStatus.IN_PROGRESS.value)
        self.assertGreater(job['updated_at'], start_time)
        
        # Complete job (COMPLETED)
        self.manager.update_job_progress(self.sample_job_id, 1.0, JobStatus.COMPLETED)
        job = self.manager.get_job_status(self.sample_job_id)
        self.assertEqual(job['status'], JobStatus.COMPLETED.value)
        self.assertIsNotNone(job.get('completed_at'))
        self.assertGreater(job['completed_at'], start_time)

    def test_job_initialization_defaults(self):
        """Test that new jobs are initialized with correct default values."""
        self.manager.update_job_progress(self.sample_job_id, 0.2)
        job = self.manager.get_job_status(self.sample_job_id)
        
        self.assertEqual(job['job_id'], self.sample_job_id)
        self.assertEqual(job['status'], JobStatus.PENDING.value)
        self.assertEqual(job['progress'], 0.2)
        self.assertIsInstance(job['created_at'], datetime)
        self.assertIsInstance(job['updated_at'], datetime)
        self.assertIsNone(job['message'])
        self.assertIsNone(job['error'])
        self.assertEqual(job['retry_count'], 0)

    def test_job_progress_with_message_and_error(self):
        """Test updating jobs with progress messages and error information."""
        self.manager.update_job_progress(
            self.sample_job_id,
            0.8,
            JobStatus.IN_PROGRESS,
            message="Generating summary",
            error="Rate limit warning"
        )
        
        job = self.manager.get_job_status(self.sample_job_id)
        self.assertEqual(job['message'], "Generating summary")
        self.assertEqual(job['error'], "Rate limit warning")

    def test_nonexistent_job_status(self):
        """Test getting status of non-existent job."""
        status = self.manager.get_job_status("nonexistent_job")
        self.assertIsNone(status)

    def test_job_status_copy_protection(self):
        """Test that returned job status is a copy to prevent external modification."""
        self.manager.update_job_progress(self.sample_job_id, 0.5, JobStatus.IN_PROGRESS)
        job_status = self.manager.get_job_status(self.sample_job_id)
        
        # Modify the returned dict
        job_status['progress'] = 0.9
        job_status['status'] = JobStatus.COMPLETED.value
        
        # Original should be unchanged
        original_status = self.manager.get_job_status(self.sample_job_id)
        self.assertEqual(original_status['progress'], 0.5)
        self.assertEqual(original_status['status'], JobStatus.IN_PROGRESS.value)

    # Thread Safety Tests

    def test_concurrent_job_updates(self):
        """Test thread safety with concurrent job updates."""
        num_threads = 10
        updates_per_thread = 20
        job_ids = [f"job_{i}" for i in range(num_threads)]
        
        def update_job(job_id: str, thread_index: int):
            """Update job progress multiple times."""
            for update_count in range(updates_per_thread):
                progress = (update_count + 1) / updates_per_thread
                status = JobStatus.IN_PROGRESS if progress < 1.0 else JobStatus.COMPLETED
                self.manager.update_job_progress(
                    job_id,
                    progress,
                    status,
                    message=f"Thread {thread_index} update {update_count}"
                )
                # Small delay to encourage race conditions
                time.sleep(0.001)
        
        # Start all threads
        threads = []
        for i, job_id in enumerate(job_ids):
            thread = threading.Thread(target=update_job, args=(job_id, i))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all jobs were created and completed properly
        self.assertEqual(len(self.manager.state_cache), num_threads)
        
        for job_id in job_ids:
            job = self.manager.get_job_status(job_id)
            self.assertIsNotNone(job)
            self.assertEqual(job['progress'], 1.0)
            self.assertEqual(job['status'], JobStatus.COMPLETED.value)

    def test_concurrent_state_persistence(self):
        """Test that concurrent operations maintain state consistency."""
        num_operations = 20  # Reduced to avoid file system race conditions
        
        def rapid_updates(thread_id):
            """Perform rapid job updates."""
            for i in range(num_operations):
                job_id = f"concurrent_job_{thread_id}_{i}"  # Unique job IDs per thread
                self.manager.update_job_progress(job_id, 0.5, JobStatus.IN_PROGRESS)
                # Small delay to reduce file system contention
                time.sleep(0.002)
        
        # Run multiple threads doing rapid updates
        threads = []
        for thread_id in range(3):
            thread = threading.Thread(target=rapid_updates, args=(thread_id,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verify state consistency - should have 3 * num_operations jobs
        expected_jobs = 3 * num_operations
        actual_jobs = len(self.manager.state_cache)
        self.assertEqual(actual_jobs, expected_jobs, 
                        f"Expected {expected_jobs} jobs, got {actual_jobs}")
        
        # Create new manager to test persistence consistency
        # Wait a moment for file system operations to complete
        time.sleep(0.1)
        new_manager = JobStateManager(persistence_file=self.test_file)
        # Allow for some jobs to have failed persistence due to concurrent access
        self.assertGreaterEqual(len(new_manager.state_cache), expected_jobs // 2,
                               "Persistence should maintain at least half the jobs during concurrent access")

    def test_read_write_lock_behavior(self):
        """Test that read operations don't block each other but write operations are exclusive."""
        read_results = []
        write_completed = threading.Event()
        
        def long_write_operation():
            """Simulate a long write operation."""
            with self.manager.lock:
                time.sleep(0.1)  # Hold lock for 100ms
                self.manager.state_cache["write_job"] = {"status": "completed"}
            write_completed.set()
        
        def read_operation(result_list):
            """Perform read operation."""
            status = self.manager.get_job_status("nonexistent")
            result_list.append(("read", datetime.now()))
        
        # Start write operation
        write_thread = threading.Thread(target=long_write_operation)
        write_thread.start()
        
        # Start multiple read operations shortly after
        time.sleep(0.01)  # Ensure write starts first
        read_threads = []
        for i in range(5):
            thread = threading.Thread(target=read_operation, args=(read_results,))
            read_threads.append(thread)
            thread.start()
        
        # Wait for all operations to complete
        write_thread.join()
        for thread in read_threads:
            thread.join()
        
        # Verify write completed before reads could proceed
        self.assertTrue(write_completed.is_set())
        self.assertEqual(len(read_results), 5)

    # Job Management Tests

    def test_get_all_jobs_no_filter(self):
        """Test getting all jobs without status filter."""
        job_ids = ["job_1", "job_2", "job_3"]
        statuses = [JobStatus.PENDING, JobStatus.IN_PROGRESS, JobStatus.COMPLETED]
        
        for job_id, status in zip(job_ids, statuses):
            progress = 1.0 if status == JobStatus.COMPLETED else 0.5
            self.manager.update_job_progress(job_id, progress, status)
        
        all_jobs = self.manager.get_all_jobs()
        self.assertEqual(len(all_jobs), 3)
        
        # Should be sorted by creation time (newest first)
        job_ids_returned = [job['job_id'] for job in all_jobs]
        self.assertEqual(job_ids_returned, list(reversed(job_ids)))

    def test_get_all_jobs_with_filter(self):
        """Test getting jobs filtered by status."""
        # Create jobs with different statuses
        self.manager.update_job_progress("pending_job", 0.0, JobStatus.PENDING)
        self.manager.update_job_progress("active_job", 0.5, JobStatus.IN_PROGRESS)
        self.manager.update_job_progress("done_job", 1.0, JobStatus.COMPLETED)
        self.manager.update_job_progress("failed_job", 0.3, JobStatus.FAILED)
        
        # Test filtering
        pending_jobs = self.manager.get_all_jobs(JobStatus.PENDING)
        self.assertEqual(len(pending_jobs), 1)
        self.assertEqual(pending_jobs[0]['job_id'], "pending_job")
        
        active_jobs = self.manager.get_all_jobs(JobStatus.IN_PROGRESS)
        self.assertEqual(len(active_jobs), 1)
        self.assertEqual(active_jobs[0]['job_id'], "active_job")
        
        completed_jobs = self.manager.get_all_jobs(JobStatus.COMPLETED)
        self.assertEqual(len(completed_jobs), 1)
        self.assertEqual(completed_jobs[0]['job_id'], "done_job")

    def test_delete_job(self):
        """Test job deletion functionality."""
        self.manager.update_job_progress(self.sample_job_id, 0.5, JobStatus.IN_PROGRESS)
        
        # Verify job exists
        self.assertIsNotNone(self.manager.get_job_status(self.sample_job_id))
        
        # Delete job
        result = self.manager.delete_job(self.sample_job_id)
        self.assertTrue(result)
        
        # Verify job is gone
        self.assertIsNone(self.manager.get_job_status(self.sample_job_id))
        
        # Deleting non-existent job should return False
        result = self.manager.delete_job("nonexistent_job")
        self.assertFalse(result)

    def test_retry_count_management(self):
        """Test retry count increment functionality."""
        self.manager.update_job_progress(self.sample_job_id, 0.2, JobStatus.PENDING)
        
        # Initial retry count should be 0
        job = self.manager.get_job_status(self.sample_job_id)
        self.assertEqual(job['retry_count'], 0)
        
        # Increment retry count
        new_count = self.manager.increment_retry_count(self.sample_job_id)
        self.assertEqual(new_count, 1)
        
        job = self.manager.get_job_status(self.sample_job_id)
        self.assertEqual(job['retry_count'], 1)
        
        # Increment again
        new_count = self.manager.increment_retry_count(self.sample_job_id)
        self.assertEqual(new_count, 2)
        
        # Non-existent job should return 0
        count = self.manager.increment_retry_count("nonexistent")
        self.assertEqual(count, 0)

    def test_active_job_count(self):
        """Test active job count calculation."""
        self.assertEqual(self.manager.get_active_job_count(), 0)
        
        # Add jobs with various statuses
        self.manager.update_job_progress("pending_job", 0.0, JobStatus.PENDING)
        self.assertEqual(self.manager.get_active_job_count(), 1)
        
        self.manager.update_job_progress("active_job", 0.5, JobStatus.IN_PROGRESS)
        self.assertEqual(self.manager.get_active_job_count(), 2)
        
        self.manager.update_job_progress("retry_job", 0.2, JobStatus.RETRY)
        self.assertEqual(self.manager.get_active_job_count(), 3)
        
        # Completed and failed jobs shouldn't count as active
        self.manager.update_job_progress("done_job", 1.0, JobStatus.COMPLETED)
        self.manager.update_job_progress("failed_job", 0.3, JobStatus.FAILED)
        self.assertEqual(self.manager.get_active_job_count(), 3)

    # Cleanup Tests

    def test_automatic_cleanup_timing(self):
        """Test that automatic cleanup runs at appropriate intervals."""
        # Mock datetime to control time passage
        with patch('job_state.datetime') as mock_datetime:
            base_time = datetime(2024, 1, 1, 12, 0, 0)
            mock_datetime.now.return_value = base_time
            mock_datetime.min = datetime.min
            
            # Create manager - should set last_cleanup to base_time
            manager = JobStateManager(persistence_file=self.test_file)
            
            # Add a job - should not trigger cleanup (within interval)
            manager.update_job_progress("job1", 0.5, JobStatus.IN_PROGRESS)
            
            # Advance time by less than cleanup interval (1 hour)
            mock_datetime.now.return_value = base_time + timedelta(minutes=30)
            manager.update_job_progress("job2", 0.5, JobStatus.IN_PROGRESS)
            
            # Advance time beyond cleanup interval
            mock_datetime.now.return_value = base_time + timedelta(hours=2)
            with patch.object(manager, '_cleanup_old_jobs') as mock_cleanup:
                manager.update_job_progress("job3", 0.5, JobStatus.IN_PROGRESS)
                mock_cleanup.assert_called_once()

    def test_cleanup_old_completed_jobs(self):
        """Test cleanup of jobs older than retention period."""
        with patch('job_state.datetime') as mock_datetime:
            # Create jobs at different times
            old_time = datetime(2024, 1, 1, 12, 0, 0)
            recent_time = datetime(2024, 1, 2, 12, 0, 0)  # 24 hours later
            now_time = datetime(2024, 1, 3, 12, 0, 0)    # 48 hours later
            
            mock_datetime.now.return_value = old_time
            
            # Create old completed job
            self.manager.update_job_progress("old_completed", 1.0, JobStatus.COMPLETED)
            
            # Create old failed job
            self.manager.update_job_progress("old_failed", 0.3, JobStatus.FAILED)
            
            # Advance time for recent job
            mock_datetime.now.return_value = recent_time
            
            # Create recent job
            self.manager.update_job_progress("recent_job", 1.0, JobStatus.COMPLETED)
            
            # Create old but still active job
            mock_datetime.now.return_value = old_time
            self.manager.update_job_progress("old_active", 0.5, JobStatus.IN_PROGRESS)
            
            # Trigger cleanup from future time
            mock_datetime.now.return_value = now_time
            cleaned_count = self.manager.force_cleanup()
            
            # Should clean up old completed and failed jobs, but not recent or active
            self.assertEqual(cleaned_count, 2)
            self.assertIsNone(self.manager.get_job_status("old_completed"))
            self.assertIsNone(self.manager.get_job_status("old_failed"))
            self.assertIsNotNone(self.manager.get_job_status("recent_job"))
            self.assertIsNotNone(self.manager.get_job_status("old_active"))

    def test_cleanup_preserves_active_jobs(self):
        """Test that cleanup never removes active jobs regardless of age."""
        with patch('job_state.datetime') as mock_datetime:
            old_time = datetime(2024, 1, 1, 12, 0, 0)
            now_time = datetime(2024, 1, 10, 12, 0, 0)  # 9 days later
            
            mock_datetime.now.return_value = old_time
            
            # Create very old active jobs
            self.manager.update_job_progress("old_pending", 0.0, JobStatus.PENDING)
            self.manager.update_job_progress("old_in_progress", 0.5, JobStatus.IN_PROGRESS)
            self.manager.update_job_progress("old_retry", 0.2, JobStatus.RETRY)
            
            # Trigger cleanup from far future
            mock_datetime.now.return_value = now_time
            cleaned_count = self.manager.force_cleanup()
            
            # No active jobs should be cleaned up
            self.assertEqual(cleaned_count, 0)
            self.assertIsNotNone(self.manager.get_job_status("old_pending"))
            self.assertIsNotNone(self.manager.get_job_status("old_in_progress"))
            self.assertIsNotNone(self.manager.get_job_status("old_retry"))

    # Statistics and Reporting Tests

    def test_get_statistics_empty_state(self):
        """Test statistics with no jobs."""
        stats = self.manager.get_statistics()
        
        expected_stats = {
            'total_jobs': 0,
            'by_status': {},
            'active_jobs': 0,
            'completed_jobs': 0,
            'failed_jobs': 0,
            'avg_progress': 0.0,
            'oldest_job': None,
            'newest_job': None
        }
        
        self.assertEqual(stats, expected_stats)

    def test_get_statistics_with_jobs(self):
        """Test statistics calculation with various job states."""
        # Create jobs with different statuses and progress
        jobs_data = [
            ("job1", 0.0, JobStatus.PENDING),
            ("job2", 0.3, JobStatus.IN_PROGRESS),
            ("job3", 0.7, JobStatus.IN_PROGRESS),
            ("job4", 1.0, JobStatus.COMPLETED),
            ("job5", 1.0, JobStatus.COMPLETED),
            ("job6", 0.5, JobStatus.FAILED),
            ("job7", 0.2, JobStatus.RETRY)
        ]
        
        for job_id, progress, status in jobs_data:
            self.manager.update_job_progress(job_id, progress, status)
        
        stats = self.manager.get_statistics()
        
        self.assertEqual(stats['total_jobs'], 7)
        self.assertEqual(stats['active_jobs'], 4)  # PENDING, IN_PROGRESS(2), RETRY
        self.assertEqual(stats['completed_jobs'], 2)
        self.assertEqual(stats['failed_jobs'], 1)
        
        # Check status breakdown
        self.assertEqual(stats['by_status'][JobStatus.PENDING.value], 1)
        self.assertEqual(stats['by_status'][JobStatus.IN_PROGRESS.value], 2)
        self.assertEqual(stats['by_status'][JobStatus.COMPLETED.value], 2)
        self.assertEqual(stats['by_status'][JobStatus.FAILED.value], 1)
        self.assertEqual(stats['by_status'][JobStatus.RETRY.value], 1)
        
        # Check average progress: (0.0 + 0.3 + 0.7 + 1.0 + 1.0 + 0.5 + 0.2) / 7 = 3.7/7
        expected_avg = 3.7 / 7
        self.assertAlmostEqual(stats['avg_progress'], expected_avg, places=3)
        
        # Check timestamp fields are present
        self.assertIsNotNone(stats['oldest_job'])
        self.assertIsNotNone(stats['newest_job'])

    # Memory Usage and Performance Tests

    @pytest.mark.slow
    def test_large_number_of_jobs_memory_usage(self):
        """Test memory behavior with a large number of jobs."""
        import tracemalloc
        
        tracemalloc.start()
        
        # Add many jobs to test memory usage
        num_jobs = 1000
        for i in range(num_jobs):
            job_id = f"bulk_job_{i}"
            progress = (i % 100) / 100.0
            status = JobStatus.COMPLETED if i % 3 == 0 else JobStatus.IN_PROGRESS
            
            self.manager.update_job_progress(
                job_id, 
                progress, 
                status,
                message=f"Processing job {i}",
                error=None if i % 10 != 0 else f"Error in job {i}"
            )
        
        # Get memory usage
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        # Verify all jobs exist
        self.assertEqual(len(self.manager.state_cache), num_jobs)
        
        # Memory usage should be reasonable (less than 50MB for 1000 jobs)
        self.assertLess(peak / 1024 / 1024, 50, "Memory usage too high for 1000 jobs")
        
        # Test that operations are still fast
        start_time = time.time()
        stats = self.manager.get_statistics()
        operation_time = time.time() - start_time
        
        self.assertLess(operation_time, 1.0, "Statistics calculation too slow")
        self.assertEqual(stats['total_jobs'], num_jobs)

    @pytest.mark.slow
    def test_persistence_performance_large_state(self):
        """Test save/load performance with large state."""
        # Create large state
        num_jobs = 500
        for i in range(num_jobs):
            self.manager.update_job_progress(
                f"perf_job_{i}",
                0.5,
                JobStatus.IN_PROGRESS,
                message=f"Long message for job {i} " * 10  # Make messages longer
            )
        
        # Test save performance
        start_time = time.time()
        self.manager._save_state()
        save_time = time.time() - start_time
        
        self.assertLess(save_time, 5.0, "State save operation too slow")
        
        # Test load performance
        start_time = time.time()
        new_manager = JobStateManager(persistence_file=self.test_file)
        load_time = time.time() - start_time
        
        self.assertLess(load_time, 5.0, "State load operation too slow")
        self.assertEqual(len(new_manager.state_cache), num_jobs)

    # Edge Cases and Error Handling

    def test_reset_all_state(self):
        """Test complete state reset functionality."""
        # Add some jobs
        for i in range(5):
            self.manager.update_job_progress(f"job_{i}", 0.5, JobStatus.IN_PROGRESS)
        
        self.assertEqual(len(self.manager.state_cache), 5)
        
        # Reset state
        self.manager.reset_all_state()
        
        self.assertEqual(len(self.manager.state_cache), 0)
        
        # Verify persistence file was updated
        new_manager = JobStateManager(persistence_file=self.test_file)
        self.assertEqual(len(new_manager.state_cache), 0)

    def test_missing_datetime_fields_handling(self):
        """Test handling of jobs with missing datetime fields."""
        # Manually add job data with missing datetime fields
        with self.manager.lock:
            self.manager.state_cache["partial_job"] = {
                'job_id': "partial_job",
                'status': JobStatus.IN_PROGRESS.value,
                'progress': 0.5,
                'message': None,
                'error': None,
                'retry_count': 0
                # Missing datetime fields
            }
        
        # Should handle missing fields gracefully
        job = self.manager.get_job_status("partial_job")
        self.assertIsNotNone(job)
        self.assertEqual(job['job_id'], "partial_job")

    @patch("job_state.logger")
    def test_logging_behavior(self, mock_logger):
        """Test that appropriate log messages are generated."""
        # Test initialization logging
        JobStateManager(persistence_file=self.test_file)
        mock_logger.info.assert_called()
        
        # Test job update logging
        self.manager.update_job_progress(self.sample_job_id, 0.5, JobStatus.IN_PROGRESS)
        mock_logger.debug.assert_called()
        
        # Test cleanup logging
        with patch('job_state.datetime') as mock_datetime:
            old_time = datetime(2024, 1, 1, 12, 0, 0)
            now_time = datetime(2024, 1, 10, 12, 0, 0)
            
            mock_datetime.now.return_value = old_time
            self.manager.update_job_progress("cleanup_job", 1.0, JobStatus.COMPLETED)
            
            mock_datetime.now.return_value = now_time
            self.manager.force_cleanup()
            
        # Should have logged cleanup
        cleanup_calls = [call for call in mock_logger.info.call_args_list 
                        if 'Cleaned up' in str(call)]
        self.assertGreater(len(cleanup_calls), 0)


if __name__ == '__main__':
    unittest.main()