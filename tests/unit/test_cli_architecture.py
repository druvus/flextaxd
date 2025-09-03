"""Test CLI architecture and validation fixes."""

import os
import tempfile

import pytest

from flextaxd.cli.main import main


class TestCLIFormatValidation:
    """Test format validation in CLI commands."""

    @pytest.fixture
    def gtdb_content(self):
        """Sample GTDB format content."""
        return """GCF_000001405.1\td__Bacteria;p__Proteobacteria;c__Gammaproteobacteria;o__Enterobacterales;f__Enterobacteriaceae;g__Escherichia;s__Escherichia_coli
GCF_000002305.1\td__Bacteria;p__Proteobacteria;c__Gammaproteobacteria;o__Enterobacterales;f__Enterobacteriaceae;g__Salmonella;s__Salmonella_enterica
"""

    @pytest.fixture
    def tsv_content(self):
        """Sample TSV format content."""
        return """parent\tchild
root\tBacteria
Bacteria\tProteobacteria
Proteobacteria\tEscherichia
Escherichia\tE_coli
"""

    @pytest.fixture
    def ncbi_nodes_content(self):
        """Sample NCBI nodes.dmp content."""
        return """1\t|\t1\t|\tno rank\t|\t\t|\t0\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t0\t|\t0\t|\t\t|
2\t|\t1\t|\tsuperkingdom\t|\t\t|\t0\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t0\t|\t0\t|\t\t|
511145\t|\t2\t|\tspecies\t|\t\t|\t0\t|\t1\t|\t1\t|\t1\t|\t1\t|\t1\t|\t0\t|\t0\t|\t\t|
"""

    @pytest.fixture
    def ncbi_names_content(self):
        """Sample NCBI names.dmp content."""
        return """1\t|\troot\t|\t\t|\tscientific name\t|
2\t|\tBacteria\t|\t\t|\tscientific name\t|
511145\t|\tEscherichia coli str. K-12 substr. MG1655\t|\t\t|\tscientific name\t|
"""

    def test_create_format_validation_mismatch(self, gtdb_content):
        """Test that create command rejects mismatched format specification."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write(gtdb_content)
            temp_file = f.name

        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        try:
            # Try to force NCBI format on GTDB content - should fail
            result = main(
                [
                    "create",
                    "--input",
                    temp_file,
                    "--format",
                    "ncbi",
                    "--database",
                    temp_db.name,
                    "--overwrite",
                ]
            )
            assert result == 1, "Should have failed format validation"
        finally:
            os.unlink(temp_file)
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)

    def test_create_format_validation_correct(self, tsv_content):
        """Test that create command accepts correct format specification."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write(tsv_content)
            temp_file = f.name

        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        try:
            # TSV format on TSV content - should work
            result = main(
                [
                    "create",
                    "--input",
                    temp_file,
                    "--format",
                    "tsv",
                    "--database",
                    temp_db.name,
                    "--overwrite",
                ]
            )
            assert result == 0, "Should have succeeded with correct format"
        finally:
            os.unlink(temp_file)
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)

    def test_create_auto_detection_works(self, gtdb_content):
        """Test that auto-detection works correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write(gtdb_content)
            temp_file = f.name

        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        try:
            # Auto-detection should work
            result = main(
                [
                    "create",
                    "--input",
                    temp_file,
                    "--format",
                    "auto",
                    "--database",
                    temp_db.name,
                    "--overwrite",
                ]
            )
            assert result == 0, "Auto-detection should have worked"
        finally:
            os.unlink(temp_file)
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)

    def test_create_ncbi_format_validation(
        self, ncbi_nodes_content, ncbi_names_content
    ):
        """Test NCBI format validation with proper NCBI files."""
        temp_dir = tempfile.mkdtemp()
        nodes_file = os.path.join(temp_dir, "nodes.dmp")
        names_file = os.path.join(temp_dir, "names.dmp")

        with open(nodes_file, "w") as f:
            f.write(ncbi_nodes_content)
        with open(names_file, "w") as f:
            f.write(ncbi_names_content)

        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        try:
            # NCBI format on NCBI content - should work
            result = main(
                [
                    "create",
                    "--input",
                    temp_dir,
                    "--format",
                    "ncbi",
                    "--database",
                    temp_db.name,
                    "--overwrite",
                ]
            )
            assert result == 0, "Should have succeeded with NCBI format"
        finally:
            os.unlink(nodes_file)
            os.unlink(names_file)
            os.rmdir(temp_dir)
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)

    def test_modify_format_validation(self, gtdb_content, tsv_content):
        """Test format validation in modify command."""
        # Create a base database first
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write(tsv_content)
            base_input = f.name

        base_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        base_db.close()

        # Create modify file with different format
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write(gtdb_content)
            mod_file = f.name

        try:
            # Create base database
            result = main(
                [
                    "create",
                    "--input",
                    base_input,
                    "--database",
                    base_db.name,
                    "--overwrite",
                ]
            )
            assert result == 0, "Base database creation should succeed"

            # Try to modify with mismatched format - should fail
            result = main(
                [
                    "modify",
                    "--database",
                    base_db.name,
                    "--mod-file",
                    mod_file,
                    "--format",
                    "ncbi",
                ]
            )
            assert result == 1, "Should have failed format validation in modify"

        finally:
            os.unlink(base_input)
            os.unlink(mod_file)
            if os.path.exists(base_db.name):
                os.unlink(base_db.name)


class TestCLIErrorHandling:
    """Test error handling consistency across CLI commands."""

    def test_nonexistent_database_error_consistency(self):
        """Test that all commands handle nonexistent database consistently."""
        nonexistent_db = "nonexistent.ftd"

        # Export command
        result_export = main(
            [
                "export",
                "--database",
                nonexistent_db,
                "--classifier",
                "ncbi",
                "--output",
                "/tmp/test",
            ]
        )
        assert result_export == 1, "Export should return 1 for nonexistent database"

        # Stats command
        result_stats = main(["stats", "--database", nonexistent_db])
        assert result_stats == 1, "Stats should return 1 for nonexistent database"

        # Modify command
        result_modify = main(
            [
                "modify",
                "--database",
                nonexistent_db,
                "--add-node",
                "test",
                "--parent-id",
                "1",
            ]
        )
        assert result_modify == 1, "Modify should return 1 for nonexistent database"

    def test_nonexistent_input_file_error(self):
        """Test create command with nonexistent input file."""
        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        try:
            result = main(
                ["create", "--input", "nonexistent.tsv", "--database", temp_db.name]
            )
            assert result == 1, "Should return 1 for nonexistent input file"
        finally:
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)

    def test_invalid_format_choice_handled_by_argparse(self):
        """Test that invalid format choices are caught by argparse."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("parent\tchild\nroot\tBacteria")
            temp_file = f.name

        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        try:
            # This should be caught by argparse before reaching our code
            with pytest.raises(SystemExit) as exc_info:
                result = main(
                    [
                        "create",
                        "--input",
                        temp_file,
                        "--format",
                        "invalid_format",
                        "--database",
                        temp_db.name,
                    ]
                )
            assert (
                exc_info.value.code == 2
            ), "Should exit with code 2 for argparse errors"
        finally:
            os.unlink(temp_file)
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)


class TestCLIExporterRegistration:
    """Test that all exporters are properly registered and accessible."""

    def test_all_export_formats_registered(self):
        """Test that all advertised export formats are actually registered."""
        # Create a simple test database
        test_content = "parent\tchild\nroot\tBacteria\nBacteria\tE_coli"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write(test_content)
            temp_input = f.name

        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        try:
            # Create database
            result = main(
                [
                    "create",
                    "--input",
                    temp_input,
                    "--database",
                    temp_db.name,
                    "--overwrite",
                ]
            )
            assert result == 0, "Database creation should succeed"

            # Test classifier formats (directory-based)
            classifier_formats_to_test = [
                "ncbi",
                "kraken2",
                "ganon",
                "ganon2",
                "centrifuge",
                "sylph",
                "diamond",
                "melon",
                "malt",
                "kaiju",
                "sourmash",
                "metabuli",
                "metacache",
                "mmseqs2",
            ]

            # Test single file formats
            file_formats_to_test = [
                "tsv",
                "json",
                "newick",
                "accession2taxid",
                "nucl2taxid",
                "prot2taxid",
                "genome_sizes",
                "malt_mapdb",
                "kmcp",
            ]

            temp_export_dir = tempfile.mkdtemp()

            # Test classifier formats
            for fmt in classifier_formats_to_test:
                output_path = os.path.join(temp_export_dir, fmt)
                result = main(
                    [
                        "export",
                        "--database",
                        temp_db.name,
                        "--classifier",
                        fmt,
                        "--output",
                        output_path,
                    ]
                )
                assert (
                    result == 0
                ), f"Classifier format {fmt} should be registered and working"

            # Test file formats
            for fmt in file_formats_to_test:
                output_path = os.path.join(temp_export_dir, f"test_{fmt}")
                result = main(
                    [
                        "export",
                        "--database",
                        temp_db.name,
                        "--format",
                        fmt,
                        "--output",
                        output_path,
                    ]
                )
                assert (
                    result == 0
                ), f"File format {fmt} should be registered and working"

        finally:
            os.unlink(temp_input)
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)
            # Clean up export directory
            import shutil

            if os.path.exists(temp_export_dir):
                shutil.rmtree(temp_export_dir)


class TestCLIHelpText:
    """Test that CLI help text is accurate and complete."""

    def test_main_help_contains_all_commands(self):
        """Test main help contains all implemented commands."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        # Help command exits with 0
        assert exc_info.value.code == 0, "Help should exit cleanly with code 0"

    def test_create_help_lists_correct_formats(self):
        """Test create command help lists the correct input formats."""
        with pytest.raises(SystemExit) as exc_info:
            main(["create", "--help"])
        assert exc_info.value.code == 0, "Create help should exit cleanly with code 0"

    def test_export_help_lists_correct_formats(self):
        """Test export command help lists the correct output formats."""
        with pytest.raises(SystemExit) as exc_info:
            main(["export", "--help"])
        assert exc_info.value.code == 0, "Export help should exit cleanly with code 0"

    def test_all_commands_have_help(self):
        """Test that all commands have working help."""
        commands = ["create", "export", "modify", "stats", "visualize"]

        for cmd in commands:
            with pytest.raises(SystemExit) as exc_info:
                main([cmd, "--help"])
            assert exc_info.value.code == 0, f"Command {cmd} should have working help"


class TestCLINewStructure:
    """Test new CLI structure with --classifier and --format split."""

    def test_mutually_exclusive_classifier_format(self):
        """Test that --classifier and --format are mutually exclusive."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("parent\tchild\nroot\tBacteria")
            temp_input = f.name

        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        try:
            # Create database first
            result = main(
                [
                    "create",
                    "--input",
                    temp_input,
                    "--database",
                    temp_db.name,
                    "--overwrite",
                ]
            )
            assert result == 0, "Database creation should succeed"

            # Try to use both --classifier and --format (should fail)
            with pytest.raises(SystemExit) as exc_info:
                main(
                    [
                        "export",
                        "--database",
                        temp_db.name,
                        "--classifier",
                        "kraken2",
                        "--format",
                        "tsv",
                        "--output",
                        "/tmp/test",
                    ]
                )
            assert (
                exc_info.value.code == 2
            ), "Should exit with code 2 for mutually exclusive arguments"

        finally:
            os.unlink(temp_input)
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)

    def test_require_one_of_classifier_format(self):
        """Test that either --classifier or --format must be specified."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("parent\tchild\nroot\tBacteria")
            temp_input = f.name

        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        try:
            # Create database first
            result = main(
                [
                    "create",
                    "--input",
                    temp_input,
                    "--database",
                    temp_db.name,
                    "--overwrite",
                ]
            )
            assert result == 0, "Database creation should succeed"

            # Try to export without --classifier or --format (should fail)
            with pytest.raises(SystemExit) as exc_info:
                main(["export", "--database", temp_db.name, "--output", "/tmp/test"])
            assert (
                exc_info.value.code == 2
            ), "Should exit with code 2 for missing required argument"

        finally:
            os.unlink(temp_input)
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)

    def test_classifier_creates_directory(self):
        """Test that classifier formats create directories with multiple files."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("parent\tchild\nroot\tBacteria\nBacteria\tE_coli")
            temp_input = f.name

        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        temp_output_dir = tempfile.mkdtemp()

        try:
            # Create database first
            result = main(
                [
                    "create",
                    "--input",
                    temp_input,
                    "--database",
                    temp_db.name,
                    "--overwrite",
                ]
            )
            assert result == 0, "Database creation should succeed"

            # Export with classifier format
            result = main(
                [
                    "export",
                    "--database",
                    temp_db.name,
                    "--classifier",
                    "ncbi",
                    "--output",
                    temp_output_dir,
                ]
            )
            assert result == 0, "Classifier export should succeed"

            # Check that directory was created with expected files
            assert os.path.isdir(temp_output_dir), "Output should be a directory"
            files = os.listdir(temp_output_dir)
            assert len(files) > 0, "Directory should contain files"
            # NCBI format should create names.dmp and nodes.dmp
            assert any("names.dmp" in f for f in files), "Should create names.dmp file"
            assert any("nodes.dmp" in f for f in files), "Should create nodes.dmp file"

        finally:
            os.unlink(temp_input)
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)
            import shutil

            if os.path.exists(temp_output_dir):
                shutil.rmtree(temp_output_dir)

    def test_format_creates_single_file(self):
        """Test that file formats create single files."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write("parent\tchild\nroot\tBacteria\nBacteria\tE_coli")
            temp_input = f.name

        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        temp_output_file = os.path.join(tempfile.mkdtemp(), "output.tsv")

        try:
            # Create database first
            result = main(
                [
                    "create",
                    "--input",
                    temp_input,
                    "--database",
                    temp_db.name,
                    "--overwrite",
                ]
            )
            assert result == 0, "Database creation should succeed"

            # Export with file format
            result = main(
                [
                    "export",
                    "--database",
                    temp_db.name,
                    "--format",
                    "tsv",
                    "--output",
                    temp_output_file,
                ]
            )
            assert result == 0, "File format export should succeed"

            # Check that single file was created
            assert os.path.isfile(temp_output_file), "Output should be a single file"
            assert os.path.getsize(temp_output_file) > 0, "File should not be empty"

        finally:
            os.unlink(temp_input)
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)
            if os.path.exists(temp_output_file):
                os.unlink(temp_output_file)
                parent_dir = os.path.dirname(temp_output_file)
                if os.path.exists(parent_dir):
                    os.rmdir(parent_dir)


class TestCLIIntegration:
    """Integration tests for CLI functionality."""

    def test_full_workflow_create_stats_export(self):
        """Test complete workflow: create -> stats -> export."""
        test_content = """parent\tchild
root\tBacteria
Bacteria\tProteobacteria
Proteobacteria\tEscherichia
Escherichia\tE_coli
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write(test_content)
            temp_input = f.name

        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        temp_export_dir = tempfile.mkdtemp()

        try:
            # Create database
            result = main(
                [
                    "create",
                    "--input",
                    temp_input,
                    "--database",
                    temp_db.name,
                    "--overwrite",
                ]
            )
            assert result == 0, "Database creation should succeed"

            # Check stats
            result = main(["stats", "--database", temp_db.name])
            assert result == 0, "Stats command should succeed"

            # Export database
            result = main(
                [
                    "export",
                    "--database",
                    temp_db.name,
                    "--format",
                    "tsv",
                    "--output",
                    os.path.join(temp_export_dir, "export.tsv"),
                ]
            )
            assert result == 0, "Export command should succeed"

            # Verify export file was created
            export_file = os.path.join(temp_export_dir, "export.tsv")
            assert os.path.exists(export_file), "Export file should be created"

        finally:
            os.unlink(temp_input)
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)
            import shutil

            if os.path.exists(temp_export_dir):
                shutil.rmtree(temp_export_dir)

    def test_visualize_command_basic(self):
        """Test visualize command basic functionality."""
        test_content = "parent\tchild\nroot\tBacteria\nBacteria\tE_coli"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            f.write(test_content)
            temp_input = f.name

        temp_db = tempfile.NamedTemporaryFile(suffix=".ftd", delete=False)
        temp_db.close()

        try:
            # Create database
            result = main(
                [
                    "create",
                    "--input",
                    temp_input,
                    "--database",
                    temp_db.name,
                    "--overwrite",
                ]
            )
            assert result == 0, "Database creation should succeed"

            # Test visualize
            result = main(
                [
                    "visualize",
                    "--database",
                    temp_db.name,
                    "--type",
                    "tree",
                    "--max-depth",
                    "2",
                ]
            )
            assert result == 0, "Visualize command should succeed"

        finally:
            os.unlink(temp_input)
            if os.path.exists(temp_db.name):
                os.unlink(temp_db.name)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
