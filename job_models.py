"""
Job Models Module

Defines data models and enums for the async worker system.
Contains job status tracking, priority levels, and job data structures.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class JobStatus(Enum):
    """Job processing status"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"


class JobPriority(Enum):
    """Job priority levels - lower numbers = higher priority"""

    HIGH = 1  # Single videos
    MEDIUM = 2  # Small playlists (2-10 videos)
    LOW = 3  # Large playlists (>10 videos)


class JobType(Enum):
    """Types of processing jobs"""

    VIDEO = "video"
    PLAYLIST = "playlist"
    BATCH = "batch"


@dataclass
class ProcessingJob:
    """
    Represents a job to be processed by the worker system.

    Contains all necessary information to process a YouTube video or playlist
    including priority, status tracking, and retry information.
    """

    job_id: str
    job_type: JobType
    priority: JobPriority
    data: Dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0
    current_step: str = ""
    total_steps: int = 1
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    worker_id: Optional[str] = None
    client_id: Optional[str] = None
    session_id: Optional[str] = None

    def __post_init__(self):
        """Initialize job with default values if not provided"""
        if not self.job_id:
            self.job_id = str(uuid.uuid4())

        # Set total steps based on job type
        if self.job_type == JobType.VIDEO:
            self.total_steps = 3  # Get transcript, generate summary, cache result
        elif self.job_type == JobType.PLAYLIST:
            video_count = len(self.data.get("video_ids", []))
            self.total_steps = (
                video_count + 2
            )  # Process each video + get playlist info + finalize
        else:  # BATCH
            self.total_steps = len(self.data.get("urls", []))

    def update_progress(self, progress: float, step: str = "", increment: bool = False):
        """
        Update job progress.

        Args:
            progress: Progress as float between 0.0 and 1.0
            step: Description of current step
            increment: If True, increment step counter
        """
        if increment and progress > self.progress:
            # Calculate which step we're on based on progress
            current_step_num = int(progress * self.total_steps) + 1
            self.current_step = step or f"Step {current_step_num} of {self.total_steps}"
        else:
            self.current_step = step or self.current_step

        self.progress = max(0.0, min(1.0, progress))

    def start_processing(self, worker_id: str):
        """Mark job as started with worker assignment"""
        self.status = JobStatus.IN_PROGRESS
        self.started_at = datetime.now(timezone.utc)
        self.worker_id = worker_id
        self.update_progress(0.0, "Starting processing...")

    def complete_successfully(self, result: Dict[str, Any]):
        """Mark job as completed successfully"""
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.result = result
        self.update_progress(1.0, "Completed")

    def fail_with_error(self, error_message: str, can_retry: bool = True):
        """Mark job as failed with error message"""
        self.error_message = error_message

        if can_retry and self.retry_count < self.max_retries:
            self.status = JobStatus.RETRY
            self.retry_count += 1
            self.current_step = (
                f"Retrying (attempt {self.retry_count + 1}/{self.max_retries + 1})"
            )
        else:
            self.status = JobStatus.FAILED
            self.completed_at = datetime.now(timezone.utc)

    def reset_for_retry(self):
        """Reset job state for retry"""
        if self.status == JobStatus.RETRY:
            self.status = JobStatus.PENDING
            self.started_at = None
            self.worker_id = None
            self.progress = 0.0
            self.current_step = "Waiting for retry..."

    def get_processing_time(self) -> Optional[float]:
        """Get processing time in seconds if job is completed"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def get_wait_time(self) -> float:
        """Get time spent waiting in queue in seconds"""
        start_time = self.started_at or datetime.now(timezone.utc)
        return (start_time - self.created_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for JSON serialization"""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "progress": self.progress,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "result": self.result,
            "worker_id": self.worker_id,
            "client_id": self.client_id,
            "session_id": self.session_id,
            "processing_time": self.get_processing_time(),
            "wait_time": self.get_wait_time(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcessingJob":
        """Create ProcessingJob from dictionary"""
        # Parse datetime fields
        created_at = (
            datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            if data.get("created_at")
            else None
        )
        started_at = (
            datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))
            if data.get("started_at")
            else None
        )
        completed_at = (
            datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
            if data.get("completed_at")
            else None
        )

        return cls(
            job_id=data["job_id"],
            job_type=JobType(data["job_type"]),
            priority=JobPriority(data["priority"]),
            data=data["data"],
            status=JobStatus(data["status"]),
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            progress=data.get("progress", 0.0),
            current_step=data.get("current_step", ""),
            total_steps=data.get("total_steps", 1),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            error_message=data.get("error_message"),
            result=data.get("result"),
            worker_id=data.get("worker_id"),
            client_id=data.get("client_id"),
            session_id=data.get("session_id"),
        )


@dataclass
class JobResult:
    """Result of a completed job"""

    job_id: str
    job_type: JobType
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "processing_time": self.processing_time,
        }


class WorkerMetrics:
    """Tracks worker performance metrics"""

    def __init__(self):
        self.jobs_processed: int = 0
        self.jobs_failed: int = 0
        self.total_processing_time: float = 0.0
        self.created_at: datetime = datetime.now(timezone.utc)
        self.last_job_at: Optional[datetime] = None

    def record_job_completion(self, processing_time: float, success: bool):
        """Record completion of a job"""
        self.jobs_processed += 1
        if not success:
            self.jobs_failed += 1
        self.total_processing_time += processing_time
        self.last_job_at = datetime.now(timezone.utc)

    def get_success_rate(self) -> float:
        """Get success rate as percentage"""
        if self.jobs_processed == 0:
            return 0.0
        return ((self.jobs_processed - self.jobs_failed) / self.jobs_processed) * 100

    def get_average_processing_time(self) -> float:
        """Get average processing time in seconds"""
        if self.jobs_processed == 0:
            return 0.0
        return self.total_processing_time / self.jobs_processed

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        return {
            "jobs_processed": self.jobs_processed,
            "jobs_failed": self.jobs_failed,
            "success_rate": self.get_success_rate(),
            "average_processing_time": self.get_average_processing_time(),
            "total_processing_time": self.total_processing_time,
            "created_at": self.created_at.isoformat(),
            "last_job_at": self.last_job_at.isoformat() if self.last_job_at else None,
        }


def create_video_job(
    url: str, model_key: str = None, client_id: str = None, session_id: str = None
) -> ProcessingJob:
    """
    Factory function to create a video processing job.

    Args:
        url: YouTube video URL
        model_key: AI model to use for summarization
        client_id: Client identifier for SSE notifications
        session_id: Session identifier for authentication

    Returns:
        ProcessingJob configured for video processing
    """
    job_data = {"url": url, "model_key": model_key, "type": "video"}

    return ProcessingJob(
        job_id=str(uuid.uuid4()),
        job_type=JobType.VIDEO,
        priority=JobPriority.HIGH,
        data=job_data,
        client_id=client_id,
        session_id=session_id,
    )


def create_playlist_job(
    url: str,
    video_ids: List[str],
    model_key: str = None,
    client_id: str = None,
    session_id: str = None,
) -> ProcessingJob:
    """
    Factory function to create a playlist processing job.

    Args:
        url: YouTube playlist URL
        video_ids: List of video IDs in the playlist
        model_key: AI model to use for summarization
        client_id: Client identifier for SSE notifications
        session_id: Session identifier for authentication

    Returns:
        ProcessingJob configured for playlist processing
    """
    job_data = {
        "url": url,
        "video_ids": video_ids,
        "model_key": model_key,
        "type": "playlist",
    }

    # Determine priority based on playlist size
    priority = JobPriority.MEDIUM if len(video_ids) <= 10 else JobPriority.LOW

    return ProcessingJob(
        job_id=str(uuid.uuid4()),
        job_type=JobType.PLAYLIST,
        priority=priority,
        data=job_data,
        client_id=client_id,
        session_id=session_id,
    )


def create_batch_job(
    urls: List[str],
    model_key: str = None,
    client_id: str = None,
    session_id: str = None,
) -> ProcessingJob:
    """
    Factory function to create a batch processing job.

    Args:
        urls: List of YouTube URLs to process
        model_key: AI model to use for summarization
        client_id: Client identifier for SSE notifications
        session_id: Session identifier for authentication

    Returns:
        ProcessingJob configured for batch processing
    """
    job_data = {"urls": urls, "model_key": model_key, "type": "batch"}

    # Determine priority based on batch size
    if len(urls) == 1:
        priority = JobPriority.HIGH
    elif len(urls) <= 10:
        priority = JobPriority.MEDIUM
    else:
        priority = JobPriority.LOW

    return ProcessingJob(
        job_id=str(uuid.uuid4()),
        job_type=JobType.BATCH,
        priority=priority,
        data=job_data,
        client_id=client_id,
        session_id=session_id,
    )
