"""Integration tests for the new modular CLI."""

import pytest
import subprocess
import sys
import tempfile
from pathlib import Path


class TestNewCLI:
    """Test the new modular CLI system."""

    def test_cli_help(self):
        """Test that CLI help works."""
        result = subprocess.run(
            [sys.executable, "-m", "flextaxd.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "Flexible modification of taxonomy databases" in result.stdout
        assert "create" in result.stdout
        assert "export" in result.stdout
        assert "stats" in result.stdout
        # Check for new focused commands instead of modify
        assert "add-node" in result.stdout
        assert "import-tree" in result.stdout
        assert "add-genome" in result.stdout

    def test_cli_version(self):
        """Test version display."""
        result = subprocess.run(
            [sys.executable, "-m", "flextaxd.cli", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "0.5.0" in result.stdout

    def test_create_command_help(self):
        """Test create command help."""
        result = subprocess.run(
            [sys.executable, "-m", "flextaxd.cli", "create", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "Create taxonomy database from various input sources" in result.stdout

    def test_add_node_command_help(self):
        """Test add-node command help."""
        result = subprocess.run(
            [sys.executable, "-m", "flextaxd.cli", "add-node", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "Add a new taxonomy node" in result.stdout
        assert "--name" in result.stdout
        assert "--parent-id" in result.stdout
        assert "--parent-name" in result.stdout

    def test_import_tree_command_help(self):
        """Test import-tree command help."""
        result = subprocess.run(
            [sys.executable, "-m", "flextaxd.cli", "import-tree", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "Import a taxonomy tree from a file" in result.stdout
        assert "--strategy" in result.stdout
        assert "--attach-to" in result.stdout
        assert "--root-node" in result.stdout

    def test_add_genome_command_help(self):
        """Test add-genome command help."""
        result = subprocess.run(
            [sys.executable, "-m", "flextaxd.cli", "add-genome", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "Add genome to taxonomy node" in result.stdout
        assert "--genome-id" in result.stdout
        assert "--tax-id" in result.stdout
        assert "--tax-name" in result.stdout
        assert "--file-path" in result.stdout
        assert "--database" in result.stdout
        assert "--assembly-accession" in result.stdout

    def test_stats_command_help(self):
        """Test stats command help."""
        result = subprocess.run(
            [sys.executable, "-m", "flextaxd.cli", "stats", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "Display detailed statistics about a taxonomy database" in result.stdout
        assert "--database" in result.stdout
        assert "--detailed" in result.stdout

    def test_export_command_help(self):
        """Test export command help."""
        result = subprocess.run(
            [sys.executable, "-m", "flextaxd.cli", "export", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert (
            "Export a taxonomy database to classifier tools" 
            in result.stdout
        )
        assert "--format" in result.stdout
        assert "--output" in result.stdout

    # NOTE: modify command has been removed and replaced with focused commands:
    # add-node, import-tree, and add-genome. Tests for these are in their respective test files.

    @pytest.mark.slow
    def test_create_basic_database(self, sample_taxonomy_file):
        """Test creating a basic database with the new CLI."""
        with tempfile.NamedTemporaryFile(suffix=".ftd", delete=False) as tmp_db:
            db_path = tmp_db.name

        try:
            # Test database creation
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "flextaxd.cli",
                    "create",
                    "--input",
                    sample_taxonomy_file,
                    "--database",
                    db_path,
                    "--format",
                    "tsv",
                    "--overwrite",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}"
            assert "Created database:" in result.stdout
            assert Path(db_path).exists()
            assert Path(db_path).stat().st_size > 0

        finally:
            if Path(db_path).exists():
                Path(db_path).unlink()

    @pytest.mark.slow
    def test_stats_command_with_database(self, temp_database):
        """Test stats command with actual database."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "flextaxd.cli",
                "stats",
                "--database",
                temp_database,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "Taxonomy Database Statistics" in result.stdout
        assert "Total nodes:" in result.stdout

    def test_error_handling_missing_database(self):
        """Test error handling when database is missing."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "flextaxd.cli",
                "stats",
                "--database",
                "/nonexistent/database.ftd",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 1
        assert "ERROR:" in result.stderr

    def test_verbose_logging(self, temp_database):
        """Test verbose logging output."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "flextaxd.cli",
                "--verbose",
                "--verbose",
                "stats",
                "--database",
                temp_database,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        # With debug logging, we should see more detailed output
        # The exact output depends on the logging configuration
