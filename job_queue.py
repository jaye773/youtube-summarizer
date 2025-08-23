"""
Job Queue Module

Implements priority-based job queue management for the async worker system.
Handles job scheduling, priority ordering, and thread-safe operations.
"""

import heapq
import threading
import time
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Callable, Set

from job_models import ProcessingJob, JobStatus, JobPriority, JobType, WorkerMetrics


# Configure logging
logger = logging.getLogger(__name__)


class PriorityJobQueue:
    """
    Thread-safe priority queue for processing jobs.
    
    Uses heapq for efficient priority ordering with FIFO for same priority levels.
    Supports job filtering, statistics, and monitoring capabilities.
    """
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize the priority job queue.
        
        Args:
            max_size: Maximum number of jobs that can be queued
        """
        self.max_size = max_size
        self._queue: List[tuple] = []  # (priority, timestamp, job)
        self._job_dict: Dict[str, ProcessingJob] = {}  # job_id -> job mapping
        self._counter = 0  # For consistent ordering of same priority jobs
        self._lock = threading.RLock()  # Reentrant lock for nested operations
        
        # Statistics tracking
        self._stats = {
            'jobs_queued': 0,
            'jobs_processed': 0,
            'jobs_failed': 0,
            'queue_created_at': datetime.now(timezone.utc)
        }
        
        # Priority counters
        self._priority_counts = defaultdict(int)
        
        # Recent job history for monitoring
        self._recent_jobs: deque = deque(maxlen=100)
        
        logger.info(f"Initialized PriorityJobQueue with max_size={max_size}")
    
    def put(self, job: ProcessingJob, timeout: Optional[float] = None) -> bool:
        """
        Add a job to the queue.
        
        Args:
            job: ProcessingJob to add to queue
            timeout: Maximum time to wait if queue is full (not implemented)
            
        Returns:
            True if job was added successfully, False otherwise
        """
        with self._lock:
            # Check if queue is full
            if len(self._queue) >= self.max_size:
                logger.warning(f"Queue is full (max_size={self.max_size}), rejecting job {job.job_id}")
                return False
            
            # Check for duplicate job IDs
            if job.job_id in self._job_dict:
                logger.warning(f"Job {job.job_id} already exists in queue")
                return False
            
            # Add to heap queue with priority ordering
            # Use negative counter for FIFO ordering within same priority
            self._counter += 1
            priority_value = job.priority.value
            timestamp = time.time()
            
            # Heap entry: (priority, -counter, timestamp, job_id)
            # Lower priority values have higher priority (1 = HIGH, 2 = MEDIUM, 3 = LOW)
            heap_entry = (priority_value, -self._counter, timestamp, job.job_id)
            heapq.heappush(self._queue, heap_entry)
            
            # Store job in lookup dict
            self._job_dict[job.job_id] = job
            
            # Update statistics
            self._stats['jobs_queued'] += 1
            self._priority_counts[job.priority] += 1
            
            # Add to recent jobs history
            self._recent_jobs.append({
                'job_id': job.job_id,
                'job_type': job.job_type.value,
                'priority': job.priority.value,
                'queued_at': datetime.now(timezone.utc).isoformat(),
                'action': 'queued'
            })
            
            logger.info(f"Queued job {job.job_id} with priority {job.priority.name} "
                       f"(queue size: {len(self._queue)})")
            return True
    
    def get(self, timeout: Optional[float] = None) -> Optional[ProcessingJob]:
        """
        Get the highest priority job from the queue.
        
        Args:
            timeout: Maximum time to wait for a job (blocking operation)
            
        Returns:
            ProcessingJob with highest priority, or None if timeout
        """
        start_time = time.time()
        
        while True:
            with self._lock:
                if self._queue:
                    # Get highest priority job
                    priority_value, neg_counter, timestamp, job_id = heapq.heappop(self._queue)
                    
                    # Retrieve and remove from job dict
                    job = self._job_dict.pop(job_id, None)
                    if job is None:
                        # Job was removed externally, try next one
                        continue
                    
                    # Update priority counters
                    self._priority_counts[job.priority] -= 1
                    if self._priority_counts[job.priority] <= 0:
                        del self._priority_counts[job.priority]
                    
                    # Add to recent jobs history
                    self._recent_jobs.append({
                        'job_id': job.job_id,
                        'job_type': job.job_type.value,
                        'priority': job.priority.value,
                        'dequeued_at': datetime.now(timezone.utc).isoformat(),
                        'action': 'dequeued',
                        'wait_time': time.time() - timestamp
                    })
                    
                    logger.info(f"Dequeued job {job.job_id} with priority {job.priority.name} "
                               f"(queue size: {len(self._queue)})")
                    return job
            
            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    logger.debug("Queue get() timed out")
                    return None
                    
                # Brief sleep before checking again
                time.sleep(min(0.1, timeout - elapsed))
            else:
                # No timeout, brief sleep to prevent busy waiting
                time.sleep(0.01)
    
    def remove_job(self, job_id: str) -> bool:
        """
        Remove a specific job from the queue.
        
        Args:
            job_id: ID of job to remove
            
        Returns:
            True if job was removed, False if not found
        """
        with self._lock:
            if job_id not in self._job_dict:
                return False
            
            job = self._job_dict.pop(job_id)
            
            # Update priority counters
            self._priority_counts[job.priority] -= 1
            if self._priority_counts[job.priority] <= 0:
                del self._priority_counts[job.priority]
            
            # Mark queue entry as removed (it will be skipped during get())
            # We don't rebuild the heap for efficiency
            
            # Add to recent jobs history
            self._recent_jobs.append({
                'job_id': job_id,
                'job_type': job.job_type.value,
                'priority': job.priority.value,
                'removed_at': datetime.now(timezone.utc).isoformat(),
                'action': 'removed'
            })
            
            logger.info(f"Removed job {job_id} from queue")
            return True
    
    def get_job(self, job_id: str) -> Optional[ProcessingJob]:
        """
        Get a specific job by ID without removing it.
        
        Args:
            job_id: ID of job to retrieve
            
        Returns:
            ProcessingJob if found, None otherwise
        """
        with self._lock:
            return self._job_dict.get(job_id)
    
    def size(self) -> int:
        """Get current queue size"""
        with self._lock:
            return len(self._job_dict)  # More accurate than len(self._queue)
    
    def is_empty(self) -> bool:
        """Check if queue is empty"""
        with self._lock:
            return len(self._job_dict) == 0
    
    def is_full(self) -> bool:
        """Check if queue is at maximum capacity"""
        with self._lock:
            return len(self._job_dict) >= self.max_size
    
    def clear(self) -> int:
        """
        Clear all jobs from the queue.
        
        Returns:
            Number of jobs removed
        """
        with self._lock:
            job_count = len(self._job_dict)
            self._queue.clear()
            self._job_dict.clear()
            self._priority_counts.clear()
            
            logger.info(f"Cleared queue, removed {job_count} jobs")
            return job_count
    
    def get_jobs_by_status(self, status: JobStatus) -> List[ProcessingJob]:
        """
        Get all jobs with a specific status.
        
        Args:
            status: JobStatus to filter by
            
        Returns:
            List of jobs with the specified status
        """
        with self._lock:
            return [job for job in self._job_dict.values() if job.status == status]
    
    def get_jobs_by_priority(self, priority: JobPriority) -> List[ProcessingJob]:
        """
        Get all jobs with a specific priority.
        
        Args:
            priority: JobPriority to filter by
            
        Returns:
            List of jobs with the specified priority
        """
        with self._lock:
            return [job for job in self._job_dict.values() if job.priority == priority]
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics.
        
        Returns:
            Dictionary containing queue statistics
        """
        with self._lock:
            current_size = len(self._job_dict)
            priority_breakdown = dict(self._priority_counts)
            
            return {
                'current_size': current_size,
                'max_size': self.max_size,
                'is_full': current_size >= self.max_size,
                'priority_breakdown': {p.name: count for p, count in priority_breakdown.items()},
                'total_jobs_queued': self._stats['jobs_queued'],
                'total_jobs_processed': self._stats['jobs_processed'],
                'total_jobs_failed': self._stats['jobs_failed'],
                'queue_created_at': self._stats['queue_created_at'].isoformat(),
                'recent_activity': list(self._recent_jobs)[-10:]  # Last 10 activities
            }
    
    def get_waiting_time_estimate(self, priority: JobPriority) -> float:
        """
        Estimate waiting time for a job with given priority.
        
        Args:
            priority: Priority level of the job
            
        Returns:
            Estimated waiting time in seconds
        """
        with self._lock:
            # Count jobs with higher or equal priority
            jobs_ahead = 0
            for job in self._job_dict.values():
                if job.priority.value <= priority.value:  # Lower value = higher priority
                    jobs_ahead += 1
            
            # Rough estimate: 30 seconds per job (can be tuned based on metrics)
            estimated_time_per_job = 30.0
            return jobs_ahead * estimated_time_per_job
    
    def cleanup_old_entries(self):
        """
        Clean up orphaned entries in the heap queue.
        This rebuilds the heap to remove entries for jobs that were removed.
        """
        with self._lock:
            if not self._queue:
                return
            
            # Rebuild heap with only valid jobs
            valid_entries = []
            for priority_value, neg_counter, timestamp, job_id in self._queue:
                if job_id in self._job_dict:
                    valid_entries.append((priority_value, neg_counter, timestamp, job_id))
            
            self._queue = valid_entries
            heapq.heapify(self._queue)
            
            logger.debug(f"Cleaned up queue, {len(valid_entries)} valid entries remain")


class JobScheduler:
    """
    High-level job scheduler that manages job queuing and worker coordination.
    Provides additional features like job batching, rate limiting, and metrics.
    """
    
    def __init__(self, max_queue_size: int = 1000, 
                 rate_limit_per_minute: int = 60):
        """
        Initialize job scheduler.
        
        Args:
            max_queue_size: Maximum number of jobs in queue
            rate_limit_per_minute: Maximum jobs per minute per client
        """
        self.queue = PriorityJobQueue(max_queue_size)
        self.rate_limit_per_minute = rate_limit_per_minute
        
        # Rate limiting tracking
        self._client_requests: Dict[str, deque] = defaultdict(lambda: deque(maxlen=rate_limit_per_minute))
        self._rate_limit_lock = threading.Lock()
        
        # Job completion callbacks
        self._completion_callbacks: List[Callable[[ProcessingJob], None]] = []
        
        # Metrics
        self.metrics = WorkerMetrics()
        
        logger.info(f"Initialized JobScheduler with queue_size={max_queue_size}, "
                   f"rate_limit={rate_limit_per_minute}/min")
    
    def submit_job(self, job: ProcessingJob, client_ip: str = None) -> tuple[bool, str]:
        """
        Submit a job to the scheduler with rate limiting.
        
        Args:
            job: ProcessingJob to submit
            client_ip: Client IP address for rate limiting
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        # Check rate limiting
        if client_ip and not self._check_rate_limit(client_ip):
            return False, f"Rate limit exceeded: max {self.rate_limit_per_minute} requests per minute"
        
        # Submit to queue
        if self.queue.put(job):
            logger.info(f"Successfully submitted job {job.job_id}")
            return True, f"Job {job.job_id} queued successfully"
        else:
            return False, "Queue is full, please try again later"
    
    def get_next_job(self, timeout: Optional[float] = None) -> Optional[ProcessingJob]:
        """
        Get the next job to process.
        
        Args:
            timeout: Maximum time to wait for a job
            
        Returns:
            Next ProcessingJob to process or None
        """
        return self.queue.get(timeout=timeout)
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a pending job.
        
        Args:
            job_id: ID of job to cancel
            
        Returns:
            True if job was cancelled, False if not found or already processing
        """
        job = self.queue.get_job(job_id)
        if job and job.status == JobStatus.PENDING:
            if self.queue.remove_job(job_id):
                logger.info(f"Cancelled job {job_id}")
                return True
        
        logger.warning(f"Could not cancel job {job_id} - not found or already processing")
        return False
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status information for a job.
        
        Args:
            job_id: ID of job to check
            
        Returns:
            Job status dictionary or None if not found
        """
        job = self.queue.get_job(job_id)
        if job:
            return job.to_dict()
        return None
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get overall queue status and statistics.
        
        Returns:
            Dictionary with queue status information
        """
        stats = self.queue.get_stats()
        stats['scheduler_metrics'] = self.metrics.to_dict()
        stats['rate_limit_per_minute'] = self.rate_limit_per_minute
        return stats
    
    def add_completion_callback(self, callback: Callable[[ProcessingJob], None]):
        """
        Add a callback to be called when jobs complete.
        
        Args:
            callback: Function to call with completed job
        """
        self._completion_callbacks.append(callback)
    
    def _check_rate_limit(self, client_ip: str) -> bool:
        """
        Check if client is within rate limit.
        
        Args:
            client_ip: Client IP address
            
        Returns:
            True if within rate limit, False otherwise
        """
        with self._rate_limit_lock:
            now = datetime.now(timezone.utc)
            client_requests = self._client_requests[client_ip]
            
            # Remove requests older than 1 minute
            cutoff_time = now - timedelta(minutes=1)
            while client_requests and client_requests[0] < cutoff_time:
                client_requests.popleft()
            
            # Check if under limit
            if len(client_requests) >= self.rate_limit_per_minute:
                logger.warning(f"Rate limit exceeded for client {client_ip}")
                return False
            
            # Add current request
            client_requests.append(now)
            return True
    
    def cleanup_periodic(self):
        """
        Perform periodic cleanup operations.
        Should be called regularly by a maintenance thread.
        """
        # Clean up queue orphaned entries
        self.queue.cleanup_old_entries()
        
        # Clean up old rate limit entries
        with self._rate_limit_lock:
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=2)
            clients_to_clean = []
            
            for client_ip, requests in self._client_requests.items():
                while requests and requests[0] < cutoff_time:
                    requests.popleft()
                
                # Remove clients with no recent requests
                if not requests:
                    clients_to_clean.append(client_ip)
            
            for client_ip in clients_to_clean:
                del self._client_requests[client_ip]
        
        logger.debug("Completed periodic cleanup")