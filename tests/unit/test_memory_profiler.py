"""Unit tests for memory profiling utilities."""

import pytest
import time
from unittest.mock import Mock, patch

from flextaxd.utils.memory_profiler import (
    MemorySnapshot, MemoryProfile, MemoryProfiler, 
    profile_memory, check_memory_threshold, force_garbage_collection
)


class TestMemorySnapshot:
    """Test MemorySnapshot dataclass."""
    
    def test_create_snapshot(self):
        """Test creating memory snapshot."""
        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=100.5,
            vms_mb=200.0,
            available_mb=1024.0,
            percent_used=25.5,
            description="test snapshot"
        )
        
        assert snapshot.rss_mb == 100.5
        assert snapshot.vms_mb == 200.0
        assert snapshot.available_mb == 1024.0
        assert snapshot.percent_used == 25.5
        assert snapshot.description == "test snapshot"


class TestMemoryProfile:
    """Test MemoryProfile dataclass."""
    
    def test_create_profile(self):
        """Test creating memory profile."""
        start_time = time.time()
        end_time = start_time + 10.0
        
        profile = MemoryProfile(
            operation_name="test_operation",
            start_time=start_time,
            end_time=end_time,
            peak_rss_mb=150.0,
            peak_vms_mb=300.0,
            memory_growth_mb=25.0
        )
        
        assert profile.operation_name == "test_operation"
        assert profile.duration_seconds == 10.0
        assert profile.peak_rss_mb == 150.0
        assert profile.memory_growth_mb == 25.0
    
    def test_average_memory_calculation(self):
        """Test average memory calculation."""
        profile = MemoryProfile(
            operation_name="test",
            start_time=0.0,
            end_time=1.0
        )
        
        # No snapshots
        assert profile.average_memory_mb == 0.0
        
        # Add snapshots
        snapshots = [
            MemorySnapshot(0.0, 100.0, 200.0, 1000.0, 10.0, "start"),
            MemorySnapshot(0.5, 120.0, 220.0, 980.0, 12.0, "middle"),
            MemorySnapshot(1.0, 110.0, 210.0, 990.0, 11.0, "end")
        ]
        profile.snapshots = snapshots
        
        # Average should be (100 + 120 + 110) / 3 = 110
        assert profile.average_memory_mb == 110.0
    
    def test_to_dict_conversion(self):
        """Test converting profile to dictionary."""
        profile = MemoryProfile(
            operation_name="test_op",
            start_time=100.0,
            end_time=110.0,
            peak_rss_mb=200.0,
            peak_vms_mb=400.0,
            memory_growth_mb=50.0
        )
        
        result = profile.to_dict()
        
        assert result["operation_name"] == "test_op"
        assert result["duration_seconds"] == 10.0
        assert result["peak_rss_mb"] == 200.0
        assert result["memory_growth_mb"] == 50.0
        assert "start_time" in result
        assert "end_time" in result


class TestMemoryProfiler:
    """Test MemoryProfiler class."""
    
    @patch('flextaxd.utils.memory_profiler.psutil.Process')
    @patch('flextaxd.utils.memory_profiler.psutil.virtual_memory')
    def test_profiler_initialization(self, mock_virtual_memory, mock_process_class):
        """Test profiler initialization."""
        # Mock psutil returns
        mock_process = Mock()
        mock_process_class.return_value = mock_process
        
        mock_virtual_memory.return_value = Mock(
            available=1024*1024*1024,  # 1GB
            percent=25.0
        )
        
        profiler = MemoryProfiler()
        
        assert profiler._process == mock_process
        assert not profiler.enable_detailed_snapshots
    
    @patch('flextaxd.utils.memory_profiler.psutil.Process')
    @patch('flextaxd.utils.memory_profiler.psutil.virtual_memory')
    def test_take_snapshot(self, mock_virtual_memory, mock_process_class):
        """Test taking memory snapshot."""
        # Mock process memory info
        mock_process = Mock()
        mock_process.memory_info.return_value = Mock(
            rss=100*1024*1024,  # 100MB
            vms=200*1024*1024   # 200MB
        )
        mock_process_class.return_value = mock_process
        
        # Mock virtual memory
        mock_virtual_memory.return_value = Mock(
            available=512*1024*1024,  # 512MB
            percent=50.0
        )
        
        profiler = MemoryProfiler()
        snapshot = profiler.take_snapshot("test snapshot")
        
        assert snapshot.rss_mb == 100.0
        assert snapshot.vms_mb == 200.0
        assert snapshot.available_mb == 512.0
        assert snapshot.percent_used == 50.0
        assert snapshot.description == "test snapshot"
    
    @patch('flextaxd.utils.memory_profiler.psutil.Process')
    @patch('flextaxd.utils.memory_profiler.psutil.virtual_memory')
    def test_start_stop_profiling(self, mock_virtual_memory, mock_process_class):
        """Test starting and stopping profiling."""
        # Setup mocks
        mock_process = Mock()
        mock_process.memory_info.return_value = Mock(rss=100*1024*1024, vms=200*1024*1024)
        mock_process_class.return_value = mock_process
        
        mock_virtual_memory.return_value = Mock(available=512*1024*1024, percent=50.0)
        
        profiler = MemoryProfiler()
        
        # Start profiling
        profiler.start_profiling("test_operation")
        
        assert profiler._current_profile is not None
        assert profiler._current_profile.operation_name == "test_operation"
        assert len(profiler._current_profile.snapshots) == 1  # Initial snapshot
        
        # Stop profiling
        profile = profiler.stop_profiling()
        
        assert profile is not None
        assert profile.operation_name == "test_operation"
        assert len(profile.snapshots) == 2  # Start + end snapshots
        assert profile.end_time > profile.start_time
        assert profiler._current_profile is None
    
    def test_stop_profiling_without_start(self):
        """Test stopping profiling without starting."""
        profiler = MemoryProfiler()
        
        result = profiler.stop_profiling()
        
        assert result is None
    
    def test_get_profile(self):
        """Test getting stored profile."""
        profiler = MemoryProfiler()
        
        # No profile exists
        assert profiler.get_profile("nonexistent") is None
        
        # Create a mock profile and add it directly
        mock_profile = MemoryProfile("test", 0.0, 1.0)
        profiler._profiles["test"] = mock_profile
        
        # Should return the profile
        retrieved = profiler.get_profile("test")
        assert retrieved == mock_profile
    
    def test_clear_profiles(self):
        """Test clearing all profiles."""
        profiler = MemoryProfiler()
        
        # Add mock profile
        mock_profile = MemoryProfile("test", 0.0, 1.0)
        profiler._profiles["test"] = mock_profile
        
        # Clear profiles
        profiler.clear_profiles()
        
        assert len(profiler._profiles) == 0
        assert profiler.get_profile("test") is None


class TestProfileMemoryDecorator:
    """Test profile_memory decorator."""
    
    @patch('flextaxd.utils.memory_profiler.MemoryProfiler')
    def test_profile_memory_decorator(self, mock_profiler_class):
        """Test profile_memory decorator functionality."""
        # Setup mock profiler
        mock_profiler = Mock()
        mock_profile = Mock()
        mock_profiler.stop_profiling.return_value = mock_profile
        mock_profiler_class.return_value = mock_profiler
        
        @profile_memory("test_operation")
        def test_function(x, y):
            return x + y
        
        # Call decorated function
        result = test_function(1, 2)
        
        # Check results
        assert result == 3
        mock_profiler.start_profiling.assert_called_once_with("test_operation")
        mock_profiler.stop_profiling.assert_called_once()
        
        # Check that profile is attached to function
        assert hasattr(test_function, 'last_profile')
        assert test_function.last_profile == mock_profile
    
    @patch('flextaxd.utils.memory_profiler.MemoryProfiler')
    def test_profile_memory_decorator_default_name(self, mock_profiler_class):
        """Test decorator with default operation name."""
        mock_profiler = Mock()
        mock_profiler_class.return_value = mock_profiler
        
        @profile_memory()
        def test_function():
            pass
        
        test_function()
        
        # Should use module.function as name
        expected_name = f"{test_function.__module__}.{test_function.__name__}"
        mock_profiler.start_profiling.assert_called_once_with(expected_name)
    
    @patch('flextaxd.utils.memory_profiler.MemoryProfiler')
    def test_profile_memory_decorator_exception(self, mock_profiler_class):
        """Test decorator behavior when function raises exception."""
        mock_profiler = Mock()
        mock_profiler_class.return_value = mock_profiler
        
        @profile_memory("failing_operation")
        def failing_function():
            raise ValueError("Test error")
        
        # Function should still raise exception
        with pytest.raises(ValueError, match="Test error"):
            failing_function()
        
        # But profiling should still be stopped
        mock_profiler.start_profiling.assert_called_once()
        mock_profiler.stop_profiling.assert_called_once()


class TestMemoryThreshold:
    """Test memory threshold checking."""
    
    @patch('flextaxd.utils.memory_profiler.MemoryProfiler')
    def test_check_memory_threshold_success(self, mock_profiler_class):
        """Test memory threshold check that passes."""
        # Mock profiler and snapshot
        mock_profiler = Mock()
        mock_snapshot = Mock()
        mock_snapshot.rss_mb = 100.0  # 100MB usage
        mock_profiler.take_snapshot.return_value = mock_snapshot
        mock_profiler_class.return_value = mock_profiler
        
        # Should not raise exception (100MB < 200MB threshold)
        check_memory_threshold(200.0, "test operation")
        
        mock_profiler.take_snapshot.assert_called_once_with("test operation")
    
    @patch('flextaxd.utils.memory_profiler.MemoryProfiler')
    def test_check_memory_threshold_failure(self, mock_profiler_class):
        """Test memory threshold check that fails."""
        # Mock profiler and snapshot
        mock_profiler = Mock()
        mock_snapshot = Mock()
        mock_snapshot.rss_mb = 300.0  # 300MB usage
        mock_profiler.take_snapshot.return_value = mock_snapshot
        mock_profiler_class.return_value = mock_profiler
        
        # Should raise exception (300MB > 200MB threshold)
        with pytest.raises(RuntimeError, match="Memory usage.*exceeds threshold"):
            check_memory_threshold(200.0, "test operation")


class TestGarbageCollection:
    """Test garbage collection utilities."""
    
    @patch('flextaxd.utils.memory_profiler.gc')
    def test_force_garbage_collection(self, mock_gc):
        """Test forced garbage collection."""
        # Mock gc module
        mock_gc.get_count.side_effect = [
            (100, 10, 1),  # Before
            (50, 5, 0)     # After
        ]
        mock_gc.get_stats.return_value = [
            {'collections': 10},
            {'collections': 5}, 
            {'collections': 1}
        ]
        mock_gc.collect.return_value = 25  # Objects collected
        
        stats = force_garbage_collection()
        
        assert stats['objects_collected'] == 25
        assert stats['before_counts'] == (100, 10, 1)
        assert stats['after_counts'] == (50, 5, 0)
        
        mock_gc.collect.assert_called_once()