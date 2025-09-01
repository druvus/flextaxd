"""Integration tests for CLI functionality."""

import pytest
import tempfile
import os
import subprocess
import sys
from pathlib import Path


class TestCLIIntegration:
    """Test command-line interface integration."""
    
    def test_flextaxd_help_command(self):
        """Test that flextaxd --help works."""
        result = subprocess.run(
            [sys.executable, "-m", "flextaxd.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower()
        assert "flextaxd" in result.stdout.lower()
    
    def test_flextaxd_version_info(self):
        """Test that version information is accessible."""
        # Try to import and check version
        result = subprocess.run([
            sys.executable, "-c", 
            "import flextaxd; print(flextaxd.__version__)"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert result.stdout.strip() == "0.8.0"
    
    @pytest.mark.slow
    def test_basic_database_creation(self, sample_taxonomy_file: str):
        """Test basic database creation from taxonomy file."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as tmp_db:
            db_path = tmp_db.name
        
        try:
            # Test database creation using new CLI
            result = subprocess.run([
                sys.executable, "-m", "flextaxd",
                "create",
                "--input", sample_taxonomy_file,
                "--database", db_path,
                "--format", "tsv",
                "--overwrite"
            ], capture_output=True, text=True, timeout=60)
            
            # Check that command completed successfully
            assert result.returncode == 0, f"Command failed: {result.stderr}"
            
            # Check that database file was created
            assert os.path.exists(db_path), "Database file was not created"
            assert os.path.getsize(db_path) > 0, "Database file is empty"
            
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    @pytest.mark.slow
    def test_database_stats_command(self, temp_database: str):
        """Test database statistics command."""
        result = subprocess.run([
            sys.executable, "-m", "flextaxd",
            "stats",
            "--database", temp_database
        ], capture_output=True, text=True, timeout=30)
        
        assert result.returncode == 0, f"Stats command failed: {result.stderr}"
        # Should contain some statistics output
        assert len(result.stdout) > 0, "No statistics output produced"