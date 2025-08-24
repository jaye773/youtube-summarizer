"""
Message compression system for SSE with support for multiple compression levels.
Provides thread-safe compression with Base64 encoding for transmission.
"""

import base64
import gzip
import json
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class CompressionLevel(Enum):
    """Compression levels with performance trade-offs."""

    FAST = 1  # Fast compression, larger size
    BALANCED = 6  # Balanced speed/size
    BEST = 9  # Best compression, slower


@dataclass
class CompressionStats:
    """Compression statistics and metrics."""

    original_size: int
    compressed_size: int
    compression_ratio: float
    compression_level: CompressionLevel
    processing_time_ms: float


class MessageCompressor:
    """Thread-safe message compression for SSE transmission."""

    # Compression threshold - messages larger than this will be compressed
    COMPRESSION_THRESHOLD = 1024  # 1KB

    def __init__(self, default_level: CompressionLevel = CompressionLevel.BALANCED):
        """Initialize compressor with default compression level."""
        self.default_level = default_level
        self._lock = threading.Lock()
        self._stats: Dict[str, CompressionStats] = {}

    def compress_message(
        self, message: Dict[str, Any], level: Optional[CompressionLevel] = None
    ) -> Tuple[str, Optional[CompressionStats]]:
        """
        Compress message if it exceeds threshold.

        Args:
            message: Dictionary message to potentially compress
            level: Compression level override

        Returns:
            Tuple of (encoded_message, compression_stats)
            If not compressed, stats will be None
        """
        import time

        start_time = time.time()

        # Serialize message
        try:
            serialized = json.dumps(message, separators=(",", ":"))
            original_size = len(serialized.encode("utf-8"))

            # Check if compression is needed
            if original_size <= self.COMPRESSION_THRESHOLD:
                return serialized, None

            # Compress the message
            compression_level = level or self.default_level
            compressed_data = gzip.compress(serialized.encode("utf-8"), compresslevel=compression_level.value)

            # Base64 encode for SSE transmission
            encoded_data = base64.b64encode(compressed_data).decode("ascii")

            # Calculate stats
            compressed_size = len(encoded_data)
            processing_time = (time.time() - start_time) * 1000

            stats = CompressionStats(
                original_size=original_size,
                compressed_size=compressed_size,
                compression_ratio=original_size / compressed_size if compressed_size > 0 else 0,
                compression_level=compression_level,
                processing_time_ms=processing_time,
            )

            # Store stats thread-safely
            with self._lock:
                message_id = message.get("id", "unknown")
                self._stats[message_id] = stats

            # Create compressed message envelope
            compressed_message = {
                "compressed": True,
                "data": encoded_data,
                "original_size": original_size,
                "compression_level": compression_level.name,
            }

            return json.dumps(compressed_message, separators=(",", ":")), stats

        except Exception:
            # Graceful fallback - return original message
            return json.dumps(message, separators=(",", ":")), None

    def get_stats(self, message_id: str) -> Optional[CompressionStats]:
        """Get compression statistics for a specific message."""
        with self._lock:
            return self._stats.get(message_id)

    def get_all_stats(self) -> Dict[str, CompressionStats]:
        """Get all compression statistics."""
        with self._lock:
            return self._stats.copy()

    def clear_stats(self) -> None:
        """Clear all compression statistics."""
        with self._lock:
            self._stats.clear()

    @staticmethod
    def decompress_message(encoded_message: str) -> Dict[str, Any]:
        """
        Decompress Base64 encoded compressed message.

        Args:
            encoded_message: Base64 encoded compressed message

        Returns:
            Decompressed message dictionary
        """
        try:
            # Parse the message envelope
            message_envelope = json.loads(encoded_message)

            # Check if message is compressed
            if not message_envelope.get("compressed", False):
                return message_envelope

            # Decode and decompress
            compressed_data = base64.b64decode(message_envelope["data"])
            decompressed_data = gzip.decompress(compressed_data)

            return json.loads(decompressed_data.decode("utf-8"))

        except Exception:
            # Fallback - try parsing as regular JSON
            return json.loads(encoded_message)
