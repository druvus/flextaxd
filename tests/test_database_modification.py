"""Tests for database modification and merging functionality."""

import tempfile
from pathlib import Path

import pytest

from flextaxd.cli.commands.create import CreateCommand
from flextaxd.cli.commands.modify import ModifyCommand
from flextaxd.database.sqlite import SQLiteTaxonomyRepository


class TestDatabaseModification:
    """Test database modification and merging functionality."""
    
    def create_mock_args(self, **kwargs):
        """Helper to create mock args with all required attributes."""
        class MockArgs:
            def __init__(self, **attrs):
                # Database path
                self.database = attrs.get('database')
                
                # Create command args
                self.input = attrs.get('input')
                self.format = attrs.get('format', 'tsv')
                self.overwrite = attrs.get('overwrite', True)
                self.no_header = attrs.get('no_header', False)
                self.parent_column = attrs.get('parent_column', 0)
                self.child_column = attrs.get('child_column', 1)
                self.id_column = attrs.get('id_column', None)
                self.rank_column = attrs.get('rank_column', None)
                self.genomeid2taxid = attrs.get('genomeid2taxid', None)
                self.genomes_path = attrs.get('genomes_path', None)
                self.auto_detect_sequences = attrs.get('auto_detect_sequences', False)
                self.sequence_type = attrs.get('sequence_type', 'genome')
                
                # Modify command args
                self.add_node = attrs.get('add_node', None)
                self.remove_node = attrs.get('remove_node', None)
                self.update_node = attrs.get('update_node', None)
                self.mod_file = attrs.get('mod_file', None)
                self.merge_database = attrs.get('merge_database', None)
                self.parent_id = attrs.get('parent_id', None)
                self.rank = attrs.get('rank', None)
                self.new_name = attrs.get('new_name', None)
                self.new_id = attrs.get('new_id', None)
                self.parent = attrs.get('parent', None)
                self.replace = attrs.get('replace', False)
                self.force = attrs.get('force', False)
                self.dry_run = attrs.get('dry_run', False)
        
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
            input=str(taxonomy_file),
            database=str(database_file),
            format='tsv'
        )
        
        result = create_cmd.execute(args)
        assert result == 0
        return database_file
    
    def test_import_from_file(self, tmp_path: Path):
        """Test importing taxonomy from another file using --mod-file."""
        # Create base database
        base_db = self.create_base_database(tmp_path)
        
        # Create modification file with new taxonomy
        # Using high IDs to avoid conflicts with auto-generated IDs (1-5)
        mod_content = """Parent\tChild\tTaxID\tRank
Escherichia\tEscherichia albertii\t1001\tspecies
Escherichia\tEscherichia fergusonii\t1002\tspecies"""
        
        mod_file = tmp_path / "modifications.tsv"
        mod_file.write_text(mod_content)
        
        # Apply modifications
        modify_cmd = ModifyCommand()
        args = self.create_mock_args(
            database=str(base_db),
            mod_file=str(mod_file),
            format='tsv'
        )
        
        result = modify_cmd.execute(args)
        assert result == 0
        
        # Verify modifications were applied
        with SQLiteTaxonomyRepository(base_db) as repo:
            stats = repo.get_statistics()
            # Should now have original 5 nodes + 2 new species = 7 nodes
            assert stats['node_count'] == 7
            
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
            
            # Verify they're under Escherichia genus (tax_id 4 in auto-generated sequence)
            escherichia_tax_id = 4  # Auto-generated ID for Escherichia
            assert albertii.parent_id == escherichia_tax_id
            assert fergusonii.parent_id == escherichia_tax_id
    
    def test_import_with_parent_attachment(self, tmp_path: Path):
        """Test importing taxonomy with --parent flag."""
        # Create base database
        base_db = self.create_base_database(tmp_path)
        
        # Create modification file with new branch
        mod_content = """Parent\tChild\tTaxID\tRank
Firmicutes\tBacillus\t1386\tgenus
Bacillus\tBacillus subtilis\t1423\tspecies"""
        
        mod_file = tmp_path / "firmicutes_branch.tsv"
        mod_file.write_text(mod_content)
        
        # Apply modifications with parent attachment
        modify_cmd = ModifyCommand()
        args = self.create_mock_args(
            database=str(base_db),
            mod_file=str(mod_file),
            format='tsv',
            parent='Bacteria'  # Attach Firmicutes under Bacteria
        )
        
        result = modify_cmd.execute(args)
        assert result == 0
        
        # Verify modifications
        with SQLiteTaxonomyRepository(base_db) as repo:
            stats = repo.get_statistics()
            # Should have original 5 + 3 new nodes (Firmicutes, Bacillus, Bacillus subtilis) = 8
            assert stats['node_count'] == 8
            
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
    
    def test_database_merging(self, tmp_path: Path):
        """Test merging one database into another."""
        # Create base database
        base_db = self.create_base_database(tmp_path)
        
        # Create source database to merge
        source_taxonomy = """Parent\tChild\tTaxID\tRank
root\tArchaea\t2157\tsuperkingdom
Archaea\tCrenarchaeota\t28889\tphylum
Crenarchaeota\tThermoproteus\t2285\tgenus"""
        
        source_taxonomy_file = tmp_path / "archaea_taxonomy.tsv"
        source_taxonomy_file.write_text(source_taxonomy)
        
        source_db = tmp_path / "archaea.ftd"
        
        # Create source database
        create_cmd = CreateCommand()
        create_args = self.create_mock_args(
            input=str(source_taxonomy_file),
            database=str(source_db),
            format='tsv'
        )
        
        result = create_cmd.execute(create_args)
        assert result == 0
        
        # Merge source database into base database
        modify_cmd = ModifyCommand()
        merge_args = self.create_mock_args(
            database=str(base_db),
            merge_database=str(source_db)
        )
        
        result = modify_cmd.execute(merge_args)
        assert result == 0
        
        # Verify merge
        with SQLiteTaxonomyRepository(base_db) as repo:
            stats = repo.get_statistics()
            # Should have original 5 + 3 archaea nodes = 8 (archaea root merged with existing root)
            assert stats['node_count'] >= 7
            
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
    
    def test_database_merging_with_replacement(self, tmp_path: Path):
        """Test merging with --replace flag."""
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
            input=str(base_taxonomy_file),
            database=str(base_db),
            format='tsv'
        )
        
        result = create_cmd.execute(base_args)
        assert result == 0
        
        # Create replacement database
        replacement_taxonomy = """Parent\tChild\tTaxID\tRank
root\tProteobacteria\t1224\tphylum
Proteobacteria\tGammaproteobacteria\t1236\tclass
Gammaproteobacteria\tEscherichia\t561\tgenus"""
        
        replacement_taxonomy_file = tmp_path / "replacement.tsv"
        replacement_taxonomy_file.write_text(replacement_taxonomy)
        
        replacement_db = tmp_path / "replacement.ftd"
        
        replacement_args = self.create_mock_args(
            input=str(replacement_taxonomy_file),
            database=str(replacement_db),
            format='tsv'
        )
        
        result = create_cmd.execute(replacement_args)
        assert result == 0
        
        # Merge with replacement
        modify_cmd = ModifyCommand()
        merge_args = self.create_mock_args(
            database=str(base_db),
            merge_database=str(replacement_db),
            parent='Bacteria',
            replace=True
        )
        
        result = modify_cmd.execute(merge_args)
        assert result == 0
        
        # Verify replacement
        with SQLiteTaxonomyRepository(base_db) as repo:
            # Should no longer have Alphaproteobacteria
            alpha_found = False
            gamma_found = False
            
            tree = repo.load_tree()
            for node in tree:
                if "Alphaproteobacteria" in node.name:
                    alpha_found = True
                elif "Gammaproteobacteria" in node.name:
                    gamma_found = True
            
            assert not alpha_found  # Should be replaced
            assert gamma_found      # Should be present from replacement
    
    def test_dry_run_functionality(self, tmp_path: Path):
        """Test dry-run functionality doesn't make changes."""
        # Create base database
        base_db = self.create_base_database(tmp_path)
        
        # Get initial state
        with SQLiteTaxonomyRepository(base_db) as repo:
            initial_count = repo.get_statistics()['node_count']
        
        # Create modification file
        mod_content = """Parent\tChild\tTaxID\tRank
Escherichia\tEscherichia vulneris\t103240\tspecies"""
        
        mod_file = tmp_path / "dry_run_test.tsv"
        mod_file.write_text(mod_content)
        
        # Run with dry-run
        modify_cmd = ModifyCommand()
        args = self.create_mock_args(
            database=str(base_db),
            mod_file=str(mod_file),
            format='tsv',
            dry_run=True
        )
        
        result = modify_cmd.execute(args)
        assert result == 0
        
        # Verify no changes were made
        with SQLiteTaxonomyRepository(base_db) as repo:
            final_count = repo.get_statistics()['node_count']
            assert final_count == initial_count  # Should be unchanged
    
    def test_silva_format_modification(self, tmp_path: Path):
        """Test modification with SILVA format files."""
        # Create base SILVA database
        silva_base = """AB000001\tBacteria;Proteobacteria;Gammaproteobacteria"""
        
        silva_base_file = tmp_path / "silva_base.txt"
        silva_base_file.write_text(silva_base)
        
        base_db = tmp_path / "silva_base.ftd"
        
        create_cmd = CreateCommand()
        create_args = self.create_mock_args(
            input=str(silva_base_file),
            database=str(base_db),
            format='silva',
            no_header=True
        )
        
        result = create_cmd.execute(create_args)
        assert result == 0
        
        # Create SILVA modification
        silva_mod = """AB000002\tBacteria;Firmicutes;Bacilli"""
        
        silva_mod_file = tmp_path / "silva_mod.txt"
        silva_mod_file.write_text(silva_mod)
        
        # Apply modification
        modify_cmd = ModifyCommand()
        mod_args = self.create_mock_args(
            database=str(base_db),
            mod_file=str(silva_mod_file),
            format='silva'
        )
        
        result = modify_cmd.execute(mod_args)
        assert result == 0
        
        # Verify both branches exist
        with SQLiteTaxonomyRepository(base_db) as repo:
            proteobacteria_found = False
            firmicutes_found = False
            
            tree = repo.load_tree()
            for node in tree:
                if "Proteobacteria" in node.name:
                    proteobacteria_found = True
                elif "Firmicutes" in node.name:
                    firmicutes_found = True
            
            assert proteobacteria_found
            assert firmicutes_found