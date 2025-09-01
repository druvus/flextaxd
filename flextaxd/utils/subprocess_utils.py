"""Secure subprocess utilities to replace os.system() calls."""

import subprocess
import shlex
import logging
from typing import List, Optional, Dict, Any, Union
from pathlib import Path

from ..core.exceptions import FlexTaxDError

logger = logging.getLogger(__name__)


class SubprocessError(FlexTaxDError):
    """Exception raised when subprocess operations fail."""
    pass


def run_command(
    command: Union[str, List[str]],
    cwd: Optional[Path] = None,
    timeout: Optional[int] = None,
    check: bool = True,
    capture_output: bool = True,
    shell: bool = False,
    env: Optional[Dict[str, str]] = None,
    **kwargs: Any
) -> subprocess.CompletedProcess[bytes]:
    """
    Run a command securely without shell injection vulnerabilities.
    
    Args:
        command: Command to run (string or list of arguments)
        cwd: Working directory for the command
        timeout: Timeout in seconds
        check: Whether to raise exception on non-zero exit
        capture_output: Whether to capture stdout/stderr
        shell: Whether to use shell (discouraged)
        env: Environment variables
        **kwargs: Additional arguments to subprocess.run
    
    Returns:
        CompletedProcess instance
    
    Raises:
        SubprocessError: If command fails or times out
    """
    # Convert string command to list for security
    cmd_args: Union[str, List[str]]
    if isinstance(command, str):
        if shell:
            # If shell=True is explicitly requested, keep as string
            # but log a warning
            logger.warning("Using shell=True may be unsafe with untrusted input")
            cmd_args = command
        else:
            # Parse safely without shell
            cmd_args = shlex.split(command)
    else:
        cmd_args = command
    
    # Prepare arguments
    run_args = {
        'cwd': cwd,
        'timeout': timeout,
        'check': check,
        'shell': shell,
        'env': env,
        **kwargs
    }
    
    if capture_output:
        run_args.update({
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'text': True
        })
    
    # Remove None values
    run_args = {k: v for k, v in run_args.items() if v is not None}
    
    logger.debug(f"Running command: {cmd_args}")
    if cwd:
        logger.debug(f"Working directory: {cwd}")
    
    try:
        result = subprocess.run(cmd_args, **run_args)
        
        if capture_output:
            if result.stdout:
                logger.debug(f"Command stdout: {result.stdout[:500]}...")
            if result.stderr:
                logger.debug(f"Command stderr: {result.stderr[:500]}...")
        
        logger.debug(f"Command completed with return code: {result.returncode}")
        return result
        
    except subprocess.TimeoutExpired as e:
        raise SubprocessError(f"Command timed out after {timeout} seconds: {e}")
    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed with return code {e.returncode}"
        if capture_output and e.stderr:
            error_msg += f": {e.stderr}"
        raise SubprocessError(error_msg)
    except FileNotFoundError as e:
        raise SubprocessError(f"Command not found: {e}")
    except OSError as e:
        raise SubprocessError(f"Failed to run command: {e}")


def run_command_safely(command: str, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
    """
    Run a command with safe defaults (no shell, timeout, etc.).
    
    This is a convenience wrapper around run_command with security-first defaults.
    """
    # Extract known parameters and pass them explicitly
    cwd = kwargs.get('cwd')
    timeout = kwargs.get('timeout', 300)  # 5 minute default timeout
    check = kwargs.get('check', True)
    capture_output = kwargs.get('capture_output', True)
    shell = kwargs.get('shell', False)
    env = kwargs.get('env')
    
    # Pass remaining kwargs
    remaining_kwargs = {k: v for k, v in kwargs.items() 
                       if k not in {'cwd', 'timeout', 'check', 'capture_output', 'shell', 'env'}}
    
    return run_command(command, cwd=cwd, timeout=timeout, check=check, 
                      capture_output=capture_output, shell=shell, env=env, **remaining_kwargs)


def create_directory(path: Path, exist_ok: bool = True) -> None:
    """
    Securely create a directory without using os.system.
    
    Args:
        path: Path to create
        exist_ok: Whether to ignore if directory already exists
    
    Raises:
        SubprocessError: If directory creation fails
    """
    try:
        path.mkdir(parents=True, exist_ok=exist_ok)
        logger.debug(f"Created directory: {path}")
    except OSError as e:
        raise SubprocessError(f"Failed to create directory {path}: {e}")


def copy_file(source: Path, destination: Path, overwrite: bool = False) -> None:
    """
    Securely copy a file without using os.system.
    
    Args:
        source: Source file path
        destination: Destination file path
        overwrite: Whether to overwrite existing file
    
    Raises:
        SubprocessError: If copy fails
    """
    import shutil
    
    try:
        if destination.exists() and not overwrite:
            raise SubprocessError(f"Destination file already exists: {destination}")
        
        # Ensure destination directory exists
        destination.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(source, destination)
        logger.debug(f"Copied file: {source} -> {destination}")
        
    except (OSError, shutil.Error) as e:
        raise SubprocessError(f"Failed to copy file {source} to {destination}: {e}")


def compress_file(file_path: Path, remove_original: bool = True) -> Path:
    """
    Compress a file using gzip without using os.system.
    
    Args:
        file_path: Path to file to compress
        remove_original: Whether to remove original file after compression
    
    Returns:
        Path to compressed file
    
    Raises:
        SubprocessError: If compression fails
    """
    import gzip
    
    compressed_path = file_path.with_suffix(file_path.suffix + '.gz')
    
    try:
        with open(file_path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb') as f_out:
                f_out.writelines(f_in)
        
        if remove_original:
            file_path.unlink()
        
        logger.debug(f"Compressed file: {file_path} -> {compressed_path}")
        return compressed_path
        
    except (OSError, IOError) as e:
        raise SubprocessError(f"Failed to compress file {file_path}: {e}")


def remove_files(pattern: str, directory: Path) -> int:
    """
    Safely remove files matching a pattern without using os.system.
    
    Args:
        pattern: Glob pattern for files to remove
        directory: Directory to search in
    
    Returns:
        Number of files removed
    
    Raises:
        SubprocessError: If removal fails
    """
    try:
        removed_count = 0
        for file_path in directory.glob(pattern):
            if file_path.is_file():
                file_path.unlink()
                removed_count += 1
                logger.debug(f"Removed file: {file_path}")
        
        logger.debug(f"Removed {removed_count} files matching pattern: {pattern}")
        return removed_count
        
    except OSError as e:
        raise SubprocessError(f"Failed to remove files with pattern {pattern}: {e}")


def validate_command_exists(command: str) -> bool:
    """
    Check if a command exists in PATH without running it.
    
    Args:
        command: Command name to check
    
    Returns:
        True if command exists, False otherwise
    """
    import shutil
    return shutil.which(command) is not None