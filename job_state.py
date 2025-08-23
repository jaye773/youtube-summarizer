"""
Job State Management & Persistence for YouTube Summarizer Async Worker

This module provides thread-safe job state tracking and persistence capabilities
for the async worker system. It manages job progress, status updates, and
maintains state across application restarts.

Key Features:
- Thread-safe state management with RLock
- JSON-based persistence to disk
- Automatic cleanup of old jobs (24-hour retention)
- Progress tracking (0.0 to 1.0)
- Comprehensive error handling and logging
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import asdict

# Import job models once Module 1 is created
try:
    from job_models import JobStatus, JobPriority, ProcessingJob
except ImportError:
    # Fallback definitions for standalone testing
    from enum import Enum
    from dataclasses import dataclass

    class JobStatus(Enum):
        PENDING = "pending"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        FAILED = "failed"
        RETRY = "retry"

    class JobPriority(Enum):
        HIGH = 1
        MEDIUM = 2
        LOW = 3

    @dataclass
    class ProcessingJob:
        job_id: str
        job_type: str
        priority: JobPriority
        data: Dict[str, Any]
        status: JobStatus = JobStatus.PENDING
        created_at: datetime = None

logger = logging.getLogger(__name__)


class JobStateManager:
    """
    Thread-safe job state management with disk persistence.

    Manages job state, progress tracking, and automatic cleanup of old jobs.
    All operations are thread-safe using RLock for concurrent access.
    """

    def __init__(self, persistence_file: str = "data/job_state.json"):
        """
        Initialize the Job State Manager.

        Args:
            persistence_file: Path to JSON file for state persistence
        """
        self.persistence_file = persistence_file
        self.state_cache: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        self._last_cleanup = datetime.now()
        self._cleanup_interval = timedelta(hours=1)  # Cleanup every hour
        self._job_retention = timedelta(hours=24)    # Keep jobs for 24 hours

        # Ensure data directory exists
        os.makedirs(os.path.dirname(persistence_file), exist_ok=True)

        # Load existing state from disk
        self._load_state()

        logger.info(f"JobStateManager initialized with {len(self.state_cache)} cached jobs")

    def _load_state(self) -> None:
        """Load job state from persistence file."""
        try:
            if os.path.exists(self.persistence_file):
                with open(self.persistence_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Convert datetime strings back to datetime objects
                for job_id, job_data in data.items():
                    if 'created_at' in job_data and job_data['created_at']:
                        job_data['created_at'] = datetime.fromisoformat(job_data['created_at'])
                    if 'updated_at' in job_data and job_data['updated_at']:
                        job_data['updated_at'] = datetime.fromisoformat(job_data['updated_at'])
                    if 'completed_at' in job_data and job_data['completed_at']:
                        job_data['completed_at'] = datetime.fromisoformat(job_data['completed_at'])

                self.state_cache = data
                logger.info(f"Loaded {len(self.state_cache)} jobs from {self.persistence_file}")
            else:
                logger.info(f"No existing state file found at {self.persistence_file}")
        except Exception as e:
            logger.error(f"Error loading state from {self.persistence_file}: {e}")
            self.state_cache = {}

    def _save_state(self) -> None:
        """Save current state to persistence file."""
        try:
            # Create a copy for serialization with datetime conversion
            serializable_state = {}
            for job_id, job_data in self.state_cache.items():
                job_copy = job_data.copy()

                # Convert datetime objects to ISO strings
                for date_field in ['created_at', 'updated_at', 'completed_at']:
                    if date_field in job_copy and isinstance(job_copy[date_field], datetime):
                        job_copy[date_field] = job_copy[date_field].isoformat()

                serializable_state[job_id] = job_copy

            # Write to temporary file first, then rename for atomicity
            temp_file = f"{self.persistence_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_state, f, indent=2, ensure_ascii=False)

            # Atomic rename
            os.replace(temp_file, self.persistence_file)
            logger.debug(f"State saved to {self.persistence_file}")

        except Exception as e:
            logger.error(f"Error saving state to {self.persistence_file}: {e}")

    def update_job_progress(
        self,
        job_id: str,
        progress: float,
        status: Optional[JobStatus] = None,
        message: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Update job progress and status in a thread-safe manner.

        Args:
            job_id: Unique job identifier
            progress: Progress value between 0.0 and 1.0
            status: Optional new job status
            message: Optional progress message
            error: Optional error message
        """
        if not (0.0 <= progress <= 1.0):
            raise ValueError(f"Progress must be between 0.0 and 1.0, got {progress}")

        with self.lock:
            # Initialize job state if it doesn't exist
            if job_id not in self.state_cache:
                self.state_cache[job_id] = {
                    'job_id': job_id,
                    'status': JobStatus.PENDING.value,
                    'progress': 0.0,
                    'created_at': datetime.now(),
                    'updated_at': datetime.now(),
                    'message': None,
                    'error': None,
                    'retry_count': 0
                }

            # Update job state
            job_data = self.state_cache[job_id]
            job_data['progress'] = progress
            job_data['updated_at'] = datetime.now()

            if status:
                job_data['status'] = status.value

            if message:
                job_data['message'] = message

            if error:
                job_data['error'] = error

            # Mark completion time
            if status == JobStatus.COMPLETED or status == JobStatus.FAILED:
                job_data['completed_at'] = datetime.now()

            logger.debug(f"Updated job {job_id}: progress={progress}, status={status}")

        # Save state to disk (outside the lock to avoid holding it too long)
        self._save_state()

        # Trigger cleanup if it's time
        self._cleanup_if_needed()

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current job status and progress.

        Args:
            job_id: Unique job identifier

        Returns:
            Dictionary with job status information or None if not found
        """
        with self.lock:
            job_data = self.state_cache.get(job_id)
            if job_data:
                # Return a copy to prevent external modification
                return job_data.copy()
            return None

    def get_all_jobs(self, status_filter: Optional[JobStatus] = None) -> List[Dict[str, Any]]:
        """
        Get all jobs, optionally filtered by status.

        Args:
            status_filter: Optional status to filter by

        Returns:
            List of job status dictionaries
        """
        with self.lock:
            jobs = []
            for job_data in self.state_cache.values():
                if status_filter is None or job_data['status'] == status_filter.value:
                    jobs.append(job_data.copy())

            # Sort by creation time (newest first)
            jobs.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
            return jobs

    def delete_job(self, job_id: str) -> bool:
        """
        Delete a job from state management.

        Args:
            job_id: Unique job identifier

        Returns:
            True if job was deleted, False if not found
        """
        with self.lock:
            if job_id in self.state_cache:
                del self.state_cache[job_id]
                logger.info(f"Deleted job {job_id}")
                self._save_state()
                return True
            return False

    def increment_retry_count(self, job_id: str) -> int:
        """
        Increment retry count for a job.

        Args:
            job_id: Unique job identifier

        Returns:
            New retry count
        """
        with self.lock:
            if job_id in self.state_cache:
                self.state_cache[job_id]['retry_count'] = self.state_cache[job_id].get('retry_count', 0) + 1
                self.state_cache[job_id]['updated_at'] = datetime.now()
                retry_count = self.state_cache[job_id]['retry_count']
                logger.debug(f"Incremented retry count for job {job_id} to {retry_count}")
                self._save_state()
                return retry_count
            return 0

    def get_active_job_count(self) -> int:
        """
        Get count of active jobs (pending or in progress).

        Returns:
            Number of active jobs
        """
        with self.lock:
            active_statuses = {JobStatus.PENDING.value, JobStatus.IN_PROGRESS.value, JobStatus.RETRY.value}
            return sum(1 for job_data in self.state_cache.values()
                      if job_data['status'] in active_statuses)

    def _cleanup_if_needed(self) -> None:
        """Trigger cleanup if enough time has passed."""
        now = datetime.now()
        if now - self._last_cleanup >= self._cleanup_interval:
            self._cleanup_old_jobs()
            self._last_cleanup = now

    def _cleanup_old_jobs(self) -> None:
        """Remove jobs older than retention period."""
        cutoff_time = datetime.now() - self._job_retention
        jobs_to_remove = []

        with self.lock:
            for job_id, job_data in self.state_cache.items():
                # Check completion time first, then creation time
                check_time = job_data.get('completed_at') or job_data.get('created_at')
                if check_time and check_time < cutoff_time:
                    # Only cleanup completed or failed jobs
                    status = job_data.get('status')
                    if status in [JobStatus.COMPLETED.value, JobStatus.FAILED.value]:
                        jobs_to_remove.append(job_id)

            # Remove old jobs
            for job_id in jobs_to_remove:
                del self.state_cache[job_id]
                logger.debug(f"Cleaned up old job {job_id}")

        if jobs_to_remove:
            logger.info(f"Cleaned up {len(jobs_to_remove)} old jobs")
            self._save_state()

    def force_cleanup(self) -> int:
        """
        Force cleanup of old jobs immediately.

        Returns:
            Number of jobs cleaned up
        """
        old_count = len(self.state_cache)
        self._cleanup_old_jobs()
        new_count = len(self.state_cache)
        return old_count - new_count

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get job state statistics.

        Returns:
            Dictionary with various statistics
        """
        with self.lock:
            stats = {
                'total_jobs': len(self.state_cache),
                'by_status': {},
                'active_jobs': 0,
                'completed_jobs': 0,
                'failed_jobs': 0,
                'avg_progress': 0.0,
                'oldest_job': None,
                'newest_job': None
            }

            if not self.state_cache:
                return stats

            # Count by status and calculate averages
            total_progress = 0.0
            creation_times = []

            for job_data in self.state_cache.values():
                status = job_data['status']
                stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

                if status in [JobStatus.PENDING.value, JobStatus.IN_PROGRESS.value, JobStatus.RETRY.value]:
                    stats['active_jobs'] += 1
                elif status == JobStatus.COMPLETED.value:
                    stats['completed_jobs'] += 1
                elif status == JobStatus.FAILED.value:
                    stats['failed_jobs'] += 1

                total_progress += job_data.get('progress', 0.0)

                if 'created_at' in job_data and job_data['created_at']:
                    creation_times.append(job_data['created_at'])

            stats['avg_progress'] = total_progress / len(self.state_cache)

            if creation_times:
                stats['oldest_job'] = min(creation_times).isoformat()
                stats['newest_job'] = max(creation_times).isoformat()

            return stats

    def reset_all_state(self) -> None:
        """Reset all job state (for testing or emergency recovery)."""
        with self.lock:
            logger.warning("Resetting all job state")
            self.state_cache.clear()
            self._save_state()
