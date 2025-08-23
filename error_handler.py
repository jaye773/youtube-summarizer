"""
Error Classification and Retry Logic for YouTube Summarizer Async Worker

This module provides comprehensive error handling, classification, and retry
strategies for the async worker system. It categorizes different error types
and applies appropriate retry policies with exponential backoff.

Key Features:
- Error classification into categories (transcript, API, network, etc.)
- Exponential backoff retry strategies
- Different retry policies per error type
- Maximum retry limits and backoff caps
- Comprehensive error logging and metrics
"""

import logging
import random
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass

# Import job models once Module 1 is created
try:
    from job_models import JobStatus
except ImportError:
    # Fallback definition for standalone testing
    from enum import Enum
    
    class JobStatus(Enum):
        PENDING = "pending"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        FAILED = "failed"
        RETRY = "retry"

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories of errors that can occur during job processing."""
    TRANSCRIPT = "transcript_error"      # YouTube transcript unavailable/failed
    API_RATE_LIMIT = "api_rate_limit"   # API rate limiting (OpenAI, Gemini)
    API_QUOTA = "api_quota"             # API quota exceeded
    NETWORK = "network_error"           # Network connectivity issues
    MODEL_ERROR = "model_error"         # AI model processing errors
    SYSTEM_ERROR = "system_error"       # System/infrastructure errors
    VALIDATION = "validation_error"     # Input validation errors
    TIMEOUT = "timeout_error"           # Operation timeout
    UNKNOWN = "unknown_error"           # Unclassified errors


@dataclass
class ErrorInfo:
    """Information about a specific error occurrence."""
    category: ErrorCategory
    message: str
    timestamp: datetime
    retry_eligible: bool
    retry_delay: float  # Seconds to wait before retry
    max_retries: int
    metadata: Dict[str, Any]


@dataclass
class RetryPolicy:
    """Retry policy configuration for an error category."""
    max_retries: int
    base_delay: float           # Base delay in seconds
    max_delay: float           # Maximum delay in seconds
    backoff_multiplier: float  # Exponential backoff multiplier
    jitter: bool               # Add random jitter to delays
    retry_eligible: bool       # Whether this error type is retry-eligible


class ErrorHandler:
    """
    Comprehensive error handling and retry logic for async job processing.
    
    Classifies errors into categories and applies appropriate retry strategies
    with exponential backoff and jitter for optimal retry patterns.
    """

    def __init__(self):
        """Initialize the Error Handler with default retry policies."""
        self._error_stats: Dict[str, int] = {}
        self._retry_policies = self._initialize_retry_policies()
        
        # Error pattern matching for classification
        self._error_patterns = self._initialize_error_patterns()
        
        logger.info("ErrorHandler initialized with retry policies for all error categories")

    def _initialize_retry_policies(self) -> Dict[ErrorCategory, RetryPolicy]:
        """Initialize retry policies for each error category."""
        return {
            # Transcript errors - moderate retries (YouTube API might recover)
            ErrorCategory.TRANSCRIPT: RetryPolicy(
                max_retries=3,
                base_delay=5.0,
                max_delay=300.0,  # 5 minutes
                backoff_multiplier=2.0,
                jitter=True,
                retry_eligible=True
            ),
            
            # API rate limiting - aggressive retries with longer delays
            ErrorCategory.API_RATE_LIMIT: RetryPolicy(
                max_retries=5,
                base_delay=60.0,  # Start with 1 minute
                max_delay=3600.0,  # Up to 1 hour
                backoff_multiplier=2.0,
                jitter=True,
                retry_eligible=True
            ),
            
            # API quota - minimal retries (needs user intervention)
            ErrorCategory.API_QUOTA: RetryPolicy(
                max_retries=1,
                base_delay=3600.0,  # 1 hour
                max_delay=3600.0,
                backoff_multiplier=1.0,
                jitter=False,
                retry_eligible=True
            ),
            
            # Network errors - moderate retries
            ErrorCategory.NETWORK: RetryPolicy(
                max_retries=4,
                base_delay=10.0,
                max_delay=600.0,  # 10 minutes
                backoff_multiplier=2.0,
                jitter=True,
                retry_eligible=True
            ),
            
            # Model processing errors - limited retries
            ErrorCategory.MODEL_ERROR: RetryPolicy(
                max_retries=2,
                base_delay=30.0,
                max_delay=300.0,
                backoff_multiplier=2.0,
                jitter=True,
                retry_eligible=True
            ),
            
            # System errors - moderate retries
            ErrorCategory.SYSTEM_ERROR: RetryPolicy(
                max_retries=3,
                base_delay=15.0,
                max_delay=600.0,
                backoff_multiplier=2.0,
                jitter=True,
                retry_eligible=True
            ),
            
            # Validation errors - no retries (user input issue)
            ErrorCategory.VALIDATION: RetryPolicy(
                max_retries=0,
                base_delay=0.0,
                max_delay=0.0,
                backoff_multiplier=1.0,
                jitter=False,
                retry_eligible=False
            ),
            
            # Timeout errors - moderate retries
            ErrorCategory.TIMEOUT: RetryPolicy(
                max_retries=3,
                base_delay=30.0,
                max_delay=900.0,  # 15 minutes
                backoff_multiplier=1.5,
                jitter=True,
                retry_eligible=True
            ),
            
            # Unknown errors - conservative retries
            ErrorCategory.UNKNOWN: RetryPolicy(
                max_retries=2,
                base_delay=60.0,
                max_delay=600.0,
                backoff_multiplier=2.0,
                jitter=True,
                retry_eligible=True
            )
        }

    def _initialize_error_patterns(self) -> Dict[ErrorCategory, List[str]]:
        """Initialize error pattern matching for classification."""
        return {
            ErrorCategory.TRANSCRIPT: [
                "transcript not available",
                "subtitles not available", 
                "transcript fetch failed",
                "youtube transcript error",
                "captions disabled",
                "no transcript found",
                "transcript unavailable"
            ],
            
            ErrorCategory.API_RATE_LIMIT: [
                "rate limit exceeded",
                "too many requests",
                "quota exceeded",
                "api rate limit",
                "rate_limit_exceeded",
                "throttled",
                "429",  # HTTP status code
                "rate limited"
            ],
            
            ErrorCategory.API_QUOTA: [
                "quota exceeded",
                "billing quota exceeded",
                "monthly quota",
                "usage limit exceeded",
                "insufficient quota",
                "quota limit reached"
            ],
            
            ErrorCategory.NETWORK: [
                "connection error",
                "network error",
                "timeout",
                "dns resolution failed",
                "connection refused",
                "network unreachable",
                "connection timeout",
                "socket timeout",
                "ssl error",
                "certificate error"
            ],
            
            ErrorCategory.MODEL_ERROR: [
                "model error",
                "processing failed",
                "ai model error",
                "generation failed",
                "model timeout",
                "model unavailable",
                "inference error",
                "content filter",
                "safety filter"
            ],
            
            ErrorCategory.SYSTEM_ERROR: [
                "internal server error",
                "system error",
                "service unavailable",
                "memory error",
                "disk space",
                "permission denied",
                "file system error",
                "database error",
                "500",  # HTTP status code
                "503"   # Service unavailable
            ],
            
            ErrorCategory.VALIDATION: [
                "invalid url",
                "invalid input",
                "validation error",
                "bad request",
                "malformed",
                "invalid format",
                "missing required",
                "400"  # HTTP status code
            ],
            
            ErrorCategory.TIMEOUT: [
                "timeout",
                "deadline exceeded",
                "operation timeout",
                "request timeout",
                "processing timeout",
                "time limit exceeded"
            ]
        }

    def classify_error(
        self, 
        error: Exception, 
        context: Optional[Dict[str, Any]] = None
    ) -> ErrorCategory:
        """
        Classify an error into a category based on error message and context.

        Args:
            error: Exception that occurred
            context: Optional context information about the operation

        Returns:
            ErrorCategory enum value
        """
        error_message = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # Check context for additional clues
        if context:
            context_str = str(context).lower()
            error_message += f" {context_str}"

        # Try to match error patterns
        for category, patterns in self._error_patterns.items():
            for pattern in patterns:
                if pattern.lower() in error_message or pattern.lower() in error_type:
                    logger.debug(f"Classified error as {category.value}: matched pattern '{pattern}'")
                    return category

        # Special handling for common exception types
        if "timeout" in error_type:
            return ErrorCategory.TIMEOUT
        elif "connection" in error_type or "network" in error_type:
            return ErrorCategory.NETWORK
        elif "validation" in error_type or "value" in error_type:
            return ErrorCategory.VALIDATION
        elif "permission" in error_type or "access" in error_type:
            return ErrorCategory.SYSTEM_ERROR

        logger.warning(f"Could not classify error: {error_message[:100]}")
        return ErrorCategory.UNKNOWN

    def handle_error(
        self, 
        error: Exception, 
        job_id: str, 
        retry_count: int = 0,
        context: Optional[Dict[str, Any]] = None
    ) -> ErrorInfo:
        """
        Handle an error by classifying it and determining retry strategy.

        Args:
            error: Exception that occurred
            job_id: ID of the job that failed
            retry_count: Current number of retries for this job
            context: Optional context information

        Returns:
            ErrorInfo object with classification and retry information
        """
        # Classify the error
        category = self.classify_error(error, context)
        
        # Get retry policy for this category
        policy = self._retry_policies[category]
        
        # Determine if retry is eligible
        retry_eligible = (
            policy.retry_eligible and 
            retry_count < policy.max_retries
        )
        
        # Calculate retry delay with exponential backoff
        retry_delay = 0.0
        if retry_eligible:
            retry_delay = self._calculate_retry_delay(
                policy, retry_count
            )

        # Update error statistics
        self._update_error_stats(category, retry_eligible)

        # Create error info
        error_info = ErrorInfo(
            category=category,
            message=str(error),
            timestamp=datetime.now(),
            retry_eligible=retry_eligible,
            retry_delay=retry_delay,
            max_retries=policy.max_retries,
            metadata={
                'job_id': job_id,
                'retry_count': retry_count,
                'error_type': type(error).__name__,
                'context': context or {}
            }
        )

        # Log error details
        self._log_error(error_info, error)

        return error_info

    def _calculate_retry_delay(
        self, 
        policy: RetryPolicy, 
        retry_count: int
    ) -> float:
        """
        Calculate retry delay using exponential backoff.

        Args:
            policy: Retry policy configuration
            retry_count: Current retry attempt number

        Returns:
            Delay in seconds before next retry
        """
        # Exponential backoff: base_delay * (multiplier ^ retry_count)
        delay = policy.base_delay * (policy.backoff_multiplier ** retry_count)
        
        # Cap at maximum delay
        delay = min(delay, policy.max_delay)
        
        # Add jitter if enabled (±25% random variation)
        if policy.jitter:
            jitter_range = delay * 0.25
            jitter = random.uniform(-jitter_range, jitter_range)
            delay += jitter
            
        # Ensure non-negative delay
        return max(0.0, delay)

    def _update_error_stats(
        self, 
        category: ErrorCategory, 
        retry_eligible: bool
    ) -> None:
        """Update internal error statistics."""
        category_key = category.value
        self._error_stats[category_key] = self._error_stats.get(category_key, 0) + 1
        
        if retry_eligible:
            retry_key = f"{category_key}_retries"
            self._error_stats[retry_key] = self._error_stats.get(retry_key, 0) + 1

    def _log_error(self, error_info: ErrorInfo, original_error: Exception) -> None:
        """Log error information with appropriate severity level."""
        job_id = error_info.metadata.get('job_id', 'unknown')
        retry_count = error_info.metadata.get('retry_count', 0)
        
        base_message = (
            f"Job {job_id} failed with {error_info.category.value}: "
            f"{error_info.message[:200]}"
        )
        
        if error_info.retry_eligible:
            logger.warning(
                f"{base_message} | Retry {retry_count + 1}/{error_info.max_retries} "
                f"in {error_info.retry_delay:.1f}s"
            )
        else:
            if error_info.category == ErrorCategory.VALIDATION:
                logger.error(f"{base_message} | Not retryable - validation error")
            else:
                logger.error(
                    f"{base_message} | Max retries exceeded "
                    f"({retry_count}/{error_info.max_retries})"
                )

        # Log full exception details at debug level
        logger.debug(f"Full error details for job {job_id}", exc_info=original_error)

    def get_next_retry_time(
        self, 
        error_info: ErrorInfo
    ) -> Optional[datetime]:
        """
        Get the datetime when the next retry should occur.

        Args:
            error_info: Error information from handle_error

        Returns:
            Datetime of next retry or None if not retryable
        """
        if not error_info.retry_eligible:
            return None
            
        return error_info.timestamp + timedelta(seconds=error_info.retry_delay)

    def should_retry_now(
        self, 
        error_info: ErrorInfo, 
        current_time: Optional[datetime] = None
    ) -> bool:
        """
        Check if a job should be retried now.

        Args:
            error_info: Error information from handle_error
            current_time: Optional current time (defaults to datetime.now())

        Returns:
            True if job should be retried now
        """
        if not error_info.retry_eligible:
            return False
            
        current_time = current_time or datetime.now()
        next_retry_time = self.get_next_retry_time(error_info)
        
        return next_retry_time is not None and current_time >= next_retry_time

    def get_error_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive error statistics.

        Returns:
            Dictionary with error statistics by category
        """
        stats = {
            'total_errors': sum(self._error_stats.values()),
            'by_category': {},
            'retry_stats': {},
            'most_common_errors': []
        }

        # Group by category and calculate retry stats
        category_counts = {}
        category_retries = {}
        
        for key, count in self._error_stats.items():
            if key.endswith('_retries'):
                category = key.replace('_retries', '')
                category_retries[category] = count
            else:
                category_counts[key] = count

        # Build category statistics
        for category_name in category_counts:
            total_errors = category_counts[category_name]
            total_retries = category_retries.get(category_name, 0)
            
            stats['by_category'][category_name] = {
                'total_errors': total_errors,
                'total_retries': total_retries,
                'retry_rate': total_retries / total_errors if total_errors > 0 else 0.0
            }

        # Find most common errors
        sorted_errors = sorted(
            category_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        stats['most_common_errors'] = [
            {'category': category, 'count': count} 
            for category, count in sorted_errors[:5]
        ]

        return stats

    def reset_statistics(self) -> None:
        """Reset error statistics (useful for testing)."""
        logger.info("Resetting error handler statistics")
        self._error_stats.clear()

    def update_retry_policy(
        self, 
        category: ErrorCategory, 
        policy: RetryPolicy
    ) -> None:
        """
        Update retry policy for a specific error category.

        Args:
            category: Error category to update
            policy: New retry policy configuration
        """
        logger.info(f"Updating retry policy for {category.value}")
        self._retry_policies[category] = policy

    def get_retry_policy(self, category: ErrorCategory) -> RetryPolicy:
        """
        Get current retry policy for an error category.

        Args:
            category: Error category

        Returns:
            Current retry policy
        """
        return self._retry_policies[category]