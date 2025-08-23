"""
Worker Manager Module

Main worker thread management for the async YouTube Summarizer system.
Coordinates worker threads, job processing, and result handling.
"""

import json
import logging
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Callable

from job_models import (
    ProcessingJob, JobStatus, JobType, JobResult, WorkerMetrics,
    create_video_job, create_playlist_job
)
from job_queue import JobScheduler

# Functions will be injected via app_context to avoid circular imports
clean_youtube_url = None
get_video_id = None
get_playlist_id = None
get_transcript = None
generate_summary = None
get_video_details = None
get_videos_from_playlist = None
load_summary_cache = None
save_summary_cache = None

# Configure logging
logger = logging.getLogger(__name__)


class WorkerThread:
    """
    Individual worker thread that processes jobs from the queue.
    Each worker runs in its own thread and handles job execution.
    """

    def __init__(self, worker_id: str, job_scheduler: JobScheduler,
                 notification_callback: Optional[Callable] = None):
        """
        Initialize worker thread.

        Args:
            worker_id: Unique identifier for this worker
            job_scheduler: JobScheduler instance to get jobs from
            notification_callback: Function to call for progress notifications
        """
        self.worker_id = worker_id
        self.job_scheduler = job_scheduler
        self.notification_callback = notification_callback

        # Thread management
        self.thread = None
        self.is_running = False
        self.should_stop = False

        # Worker metrics
        self.metrics = WorkerMetrics()
        self.current_job: Optional[ProcessingJob] = None

        # Cache reference
        self._summary_cache = {}
        self._cache_lock = threading.Lock()

        logger.info(f"Initialized worker {worker_id}")

    def start(self):
        """Start the worker thread"""
        if self.thread and self.thread.is_alive():
            logger.warning(f"Worker {self.worker_id} is already running")
            return

        self.should_stop = False
        self.thread = threading.Thread(target=self._run, name=f"Worker-{self.worker_id}")
        self.thread.daemon = True
        self.thread.start()
        self.is_running = True

        logger.info(f"Started worker {self.worker_id}")

    def stop(self, timeout: float = 10.0):
        """
        Stop the worker thread gracefully.

        Args:
            timeout: Maximum time to wait for worker to stop
        """
        if not self.is_running:
            return

        self.should_stop = True

        if self.thread:
            self.thread.join(timeout=timeout)
            if self.thread.is_alive():
                logger.warning(f"Worker {self.worker_id} did not stop within timeout")
            else:
                logger.info(f"Worker {self.worker_id} stopped successfully")

        self.is_running = False

    def _run(self):
        """Main worker thread loop"""
        logger.info(f"Worker {self.worker_id} started processing")

        # Load cache at start
        try:
            self._summary_cache = load_summary_cache()
            logger.debug(f"Worker {self.worker_id} loaded cache with {len(self._summary_cache)} entries")
        except Exception as e:
            logger.error(f"Worker {self.worker_id} failed to load cache: {e}")
            self._summary_cache = {}

        while not self.should_stop:
            try:
                # Get next job with timeout
                job = self.job_scheduler.get_next_job(timeout=1.0)

                if job is None:
                    continue  # Timeout, check should_stop and try again

                # Process the job
                self.current_job = job
                result = self._process_job(job)
                self.current_job = None

                # Record metrics
                processing_time = result.processing_time or 0.0
                self.metrics.record_job_completion(processing_time, result.success)

                # Notify completion if callback provided
                if self.notification_callback:
                    try:
                        self.notification_callback(job, result)
                    except Exception as e:
                        logger.error(f"Notification callback failed: {e}")

            except Exception as e:
                logger.error(f"Worker {self.worker_id} encountered error: {e}")
                logger.error(traceback.format_exc())

                # If we have a current job, mark it as failed
                if self.current_job:
                    self.current_job.fail_with_error(f"Worker error: {str(e)}", can_retry=True)
                    self.current_job = None

                # Brief sleep to prevent tight error loop
                time.sleep(1.0)

        logger.info(f"Worker {self.worker_id} finished processing")

    def _process_job(self, job: ProcessingJob) -> JobResult:
        """
        Process a single job.

        Args:
            job: ProcessingJob to process

        Returns:
            JobResult with processing outcome
        """
        start_time = time.time()
        job.start_processing(self.worker_id)

        try:
            # Send initial progress notification
            self._notify_progress(job, 0.0, "Starting processing...")

            if job.job_type == JobType.VIDEO:
                result_data = self._process_video_job(job)
            elif job.job_type == JobType.PLAYLIST:
                result_data = self._process_playlist_job(job)
            elif job.job_type == JobType.BATCH:
                result_data = self._process_batch_job(job)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")

            # Mark job as completed
            job.complete_successfully(result_data)
            processing_time = time.time() - start_time

            logger.info(f"Worker {self.worker_id} completed job {job.job_id} in {processing_time:.2f}s")

            return JobResult(
                job_id=job.job_id,
                job_type=job.job_type,
                success=True,
                data=result_data,
                processing_time=processing_time
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Worker {self.worker_id} failed to process job {job.job_id}: {error_msg}")
            logger.error(traceback.format_exc())

            # Mark job as failed
            job.fail_with_error(error_msg, can_retry=True)
            processing_time = time.time() - start_time

            return JobResult(
                job_id=job.job_id,
                job_type=job.job_type,
                success=False,
                error=error_msg,
                processing_time=processing_time
            )

    def _process_video_job(self, job: ProcessingJob) -> Dict[str, Any]:
        """
        Process a single video summarization job.

        Args:
            job: Video processing job

        Returns:
            Dictionary with video processing results
        """
        url = job.data.get('url', '')
        model_key = job.data.get('model_key')

        # Step 1: Extract video ID and clean URL
        self._notify_progress(job, 0.1, "Extracting video ID...")
        cleaned_url = clean_youtube_url(url)
        video_id = get_video_id(cleaned_url)

        if not video_id:
            raise ValueError("Could not extract video ID from URL")

        # Step 2: Check cache first
        self._notify_progress(job, 0.2, "Checking cache...")
        cache_key = f"{video_id}_{model_key or 'default'}"

        with self._cache_lock:
            if cache_key in self._summary_cache:
                cached_result = self._summary_cache[cache_key].copy()
                cached_result['cached'] = True
                cached_result['video_id'] = video_id
                self._notify_progress(job, 1.0, "Retrieved from cache")
                return cached_result

        # Step 3: Get video details
        self._notify_progress(job, 0.3, "Getting video details...")
        video_details = get_video_details([video_id])
        if not video_details or video_id not in video_details:
            raise ValueError("Could not fetch video details")

        title = video_details[video_id]['title']
        thumbnail_url = video_details[video_id].get('thumbnail_url')

        # Step 4: Get transcript
        self._notify_progress(job, 0.4, "Fetching transcript...")
        transcript, transcript_error = get_transcript(video_id)

        if not transcript:
            raise ValueError(transcript_error or "Could not fetch transcript")

        # Step 5: Generate summary
        self._notify_progress(job, 0.6, "Generating summary...")
        summary, summary_error = generate_summary(transcript, title, model_key)

        if not summary:
            raise ValueError(summary_error or "Could not generate summary")

        # Step 6: Cache and return result
        self._notify_progress(job, 0.9, "Caching result...")
        result = {
            'video_id': video_id,
            'title': title,
            'summary': summary,
            'thumbnail_url': thumbnail_url,
            'url': cleaned_url,
            'model_used': model_key,
            'cached': False,
            'processed_at': datetime.now(timezone.utc).isoformat()
        }

        # Cache the result
        with self._cache_lock:
            self._summary_cache[cache_key] = result.copy()
            try:
                save_summary_cache(self._summary_cache)
            except Exception as e:
                logger.warning(f"Failed to save cache: {e}")

        self._notify_progress(job, 1.0, "Completed successfully")
        return result

    def _process_playlist_job(self, job: ProcessingJob) -> Dict[str, Any]:
        """
        Process a playlist summarization job.

        Args:
            job: Playlist processing job

        Returns:
            Dictionary with playlist processing results
        """
        url = job.data.get('url', '')
        video_ids = job.data.get('video_ids', [])
        model_key = job.data.get('model_key')

        if not video_ids:
            # Extract playlist ID and get videos
            self._notify_progress(job, 0.05, "Extracting playlist info...")
            playlist_id = get_playlist_id(url)
            if not playlist_id:
                raise ValueError("Could not extract playlist ID from URL")

            video_items, error = get_videos_from_playlist(playlist_id)
            if error:
                raise ValueError(f"Could not fetch playlist videos: {error}")

            video_ids = [item['contentDetails']['videoId'] for item in video_items if 'contentDetails' in item]

        if not video_ids:
            raise ValueError("No videos found in playlist")

        # Process each video
        results = []
        total_videos = len(video_ids)

        for i, video_id in enumerate(video_ids):
            progress = (i / total_videos) * 0.9  # Reserve last 10% for finalization
            self._notify_progress(job, progress, f"Processing video {i+1} of {total_videos}...")

            try:
                # Create a temporary video job
                video_job_data = {
                    'url': f"https://www.youtube.com/watch?v={video_id}",
                    'model_key': model_key,
                    'type': 'video'
                }
                temp_job = ProcessingJob(
                    job_id=f"{job.job_id}_video_{i}",
                    job_type=JobType.VIDEO,
                    priority=job.priority,
                    data=video_job_data
                )

                # Process the video
                video_result = self._process_video_job(temp_job)
                results.append(video_result)

                # Add delay between videos to prevent rate limiting
                if i < total_videos - 1:  # Don't delay after the last video
                    time.sleep(1.0)

            except Exception as e:
                logger.warning(f"Failed to process video {video_id} in playlist: {e}")
                # Add error entry but continue processing
                results.append({
                    'video_id': video_id,
                    'title': f"Video {video_id}",
                    'error': str(e),
                    'cached': False
                })

        self._notify_progress(job, 1.0, "Playlist processing completed")

        return {
            'type': 'playlist',
            'total_videos': total_videos,
            'successful_videos': len([r for r in results if 'error' not in r]),
            'failed_videos': len([r for r in results if 'error' in r]),
            'results': results,
            'processed_at': datetime.now(timezone.utc).isoformat()
        }

    def _process_batch_job(self, job: ProcessingJob) -> Dict[str, Any]:
        """
        Process a batch job (multiple URLs).

        Args:
            job: Batch processing job

        Returns:
            Dictionary with batch processing results
        """
        urls = job.data.get('urls', [])
        model_key = job.data.get('model_key')

        if not urls:
            raise ValueError("No URLs provided for batch processing")

        results = []
        total_urls = len(urls)

        for i, url in enumerate(urls):
            progress = (i / total_urls) * 0.9
            self._notify_progress(job, progress, f"Processing URL {i+1} of {total_urls}...")

            try:
                # Determine if it's a video or playlist
                if get_playlist_id(url):
                    # It's a playlist
                    playlist_job_data = {
                        'url': url,
                        'video_ids': [],  # Will be extracted
                        'model_key': model_key,
                        'type': 'playlist'
                    }
                    temp_job = ProcessingJob(
                        job_id=f"{job.job_id}_playlist_{i}",
                        job_type=JobType.PLAYLIST,
                        priority=job.priority,
                        data=playlist_job_data
                    )
                    result = self._process_playlist_job(temp_job)
                else:
                    # It's a video
                    video_job_data = {
                        'url': url,
                        'model_key': model_key,
                        'type': 'video'
                    }
                    temp_job = ProcessingJob(
                        job_id=f"{job.job_id}_video_{i}",
                        job_type=JobType.VIDEO,
                        priority=job.priority,
                        data=video_job_data
                    )
                    result = self._process_video_job(temp_job)

                result['url'] = url
                results.append(result)

                # Add delay between URLs to prevent rate limiting
                if i < total_urls - 1:  # Don't delay after the last URL
                    time.sleep(1.0)

            except Exception as e:
                logger.warning(f"Failed to process URL {url} in batch: {e}")
                results.append({
                    'url': url,
                    'error': str(e),
                    'processed_at': datetime.now(timezone.utc).isoformat()
                })

        self._notify_progress(job, 1.0, "Batch processing completed")

        return {
            'type': 'batch',
            'total_urls': total_urls,
            'successful_urls': len([r for r in results if 'error' not in r]),
            'failed_urls': len([r for r in results if 'error' in r]),
            'results': results,
            'processed_at': datetime.now(timezone.utc).isoformat()
        }

    def _notify_progress(self, job: ProcessingJob, progress: float, message: str):
        """
        Send progress notification for a job.

        Args:
            job: Job being processed
            progress: Progress as float 0.0-1.0
            message: Progress message
        """
        job.update_progress(progress, message)

        if self.notification_callback:
            try:
                self.notification_callback(job, None, progress_update=True)
            except Exception as e:
                logger.error(f"Progress notification failed: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current worker status"""
        return {
            'worker_id': self.worker_id,
            'is_running': self.is_running,
            'current_job_id': self.current_job.job_id if self.current_job else None,
            'metrics': self.metrics.to_dict()
        }


class WorkerManager:
    """
    Main worker manager that coordinates multiple worker threads.
    Provides high-level interface for job submission and worker management.
    """

    def __init__(self, num_workers: int = 3, max_queue_size: int = 1000,
                 rate_limit_per_minute: int = 60):
        """
        Initialize the worker manager.

        Args:
            num_workers: Number of worker threads to create
            max_queue_size: Maximum size of job queue
            rate_limit_per_minute: Rate limit per client per minute
        """
        self.num_workers = num_workers
        self.job_scheduler = JobScheduler(max_queue_size, rate_limit_per_minute)
        self.workers: List[WorkerThread] = []
        self.is_running = False

        # Notification callbacks
        self._progress_callbacks: List[Callable] = []
        self._completion_callbacks: List[Callable] = []

        # Management thread for periodic tasks
        self._management_thread = None
        self._should_stop_management = False

        logger.info(f"Initialized WorkerManager with {num_workers} workers")

    def set_app_functions(self, app_context: Dict[str, Any]):
        """
        Set app context functions to avoid circular imports.

        Args:
            app_context: Dictionary containing all required functions and objects
        """
        global clean_youtube_url, get_video_id, get_playlist_id, get_transcript
        global generate_summary, get_video_details, get_videos_from_playlist
        global load_summary_cache, save_summary_cache

        # Extract functions from app context
        clean_youtube_url = lambda url: url  # Simple version
        get_video_id = app_context.get("extract_video_id")
        get_playlist_id = app_context.get("extract_playlist_id")
        get_transcript = app_context.get("get_transcript")
        generate_summary = app_context.get("generate_summary")
        get_video_details = app_context.get("get_video_details")
        get_videos_from_playlist = app_context.get("get_videos_from_playlist")
        save_summary_cache = app_context.get("save_summary_cache")

        # Store app context for worker threads
        self.app_context = app_context

        logger.info("✅ App functions configured for worker system")

    @property
    def max_workers(self):
        """Get the number of worker threads"""
        return self.num_workers

    def start(self):
        """Start all worker threads and management"""
        if self.is_running:
            logger.warning("WorkerManager is already running")
            return

        # Create and start workers
        for i in range(self.num_workers):
            worker_id = f"worker-{i+1}"
            worker = WorkerThread(
                worker_id=worker_id,
                job_scheduler=self.job_scheduler,
                notification_callback=self._handle_worker_notification
            )
            self.workers.append(worker)
            worker.start()

        # Start management thread
        self._should_stop_management = False
        self._management_thread = threading.Thread(target=self._management_loop, name="WorkerManager-Management")
        self._management_thread.daemon = True
        self._management_thread.start()

        self.is_running = True
        logger.info(f"Started WorkerManager with {len(self.workers)} workers")

    def stop(self, timeout: float = 30.0):
        """
        Stop all worker threads gracefully.

        Args:
            timeout: Maximum time to wait for shutdown
        """
        if not self.is_running:
            return

        logger.info("Stopping WorkerManager...")

        # Stop management thread
        self._should_stop_management = True
        if self._management_thread:
            self._management_thread.join(timeout=5.0)

        # Stop all workers
        stop_start_time = time.time()
        for worker in self.workers:
            remaining_timeout = max(0.0, timeout - (time.time() - stop_start_time))
            worker.stop(timeout=remaining_timeout)

        self.workers.clear()
        self.is_running = False

        logger.info("WorkerManager stopped")

    def submit_job(self, job: ProcessingJob, client_ip: str = None) -> tuple[bool, str]:
        """
        Submit a job for processing.

        Args:
            job: ProcessingJob to submit
            client_ip: Client IP for rate limiting

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.is_running:
            return False, "Worker manager is not running"

        return self.job_scheduler.submit_job(job, client_ip)

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a pending job.

        Args:
            job_id: ID of job to cancel

        Returns:
            True if cancelled successfully
        """
        return self.job_scheduler.cancel_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a specific job.

        Args:
            job_id: Job ID to check

        Returns:
            Job status dictionary or None
        """
        return self.job_scheduler.get_job_status(job_id)

    def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status"""
        queue_status = self.job_scheduler.get_queue_status()

        worker_statuses = [worker.get_status() for worker in self.workers]

        return {
            'is_running': self.is_running,
            'num_workers': len(self.workers),
            'workers': worker_statuses,
            'queue': queue_status,
            'system_metrics': {
                'total_workers': len(self.workers),
                'active_workers': sum(1 for w in self.workers if w.current_job is not None),
                'idle_workers': sum(1 for w in self.workers if w.current_job is None),
            }
        }

    def add_progress_callback(self, callback: Callable):
        """Add callback for progress updates"""
        self._progress_callbacks.append(callback)

    def add_completion_callback(self, callback: Callable):
        """Add callback for job completion"""
        self._completion_callbacks.append(callback)

    def _handle_worker_notification(self, job: ProcessingJob, result: Optional[JobResult],
                                   progress_update: bool = False):
        """
        Handle notifications from workers.

        Args:
            job: Job that triggered notification
            result: Job result (None for progress updates)
            progress_update: True if this is a progress update
        """
        try:
            if progress_update:
                # Handle progress notifications
                for callback in self._progress_callbacks:
                    callback(job)
            else:
                # Handle completion notifications
                for callback in self._completion_callbacks:
                    callback(job, result)
        except Exception as e:
            logger.error(f"Notification callback error: {e}")

    def _management_loop(self):
        """Management thread loop for periodic tasks"""
        logger.info("Started worker management thread")

        while not self._should_stop_management:
            try:
                # Perform periodic cleanup
                self.job_scheduler.cleanup_periodic()

                # Check worker health
                for worker in self.workers:
                    if not worker.is_running and not self._should_stop_management:
                        logger.warning(f"Worker {worker.worker_id} stopped unexpectedly, restarting...")
                        try:
                            worker.start()
                        except Exception as e:
                            logger.error(f"Failed to restart worker {worker.worker_id}: {e}")

                # Sleep for 30 seconds before next check
                for _ in range(30):
                    if self._should_stop_management:
                        break
                    time.sleep(1.0)

            except Exception as e:
                logger.error(f"Management loop error: {e}")
                time.sleep(5.0)  # Brief sleep on error

        logger.info("Worker management thread stopped")
