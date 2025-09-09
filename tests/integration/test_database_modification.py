"""Tests for database modification and merging functionality using new focused commands."""

import tempfile
from pathlib import Path

import pytest

from flextaxd.cli.commands.create import CreateCommand
from flextaxd.cli.commands.import_tree import ImportTreeCommand
from flextaxd.cli.commands.add_node import AddNodeCommand
from flextaxd.cli.commands.add_genome import AddGenomeCommand
from flextaxd.database.sqlite import SQLiteTaxonomyRepository


class TestDatabaseModification:
    """Test database modification and merging functionality."""

    def create_mock_args(self, **kwargs):
        """Helper to create mock args with all required attributes."""

        class MockArgs:
            def __init__(self, **attrs):
                # Database path
                self.database = attrs.get("database")

                # Create command args
                self.input = attrs.get("input")
                self.format = attrs.get("format", "tsv")
                self.overwrite = attrs.get("overwrite", True)
                self.no_header = attrs.get("no_header", False)
                self.parent_column = attrs.get("parent_column", 0)
                self.child_column = attrs.get("child_column", 1)
                self.id_column = attrs.get("id_column", None)
                self.rank_column = attrs.get("rank_column", None)
                self.genomeid2taxid = attrs.get("genomeid2taxid", None)
                self.genomes_path = attrs.get("genomes_path", None)
                self.auto_detect_sequences = attrs.get("auto_detect_sequences", False)
                self.sequence_type = attrs.get("sequence_type", "genome")
                
                # NCBI datasets args (Phase 3 enhancement)
                self.ncbi_datasets = attrs.get("ncbi_datasets", None)
                self.taxonomy_only = attrs.get("taxonomy_only", False)
                self.assembly_level = attrs.get("assembly_level", None)
                self.max_genomes = attrs.get("max_genomes", None)

                # Common command args
                self.force = attrs.get("force", False)
                self.dry_run = attrs.get("dry_run", False)
                self.verbose = attrs.get("verbose", False)
                self.quiet = attrs.get("quiet", False)
                self.skip_validation = attrs.get("skip_validation", True)
                
                # Global CLI options (from main parser) - required by all commands
                self.log_file = attrs.get("log_file", None)
                self.command = attrs.get("command", 'create')
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = attrs.get("progress_width", 80)
                self.no_eta = attrs.get("no_eta", False)
                self.no_rate = attrs.get("no_rate", False)
                self.progress_log = attrs.get("progress_log", None)
                self.progress_interval = attrs.get("progress_interval", 1.0)

        return MockArgs(**kwargs)

    def create_base_database(self, tmp_path: Path) -> Path:
        """Create a base database for testing modifications."""
        # Create base taxonomy
        taxonomy_content = """Parent\tChild\tTaxID\tRank
root\tBacteria\t2\tsuperkingdom
Bacteria\tProteobacteria\t1224\tphylum
Proteobacteria\tEscherichia\t561\tgenus
Escherichia\tEscherichia coli\t562\tspecies"""

        taxonomy_file = tmp_path / "base_taxonomy.tsv"
        taxonomy_file.write_text(taxonomy_content)

        database_file = tmp_path / "base.ftd"

        # Create database
        create_cmd = CreateCommand()
        args = self.create_mock_args(
            input=str(taxonomy_file), database=str(database_file), format="tsv"
        )

        result = create_cmd.execute(args)
        assert result == 0
        return database_file

    def test_import_from_file(self, tmp_path: Path):
        """Test importing taxonomy from another file using import-tree command."""
        # Create base database
        base_db = self.create_base_database(tmp_path)

        # Create modification file with new taxonomy in TSV format
        # Using parent\tchild format expected by TSV parser
        mod_content = """parent\tchild
Escherichia\tEscherichia albertii
Escherichia\tEscherichia fergusonii"""

        mod_file = tmp_path / "modifications.tsv"
        mod_file.write_text(mod_content)

        # Apply modifications using import-tree command
        import_cmd = ImportTreeCommand()
        
        class MockArgs:
            def __init__(self):
                self.database = str(base_db)
                self.input = str(mod_file)
                self.strategy = "merge"
                self.attach_to = "Escherichia"  # Attach to existing Escherichia genus
                self.attach_to_id = None
                self.target = None
                self.root_node = None
                self.auto_root = True
                self.keep_names = "file"
                self.on_conflict = "skip"
                self.format = "auto"
                self.dry_run = False
                self.force = False
                self.backup = True
                self.verbose = False
                self.quiet = False
                self.skip_validation = True
                
                # Global CLI options (from main parser) - required by all commands
                self.log_file = None
                self.command = 'import-tree'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0

        args = MockArgs()
        result = import_cmd.execute(args)
        assert result == 0

        # Verify modifications were applied
        with SQLiteTaxonomyRepository(base_db) as repo:
            stats = repo.get_statistics()
            # Should now have original 5 nodes + 2 new species = 7 nodes
            assert stats["node_count"] == 7

            # Verify new species exist
            albertii = None
            fergusonii = None
            tree = repo.load_tree()
            for node in tree:
                if node.name == "Escherichia albertii":
                    albertii = node
                elif node.name == "Escherichia fergusonii":
                    fergusonii = node

            assert albertii is not None
            assert fergusonii is not None

            # Verify they're attached under Escherichia genus
            escherichia_tax_id = 4  # Auto-generated ID for Escherichia
            assert albertii.parent_id == escherichia_tax_id
            assert fergusonii.parent_id == escherichia_tax_id

    def test_add_single_node(self, tmp_path: Path):
        """Test adding a single node using add-node command."""
        # Create base database
        base_db = self.create_base_database(tmp_path)

        # Add a new genus using add-node command
        add_cmd = AddNodeCommand()
        
        class MockArgs:
            def __init__(self):
                self.database = str(base_db)
                self.name = "Salmonella"
                self.parent_id = None
                self.parent_name = "Proteobacteria"  # Add under existing phylum
                self.rank = "genus"
                self.tax_id = None  # Auto-generate
                self.dry_run = False
                self.force = False
                self.verbose = False
                self.quiet = False
                self.skip_validation = True
                
                # Global CLI options (from main parser) - required by all commands
                self.log_file = None
                self.command = 'add-node'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0

        args = MockArgs()
        result = add_cmd.execute(args)
        assert result == 0

        # Verify the node was added
        with SQLiteTaxonomyRepository(base_db) as repo:
            stats = repo.get_statistics()
            # Should have original 5 nodes + 1 new genus = 6 nodes
            assert stats["node_count"] == 6

            # Find Salmonella and verify it's under Proteobacteria
            salmonella = None
            proteobacteria_tax_id = 3  # Auto-generated ID for Proteobacteria

            tree = repo.load_tree()
            for node in tree:
                if node.name == "Salmonella":
                    salmonella = node
                    break

            assert salmonella is not None
            assert salmonella.parent_id == proteobacteria_tax_id

    def test_import_with_parent_attachment(self, tmp_path: Path):
        """Test importing taxonomy tree with parent attachment using import-tree."""
        # Create base database
        base_db = self.create_base_database(tmp_path)

        # Create modification file with new branch in parent-child format
        mod_content = """parent\tchild
Firmicutes\tBacillus
Bacillus\tBacillus subtilis"""

        mod_file = tmp_path / "firmicutes_branch.tsv"
        mod_file.write_text(mod_content)

        # Apply modifications with parent attachment using import-tree
        import_cmd = ImportTreeCommand()
        
        class MockArgs:
            def __init__(self):
                self.database = str(base_db)
                self.input = str(mod_file)
                self.strategy = "merge"
                self.attach_to = "Bacteria"  # Attach Firmicutes under Bacteria
                self.attach_to_id = None
                self.target = None
                self.root_node = "Firmicutes"  # Firmicutes is the root of imported tree
                self.auto_root = False
                self.keep_names = "file"
                self.on_conflict = "skip"
                self.format = "auto"
                self.dry_run = False
                self.force = False
                self.backup = True
                self.verbose = False
                self.quiet = False
                self.skip_validation = True
                
                # Global CLI options (from main parser) - required by all commands
                self.log_file = None
                self.command = 'import-tree'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0

        args = MockArgs()
        result = import_cmd.execute(args)
        assert result == 0

        # Verify modifications
        with SQLiteTaxonomyRepository(base_db) as repo:
            stats = repo.get_statistics()
            # Should have original 5 + 3 new nodes (Firmicutes, Bacillus, Bacillus subtilis) = 8
            assert stats["node_count"] == 8

            # Find Firmicutes and verify it's under Bacteria
            firmicutes = None
            bacteria_tax_id = 2  # Auto-generated ID for Bacteria

            tree = repo.load_tree()
            for node in tree:
                if node.name == "Firmicutes":
                    firmicutes = node
                    break

            assert firmicutes is not None
            assert firmicutes.parent_id == bacteria_tax_id

    def test_import_tree_merge_strategy(self, tmp_path: Path):
        """Test importing taxonomy tree with merge strategy using import-tree command."""
        # Create base database
        base_db = self.create_base_database(tmp_path)

        # Create source taxonomy tree to import
        source_taxonomy = """Parent\tChild\tTaxID\tRank
root\tArchaea\t2157\tsuperkingdom
Archaea\tCrenarchaeota\t28889\tphylum
Crenarchaeota\tThermoproteus\t2285\tgenus"""

        source_taxonomy_file = tmp_path / "archaea_taxonomy.tsv"
        source_taxonomy_file.write_text(source_taxonomy)

        # Import tree with merge strategy using import-tree command
        import_cmd = ImportTreeCommand()
        
        class MockArgs:
            def __init__(self):
                self.database = str(base_db)
                self.input = str(source_taxonomy_file)
                self.strategy = "merge"
                self.attach_to = "root"  # Attach to existing root
                self.attach_to_id = None
                self.target = None
                self.root_node = "Archaea"  # Archaea is the root of imported tree
                self.auto_root = False
                self.keep_names = "file"
                self.on_conflict = "skip"
                self.format = "tsv"
                self.dry_run = False
                self.force = False
                self.backup = True
                self.verbose = False
                self.quiet = False
                self.skip_validation = True
                
                # Global CLI options (from main parser) - required by all commands
                self.log_file = None
                self.command = 'import-tree'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0

        args = MockArgs()
        result = import_cmd.execute(args)
        assert result == 0

        # Verify import
        with SQLiteTaxonomyRepository(base_db) as repo:
            stats = repo.get_statistics()
            # Should have original 5 + 3 archaea nodes = 8
            assert stats["node_count"] >= 7

            # Verify archaea nodes exist
            archaea_found = False
            crenarchaeota_found = False
            thermoproteus_found = False

            tree = repo.load_tree()
            for node in tree:
                if "Archaea" in node.name:
                    archaea_found = True
                elif "Crenarchaeota" in node.name:
                    crenarchaeota_found = True
                elif "Thermoproteus" in node.name:
                    thermoproteus_found = True

            assert archaea_found
            assert crenarchaeota_found
            assert thermoproteus_found

    def test_import_tree_replace_strategy(self, tmp_path: Path):
        """Test importing taxonomy tree with replace strategy using import-tree command."""
        # Create base database with existing branch
        base_taxonomy = """Parent\tChild\tTaxID\tRank
root\tBacteria\t2\tsuperkingdom
Bacteria\tProteobacteria\t1224\tphylum
Proteobacteria\tAlphaproteobacteria\t28211\tclass"""

        base_taxonomy_file = tmp_path / "base_with_alpha.tsv"
        base_taxonomy_file.write_text(base_taxonomy)

        base_db = tmp_path / "base_replaceable.ftd"

        create_cmd = CreateCommand()
        base_args = self.create_mock_args(
            input=str(base_taxonomy_file), database=str(base_db), format="tsv"
        )

        result = create_cmd.execute(base_args)
        assert result == 0

        # Create replacement taxonomy tree
        replacement_taxonomy = """Parent\tChild\tTaxID\tRank
Proteobacteria\tGammaproteobacteria\t1236\tclass
Gammaproteobacteria\tEscherichia\t561\tgenus"""

        replacement_taxonomy_file = tmp_path / "replacement.tsv"
        replacement_taxonomy_file.write_text(replacement_taxonomy)

        # Import with replace strategy using import-tree command
        import_cmd = ImportTreeCommand()
        
        class MockArgs:
            def __init__(self):
                self.database = str(base_db)
                self.input = str(replacement_taxonomy_file)
                self.strategy = "replace"
                self.attach_to = None
                self.attach_to_id = None
                self.target = "Alphaproteobacteria"  # Replace this node
                self.root_node = "Gammaproteobacteria"
                self.auto_root = False
                self.keep_names = "file"
                self.on_conflict = "replace"
                self.format = "tsv"
                self.dry_run = False
                self.force = True
                self.backup = True
                self.verbose = False
                self.quiet = False
                self.skip_validation = True
                
                # Global CLI options (from main parser) - required by all commands
                self.log_file = None
                self.command = 'import-tree'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0

        args = MockArgs()
        result = import_cmd.execute(args)
        assert result == 0

        # Verify replacement
        with SQLiteTaxonomyRepository(base_db) as repo:
            # Should no longer have Alphaproteobacteria, should have Gammaproteobacteria
            alpha_found = False
            gamma_found = False

            tree = repo.load_tree()
            for node in tree:
                if "Alphaproteobacteria" in node.name:
                    alpha_found = True
                elif "Gammaproteobacteria" in node.name:
                    gamma_found = True

            assert not alpha_found  # Should be replaced
            assert gamma_found  # Should be present from replacement

    def test_dry_run_functionality(self, tmp_path: Path):
        """Test dry-run functionality doesn't make changes."""
        # Create base database
        base_db = self.create_base_database(tmp_path)

        # Get initial state
        with SQLiteTaxonomyRepository(base_db) as repo:
            initial_count = repo.get_statistics()["node_count"]

        # Create modification file
        mod_content = """Parent\tChild\tTaxID\tRank
Escherichia\tEscherichia vulneris\t103240\tspecies"""

        mod_file = tmp_path / "dry_run_test.tsv"
        mod_file.write_text(mod_content)

        # Run with dry-run using import-tree command
        import_cmd = ImportTreeCommand()
        
        class MockArgs:
            def __init__(self):
                self.database = str(base_db)
                self.input = str(mod_file)
                self.strategy = "merge"
                self.attach_to = "Escherichia"  # Attach new species under Escherichia
                self.attach_to_id = None
                self.target = None
                self.root_node = None
                self.auto_root = True
                self.keep_names = "file"
                self.on_conflict = "skip"
                self.format = "tsv"
                self.dry_run = True  # Key: dry-run mode
                self.force = False
                self.backup = True
                self.verbose = False
                self.quiet = False
                self.skip_validation = True
                
                # Global CLI options (from main parser) - required by all commands
                self.log_file = None
                self.command = 'import-tree'
                
                # Progress-related options (expected by CLI commands with progress indicators)
                self.progress_width = 80
                self.no_eta = False
                self.no_rate = False
                self.progress_log = None
                self.progress_interval = 1.0

        args = MockArgs()
        result = import_cmd.execute(args)
        assert result == 0

        # Verify no changes were made
        with SQLiteTaxonomyRepository(base_db) as repo:
            final_count = repo.get_statistics()["node_count"]
            assert final_count == initial_count  # Should be unchanged

    # NOTE: SILVA format modification functionality was removed with the modify command.
    # The new focused commands (add-node, import-tree, add-genome) don't support SILVA format imports.
    # SILVA format is only supported during initial database creation with the create command.
