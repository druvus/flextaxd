"""Progress reporting utilities for long-running operations."""

import sys
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional, Dict, Any, Iterator, Callable
import threading
from pathlib import Path


@dataclass
class ProgressInfo:
    """Information about current progress."""
    current: int
    total: int
    description: str = ""
    elapsed_time: float = 0.0
    
    @property
    def percentage(self) -> float:
        """Calculate completion percentage."""
        if self.total == 0:
            return 100.0
        return (self.current / self.total) * 100.0
    
    @property
    def eta_seconds(self) -> Optional[float]:
        """Estimate time remaining in seconds."""
        if self.current == 0 or self.elapsed_time == 0:
            return None
        
        rate = self.current / self.elapsed_time
        if rate == 0:
            return None
            
        remaining = self.total - self.current
        return remaining / rate
    
    @property
    def rate(self) -> float:
        """Calculate processing rate (items/second)."""
        if self.elapsed_time == 0:
            return 0.0
        return self.current / self.elapsed_time


class ProgressReporter(ABC):
    """Abstract base class for progress reporters."""
    
    @abstractmethod
    def start(self, total: int, description: str = "") -> None:
        """Start progress reporting."""
        pass
    
    @abstractmethod
    def update(self, current: int, description: str = "") -> None:
        """Update progress."""
        pass
    
    @abstractmethod
    def finish(self, message: str = "") -> None:
        """Finish progress reporting."""
        pass
    
    @abstractmethod
    def is_active(self) -> bool:
        """Check if progress reporting is active."""
        pass


class ConsoleProgressReporter(ProgressReporter):
    """Progress reporter that outputs to console."""
    
    def __init__(self, width: int = 50, show_eta: bool = True, show_rate: bool = True):
        self.width = width
        self.show_eta = show_eta
        self.show_rate = show_rate
        self.start_time = 0.0
        self.total = 0
        self.description = ""
        self._active = False
        self._last_update_time = 0.0
        self._update_interval = 0.1  # Update every 100ms max
    
    def start(self, total: int, description: str = "") -> None:
        """Start progress reporting."""
        self.total = total
        self.description = description
        self.start_time = time.time()
        self._active = True
        self._last_update_time = 0.0
        
        if description:
            print(f"{description}")
    
    def update(self, current: int, description: str = "") -> None:
        """Update progress display."""
        if not self._active:
            return
            
        # Throttle updates to avoid excessive console output
        current_time = time.time()
        if current_time - self._last_update_time < self._update_interval and current < self.total:
            return
        self._last_update_time = current_time
        
        elapsed = current_time - self.start_time
        progress_info = ProgressInfo(current, self.total, description, elapsed)
        
        # Build progress bar
        if self.total > 0:
            filled_width = int((current / self.total) * self.width)
            bar = "█" * filled_width + "░" * (self.width - filled_width)
            percentage = progress_info.percentage
        else:
            bar = "█" * self.width
            percentage = 100.0
        
        # Build status line
        status_parts = [f"{percentage:5.1f}% |{bar}| {current}/{self.total}"]
        
        if self.show_rate and progress_info.rate > 0:
            if progress_info.rate >= 1:
                status_parts.append(f"{progress_info.rate:.1f}/sec")
            else:
                status_parts.append(f"{progress_info.rate:.2f}/sec")
        
        if self.show_eta and progress_info.eta_seconds:
            eta = progress_info.eta_seconds
            if eta < 60:
                status_parts.append(f"ETA: {eta:.0f}s")
            elif eta < 3600:
                status_parts.append(f"ETA: {eta/60:.1f}m")
            else:
                status_parts.append(f"ETA: {eta/3600:.1f}h")
        
        if description:
            status_parts.append(description)
        
        status_line = " ".join(status_parts)
        
        # Clear line and print progress
        print(f"\r{status_line:<80}", end="", flush=True)
    
    def finish(self, message: str = "") -> None:
        """Finish progress reporting."""
        if not self._active:
            return
            
        self._active = False
        elapsed = time.time() - self.start_time
        
        # Final update
        print(f"\r{' ' * 80}", end="", flush=True)  # Clear line
        
        if message:
            print(f"\r✓ {message}")
        else:
            rate = self.total / elapsed if elapsed > 0 else 0
            print(f"\r✓ Completed {self.total} items in {elapsed:.1f}s ({rate:.1f}/sec)")
    
    def is_active(self) -> bool:
        """Check if progress reporting is active."""
        return self._active


class SilentProgressReporter(ProgressReporter):
    """Progress reporter that doesn't output anything (for testing/batch operations)."""
    
    def __init__(self):
        self._active = False
    
    def start(self, total: int, description: str = "") -> None:
        self._active = True
    
    def update(self, current: int, description: str = "") -> None:
        pass
    
    def finish(self, message: str = "") -> None:
        self._active = False
    
    def is_active(self) -> bool:
        return self._active


class LoggingProgressReporter(ProgressReporter):
    """Progress reporter that logs to a logger at intervals."""
    
    def __init__(self, logger, log_interval: int = 1000):
        self.logger = logger
        self.log_interval = log_interval
        self.start_time = 0.0
        self.total = 0
        self.description = ""
        self._active = False
        self._last_logged = 0
    
    def start(self, total: int, description: str = "") -> None:
        self.total = total
        self.description = description
        self.start_time = time.time()
        self._active = True
        self._last_logged = 0
        
        self.logger.info(f"Starting: {description} ({total} items)")
    
    def update(self, current: int, description: str = "") -> None:
        if not self._active:
            return
            
        # Log at intervals
        if current - self._last_logged >= self.log_interval or current == self.total:
            elapsed = time.time() - self.start_time
            progress_info = ProgressInfo(current, self.total, description, elapsed)
            
            log_msg = f"Progress: {progress_info.percentage:.1f}% ({current}/{self.total})"
            if progress_info.rate > 0:
                log_msg += f" at {progress_info.rate:.1f}/sec"
            if description:
                log_msg += f" - {description}"
                
            self.logger.info(log_msg)
            self._last_logged = current
    
    def finish(self, message: str = "") -> None:
        if not self._active:
            return
            
        self._active = False
        elapsed = time.time() - self.start_time
        
        if message:
            self.logger.info(f"Completed: {message}")
        else:
            rate = self.total / elapsed if elapsed > 0 else 0
            self.logger.info(f"Completed {self.total} items in {elapsed:.1f}s ({rate:.1f}/sec)")
    
    def is_active(self) -> bool:
        return self._active


class MultiProgressReporter(ProgressReporter):
    """Progress reporter that combines multiple reporters."""
    
    def __init__(self, reporters: list[ProgressReporter]):
        self.reporters = reporters
        self._active = False
    
    def start(self, total: int, description: str = "") -> None:
        self._active = True
        for reporter in self.reporters:
            reporter.start(total, description)
    
    def update(self, current: int, description: str = "") -> None:
        if not self._active:
            return
        for reporter in self.reporters:
            reporter.update(current, description)
    
    def finish(self, message: str = "") -> None:
        if not self._active:
            return
        self._active = False
        for reporter in self.reporters:
            reporter.finish(message)
    
    def is_active(self) -> bool:
        return self._active


class ProgressManager:
    """Centralized progress management for FlexTaxD operations."""
    
    def __init__(self):
        self._default_reporter: Optional[ProgressReporter] = None
        self._active_operations: Dict[str, ProgressReporter] = {}
        self._lock = threading.Lock()
    
    def set_default_reporter(self, reporter: ProgressReporter) -> None:
        """Set the default progress reporter."""
        self._default_reporter = reporter
    
    def get_reporter(self, operation_id: Optional[str] = None) -> ProgressReporter:
        """Get a progress reporter for an operation."""
        if operation_id and operation_id in self._active_operations:
            return self._active_operations[operation_id]
        
        if self._default_reporter:
            return self._default_reporter
            
        # Return console reporter as fallback
        return ConsoleProgressReporter()
    
    @contextmanager
    def operation(self, total: int, description: str = "", 
                  operation_id: Optional[str] = None,
                  reporter: Optional[ProgressReporter] = None) -> Iterator[ProgressReporter]:
        """Context manager for a progress-tracked operation."""
        
        if reporter is None:
            reporter = self.get_reporter(operation_id)
        
        if operation_id:
            with self._lock:
                self._active_operations[operation_id] = reporter
        
        try:
            reporter.start(total, description)
            yield reporter
        finally:
            reporter.finish()
            if operation_id:
                with self._lock:
                    self._active_operations.pop(operation_id, None)
    
    def create_callback(self, reporter: ProgressReporter) -> Callable[[int, int], None]:
        """Create a callback function for progress reporting."""
        def callback(current: int, total: int, description: str = ""):
            if not reporter.is_active():
                reporter.start(total, description)
            reporter.update(current, description)
        return callback


# Global progress manager instance
progress_manager = ProgressManager()


# Convenience functions
def set_progress_reporter(reporter: ProgressReporter) -> None:
    """Set the global default progress reporter."""
    progress_manager.set_default_reporter(reporter)


def create_console_reporter(width: int = 50, show_eta: bool = True, show_rate: bool = True) -> ConsoleProgressReporter:
    """Create a console progress reporter with specified options."""
    return ConsoleProgressReporter(width=width, show_eta=show_eta, show_rate=show_rate)


def create_silent_reporter() -> SilentProgressReporter:
    """Create a silent progress reporter."""
    return SilentProgressReporter()


def create_logging_reporter(logger, log_interval: int = 1000) -> LoggingProgressReporter:
    """Create a logging progress reporter."""
    return LoggingProgressReporter(logger, log_interval)


@contextmanager
def progress_operation(total: int, description: str = "", 
                      reporter: Optional[ProgressReporter] = None) -> Iterator[ProgressReporter]:
    """Context manager for a simple progress operation."""
    with progress_manager.operation(total, description, reporter=reporter) as prog:
        yield prog


# Decorators for easy integration
def with_progress(total_func: Optional[Callable] = None, description: str = ""):
    """Decorator to add progress reporting to a function."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Try to determine total from function or arguments
            if total_func:
                total = total_func(*args, **kwargs)
            else:
                # Look for common parameter names
                total = kwargs.get('total', kwargs.get('count', kwargs.get('items', 100)))
            
            with progress_operation(total, description or func.__name__) as progress:
                return func(*args, progress=progress, **kwargs)
        return wrapper
    return decorator