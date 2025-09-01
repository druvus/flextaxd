"""Unit tests for subprocess utilities."""

import pytest
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from flextaxd.utils.subprocess_utils import (
    SubprocessError, run_command, run_command_safely, create_directory
)


class TestSubprocessError:
    """Test SubprocessError exception."""
    
    def test_subprocess_error_creation(self):
        """Test creating SubprocessError."""
        error = SubprocessError("Test error message")
        assert str(error) == "Test error message"
        assert isinstance(error, Exception)


class TestRunCommand:
    """Test run_command function."""
    
    @patch('flextaxd.utils.subprocess_utils.subprocess.run')
    def test_run_command_success_string(self, mock_run):
        """Test successful command execution with string command."""
        # Mock successful subprocess.run
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = b"success output"
        mock_result.stderr = b""
        mock_run.return_value = mock_result
        
        result = run_command("echo hello")
        
        assert result == mock_result
        mock_run.assert_called_once()
        
        # Check that command was properly split
        call_args = mock_run.call_args
        assert call_args[0][0] == ['echo', 'hello']  # Command should be split
    
    @patch('flextaxd.utils.subprocess_utils.subprocess.run')
    def test_run_command_success_list(self, mock_run):
        """Test successful command execution with list command."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        result = run_command(['echo', 'hello'])
        
        assert result == mock_result
        mock_run.assert_called_once()
        
        # Command should be passed as-is when it's already a list
        call_args = mock_run.call_args
        assert call_args[0][0] == ['echo', 'hello']
    
    @patch('flextaxd.utils.subprocess_utils.subprocess.run')
    def test_run_command_with_shell(self, mock_run):
        """Test command execution with shell=True."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        result = run_command("echo $HOME", shell=True)
        
        assert result == mock_result
        
        # When shell=True, command should remain as string
        call_args = mock_run.call_args
        assert call_args[0][0] == "echo $HOME"
        assert call_args[1]['shell'] is True
    
    @patch('flextaxd.utils.subprocess_utils.subprocess.run')
    def test_run_command_with_options(self, mock_run):
        """Test command execution with various options."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        test_cwd = Path("/test/dir")
        test_env = {"VAR": "value"}
        
        result = run_command(
            "echo test",
            cwd=test_cwd,
            timeout=30,
            check=False,
            capture_output=True,
            env=test_env
        )
        
        assert result == mock_result
        
        # Check that options were passed correctly
        call_args = mock_run.call_args
        kwargs = call_args[1]
        assert kwargs['cwd'] == test_cwd
        assert kwargs['timeout'] == 30
        assert kwargs['check'] is False
        # capture_output=True is converted to stdout/stderr parameters
        assert kwargs['stdout'] == -1  # subprocess.PIPE
        assert kwargs['stderr'] == -1  # subprocess.PIPE
        assert kwargs['env'] == test_env
    
    @patch('flextaxd.utils.subprocess_utils.subprocess.run')
    def test_run_command_timeout_error(self, mock_run):
        """Test command execution timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired('test', 30)
        
        with pytest.raises(SubprocessError, match="Command timed out"):
            run_command("sleep 60", timeout=30)
    
    @patch('flextaxd.utils.subprocess_utils.subprocess.run')
    def test_run_command_file_not_found(self, mock_run):
        """Test command execution with file not found."""
        mock_run.side_effect = FileNotFoundError("Command not found")
        
        with pytest.raises(SubprocessError, match="Command not found"):
            run_command("nonexistent_command")
    
    @patch('flextaxd.utils.subprocess_utils.subprocess.run')
    def test_run_command_os_error(self, mock_run):
        """Test command execution with OS error."""
        mock_run.side_effect = OSError("Permission denied")
        
        with pytest.raises(SubprocessError, match="Failed to run command"):
            run_command("restricted_command")
    
    @patch('flextaxd.utils.subprocess_utils.subprocess.run')
    def test_run_command_called_process_error(self, mock_run):
        """Test command execution with CalledProcessError."""
        error = subprocess.CalledProcessError(1, 'test', "error output")
        mock_run.side_effect = error
        
        with pytest.raises(SubprocessError, match="Command failed with return code 1"):
            run_command("failing_command")


class TestRunCommandSafely:
    """Test run_command_safely wrapper function."""
    
    @patch('flextaxd.utils.subprocess_utils.run_command')
    def test_run_command_safely_defaults(self, mock_run_command):
        """Test run_command_safely applies safe defaults."""
        mock_result = Mock()
        mock_run_command.return_value = mock_result
        
        result = run_command_safely("echo test")
        
        assert result == mock_result
        
        # Check that safe defaults were applied
        mock_run_command.assert_called_once()
        call_args = mock_run_command.call_args
        
        # Check command
        assert call_args[0][0] == "echo test"
        
        # Check keyword arguments include safe defaults
        kwargs = call_args[1]
        assert kwargs['shell'] is False
        assert kwargs['check'] is True
        assert kwargs['capture_output'] is True
        assert kwargs['timeout'] == 300  # 5 minute default
    
    @patch('flextaxd.utils.subprocess_utils.run_command')
    def test_run_command_safely_override_defaults(self, mock_run_command):
        """Test run_command_safely allows overriding defaults."""
        mock_result = Mock()
        mock_run_command.return_value = mock_result
        
        result = run_command_safely(
            "echo test",
            timeout=60,
            check=False,
            capture_output=False
        )
        
        assert result == mock_result
        
        # Check that overrides were applied
        call_args = mock_run_command.call_args
        kwargs = call_args[1]
        assert kwargs['timeout'] == 60  # Overridden
        assert kwargs['check'] is False  # Overridden
        assert kwargs['capture_output'] is False  # Overridden
        assert kwargs['shell'] is False  # Default maintained
    
    @patch('flextaxd.utils.subprocess_utils.run_command')
    def test_run_command_safely_extra_kwargs(self, mock_run_command):
        """Test run_command_safely passes through extra kwargs."""
        mock_result = Mock()
        mock_run_command.return_value = mock_result
        
        test_env = {"TEST": "value"}
        result = run_command_safely("echo test", env=test_env, custom_arg="custom")
        
        assert result == mock_result
        
        # Check that extra kwargs were passed through
        call_args = mock_run_command.call_args
        kwargs = call_args[1]
        assert kwargs['env'] == test_env
        assert kwargs['custom_arg'] == "custom"


class TestCreateDirectory:
    """Test create_directory function."""
    
    def test_create_directory_success(self, tmp_path):
        """Test successful directory creation."""
        test_dir = tmp_path / "test_directory"
        
        # Directory should not exist initially
        assert not test_dir.exists()
        
        # Create directory
        create_directory(test_dir)
        
        # Directory should now exist
        assert test_dir.exists()
        assert test_dir.is_dir()
    
    def test_create_directory_already_exists(self, tmp_path):
        """Test creating directory that already exists."""
        test_dir = tmp_path / "existing_directory"
        test_dir.mkdir()
        
        # Should not raise error when directory already exists
        create_directory(test_dir, exist_ok=True)
        
        # Directory should still exist
        assert test_dir.exists()
        assert test_dir.is_dir()
    
    def test_create_directory_already_exists_no_exist_ok(self, tmp_path):
        """Test creating directory that already exists with exist_ok=False."""
        test_dir = tmp_path / "existing_directory"
        test_dir.mkdir()
        
        # Should raise SubprocessError when directory exists and exist_ok=False
        with pytest.raises(SubprocessError, match="Failed to create directory"):
            create_directory(test_dir, exist_ok=False)
    
    def test_create_directory_nested_path(self, tmp_path):
        """Test creating nested directory structure."""
        nested_dir = tmp_path / "level1" / "level2" / "level3"
        
        # Nested path should not exist initially
        assert not nested_dir.exists()
        
        # Create nested directory
        create_directory(nested_dir)
        
        # All levels should now exist
        assert nested_dir.exists()
        assert nested_dir.is_dir()
        assert (tmp_path / "level1").exists()
        assert (tmp_path / "level1" / "level2").exists()
    
    def test_create_directory_permission_error(self, tmp_path):
        """Test directory creation with permission error."""
        # Create a directory and make it read-only
        parent_dir = tmp_path / "readonly_parent"
        parent_dir.mkdir()
        parent_dir.chmod(0o444)  # Read-only
        
        restricted_dir = parent_dir / "cannot_create"
        
        try:
            # Should raise SubprocessError wrapping the OSError/PermissionError
            with pytest.raises(SubprocessError, match="Failed to create directory"):
                create_directory(restricted_dir)
        finally:
            # Restore permissions for cleanup
            parent_dir.chmod(0o755)


class TestShellSafetyFeatures:
    """Test shell injection prevention features."""
    
    @patch('flextaxd.utils.subprocess_utils.subprocess.run')
    def test_string_command_without_shell_is_split(self, mock_run):
        """Test that string commands are safely split when shell=False."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        # Command with arguments that could be dangerous if passed to shell
        command = "echo 'hello world; rm -rf /'"
        
        run_command(command, shell=False)
        
        # Command should be split into safe list
        call_args = mock_run.call_args
        cmd_args = call_args[0][0]
        
        # Should be split, not passed as dangerous shell command
        assert isinstance(cmd_args, list)
        assert cmd_args[0] == "echo"
        assert "hello world; rm -rf /" in cmd_args[1]  # Should be treated as single argument
    
    @patch('flextaxd.utils.subprocess_utils.subprocess.run')
    def test_shell_true_warning_logged(self, mock_run):
        """Test that shell=True usage is logged as warning."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        with patch('flextaxd.utils.subprocess_utils.logger') as mock_logger:
            run_command("echo test", shell=True)
            
            # Should log warning about shell=True usage
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args[0][0]
            assert "shell=True may be unsafe" in warning_call
    
    def test_list_command_bypasses_shell_parsing(self):
        """Test that list commands bypass shell parsing entirely."""
        with patch('flextaxd.utils.subprocess_utils.subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "output"
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            
            # Command as list should not be processed by shell
            command_list = ["echo", "hello; rm -rf /"]
            
            run_command(command_list)
            
            # Should be passed exactly as provided
            call_args = mock_run.call_args
            assert call_args[0][0] == command_list