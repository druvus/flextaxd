"""Memory profiling utilities for large dataset processing."""

import psutil
import gc
from typing import Dict, Any, Optional, List, Callable
from functools import wraps
from dataclasses import dataclass, field
from time import time

from ..utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class MemorySnapshot:
    """Memory usage snapshot at a point in time."""

    timestamp: float
    rss_mb: float  # Resident Set Size in MB
    vms_mb: float  # Virtual Memory Size in MB
    available_mb: float  # Available memory in MB
    percent_used: float  # Percentage of memory used
    description: str = ""


@dataclass
class MemoryProfile:
    """Complete memory profiling data for an operation."""

    operation_name: str
    start_time: float
    end_time: float
    snapshots: List[MemorySnapshot] = field(default_factory=list)
    peak_rss_mb: float = 0.0
    peak_vms_mb: float = 0.0
    memory_growth_mb: float = 0.0

    @property
    def duration_seconds(self) -> float:
        """Get operation duration in seconds."""
        return self.end_time - self.start_time

    @property
    def average_memory_mb(self) -> float:
        """Get average RSS memory usage during operation."""
        if not self.snapshots:
            return 0.0
        return sum(s.rss_mb for s in self.snapshots) / len(self.snapshots)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "operation_name": self.operation_name,
            "duration_seconds": self.duration_seconds,
            "peak_rss_mb": self.peak_rss_mb,
            "peak_vms_mb": self.peak_vms_mb,
            "memory_growth_mb": self.memory_growth_mb,
            "average_memory_mb": self.average_memory_mb,
            "snapshots": len(self.snapshots),
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


class MemoryProfiler:
    """Memory profiler for tracking memory usage during operations."""

    def __init__(self, enable_detailed_snapshots: bool = False):
        self.enable_detailed_snapshots = enable_detailed_snapshots
        self._profiles: Dict[str, MemoryProfile] = {}
        self._current_profile: Optional[MemoryProfile] = None

        # Force garbage collection to get cleaner initial state
        gc.collect()

        # Get process handle
        self._process = psutil.Process()

    def _get_memory_info(self) -> Dict[str, float]:
        """Get current memory information."""
        # Get process memory info
        memory_info = self._process.memory_info()

        # Get system memory info
        virtual_memory = psutil.virtual_memory()

        return {
            "rss_mb": memory_info.rss / 1024 / 1024,
            "vms_mb": memory_info.vms / 1024 / 1024,
            "available_mb": virtual_memory.available / 1024 / 1024,
            "percent_used": virtual_memory.percent,
        }

    def take_snapshot(self, description: str = "") -> MemorySnapshot:
        """Take a memory usage snapshot."""
        memory_info = self._get_memory_info()

        snapshot = MemorySnapshot(
            timestamp=time(),
            rss_mb=memory_info["rss_mb"],
            vms_mb=memory_info["vms_mb"],
            available_mb=memory_info["available_mb"],
            percent_used=memory_info["percent_used"],
            description=description,
        )

        if self._current_profile:
            self._current_profile.snapshots.append(snapshot)

            # Update peak values
            if snapshot.rss_mb > self._current_profile.peak_rss_mb:
                self._current_profile.peak_rss_mb = snapshot.rss_mb
            if snapshot.vms_mb > self._current_profile.peak_vms_mb:
                self._current_profile.peak_vms_mb = snapshot.vms_mb

        return snapshot

    def start_profiling(self, operation_name: str) -> None:
        """Start profiling a new operation."""
        # Force garbage collection before starting
        gc.collect()

        self._current_profile = MemoryProfile(
            operation_name=operation_name, start_time=time(), end_time=0.0
        )

        # Take initial snapshot
        self.take_snapshot("start")

        logger.info(f"Started memory profiling for: {operation_name}")

    def stop_profiling(self) -> Optional[MemoryProfile]:
        """Stop current profiling and return the profile."""
        if not self._current_profile:
            logger.warning("No active profiling to stop")
            return None

        # Take final snapshot
        final_snapshot = self.take_snapshot("end")

        # Calculate final metrics
        self._current_profile.end_time = time()

        if self._current_profile.snapshots:
            initial_memory = self._current_profile.snapshots[0].rss_mb
            final_memory = final_snapshot.rss_mb
            self._current_profile.memory_growth_mb = final_memory - initial_memory

        # Store the completed profile
        profile_name = self._current_profile.operation_name
        self._profiles[profile_name] = self._current_profile

        logger.info(f"Completed memory profiling for: {profile_name}")
        logger.info(f"  Duration: {self._current_profile.duration_seconds:.2f}s")
        logger.info(f"  Peak RSS: {self._current_profile.peak_rss_mb:.1f} MB")
        logger.info(
            f"  Memory growth: {self._current_profile.memory_growth_mb:+.1f} MB"
        )

        completed_profile = self._current_profile
        self._current_profile = None

        return completed_profile

    def get_profile(self, operation_name: str) -> Optional[MemoryProfile]:
        """Get a completed memory profile by name."""
        return self._profiles.get(operation_name)

    def get_all_profiles(self) -> Dict[str, MemoryProfile]:
        """Get all completed memory profiles."""
        return self._profiles.copy()

    def clear_profiles(self) -> None:
        """Clear all stored profiles."""
        self._profiles.clear()

    def log_memory_usage(self, description: str = "") -> None:
        """Log current memory usage."""
        memory_info = self._get_memory_info()

        log_msg = f"Memory usage"
        if description:
            log_msg += f" ({description})"
        log_msg += f": RSS={memory_info['rss_mb']:.1f}MB, "
        log_msg += f"VMS={memory_info['vms_mb']:.1f}MB, "
        log_msg += f"Available={memory_info['available_mb']:.1f}MB"

        logger.info(log_msg)


def profile_memory(
    operation_name: Optional[str] = None, enable_snapshots: bool = False
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for automatic memory profiling of functions.

    Args:
        operation_name: Name for the profiling operation. Defaults to function name.
        enable_snapshots: Whether to take detailed memory snapshots during execution.

    Returns:
        Decorated function that will be memory profiled.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            profiler = MemoryProfiler(enable_detailed_snapshots=enable_snapshots)
            name = operation_name or f"{func.__module__}.{func.__name__}"

            profiler.start_profiling(name)
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                profile = profiler.stop_profiling()
                if profile:
                    # Store profile in function for access
                    wrapper.last_profile = profile  # type: ignore

        return wrapper

    return decorator


def check_memory_threshold(max_memory_mb: float, description: str = "") -> None:
    """Check if current memory usage exceeds a threshold.

    Args:
        max_memory_mb: Maximum allowed memory usage in MB.
        description: Description of what's being checked.

    Raises:
        RuntimeError: If memory usage exceeds threshold.
    """
    profiler = MemoryProfiler()
    snapshot = profiler.take_snapshot(description)

    if snapshot.rss_mb > max_memory_mb:
        msg = f"Memory usage ({snapshot.rss_mb:.1f} MB) exceeds threshold ({max_memory_mb} MB)"
        if description:
            msg += f" during: {description}"

        logger.error(msg)
        raise RuntimeError(msg)


def force_garbage_collection() -> Dict[str, Any]:
    """Force garbage collection and return collection stats.

    Returns:
        Dictionary with garbage collection statistics.
    """
    before_counts = gc.get_count()
    before_collected = sum(gc.get_stats()[i]["collections"] for i in range(3))

    # Force full garbage collection
    collected = gc.collect()

    after_counts = gc.get_count()
    after_collected = sum(gc.get_stats()[i]["collections"] for i in range(3))

    stats = {
        "objects_collected": collected,
        "before_counts": before_counts,
        "after_counts": after_counts,
        "total_collections": after_collected - before_collected,
    }

    logger.debug(f"Garbage collection completed: {stats}")
    return stats
