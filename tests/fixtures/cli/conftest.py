"""CLI test configuration and fixtures."""

import pytest
import tempfile
import argparse
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any, List, Optional

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, GenomeInfo, TaxonomicRank
from flextaxd.database.sqlite import SQLiteTaxonomyRepository


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture  
def sample_taxonomy_tree():
    """Create a sample taxonomy tree for testing."""
    tree = TaxonomyTree()
    
    # Create a simple taxonomy: root -> bacteria -> proteobacteria -> e.coli
    root = TaxonomyNode(tax_id=1, name="root", rank=TaxonomicRank.ROOT)
    bacteria = TaxonomyNode(tax_id=2, name="Bacteria", rank=TaxonomicRank.SUPERKINGDOM, parent_id=1)
    proteobacteria = TaxonomyNode(tax_id=3, name="Proteobacteria", rank=TaxonomicRank.PHYLUM, parent_id=2)  
    ecoli = TaxonomyNode(tax_id=4, name="Escherichia coli", rank=TaxonomicRank.SPECIES, parent_id=3)
    
    for node in [root, bacteria, proteobacteria, ecoli]:
        tree.add_node(node)
    
    # Add some genomes
    genome1 = GenomeInfo(
        genome_id="ecoli_k12", 
        tax_id=4,
        file_path="/genomes/ecoli_k12.fasta",
        sequence_length=4641652,
        sequence_type="genome",
        assembly_accession="GCF_000005825.2",
        source="NCBI"
    )
    
    genome2 = GenomeInfo(
        genome_id="ecoli_o157",
        tax_id=4,
        file_path="/genomes/ecoli_o157.fasta", 
        sequence_length=5528445,
        sequence_type="genome",
        assembly_accession="GCF_000008865.2",
        source="NCBI"
    )
    
    tree.add_genome(genome1)
    tree.add_genome(genome2)
    
    return tree


@pytest.fixture
def mock_repository(sample_taxonomy_tree):
    """Create a mocked repository."""
    mock_repo = Mock(spec=SQLiteTaxonomyRepository)
    mock_repo.load_tree.return_value = sample_taxonomy_tree
    mock_repo.save_tree.return_value = None
    mock_repo.__enter__.return_value = mock_repo
    mock_repo.__exit__.return_value = None
    return mock_repo


@pytest.fixture
def sample_database_path(temp_dir):
    """Create a sample database file path."""
    db_path = temp_dir / "test.ftd"
    # Create an empty file to simulate existing database
    db_path.touch()
    return str(db_path)


@pytest.fixture  
def sample_input_files(temp_dir):
    """Create sample input files for testing."""
    files = {}
    
    # TSV taxonomy file
    tsv_content = """tax_id\tparent_id\tname\trank
1\t\troot\troot
2\t1\tBacteria\tsuperkingdom
3\t2\tProteobacteria\tphylum
4\t3\tEscherichia coli\tspecies
"""
    tsv_file = temp_dir / "taxonomy.tsv"
    tsv_file.write_text(tsv_content)
    files["tsv"] = str(tsv_file)
    
    # NCBI names.dmp style file
    names_content = """1\t|\troot\t|\t\t|\tscientific name\t|
2\t|\tBacteria\t|\t\t|\tscientific name\t|
3\t|\tProteobacteria\t|\t\t|\tscientific name\t|
4\t|\tEscherichia coli\t|\t\t|\tscientific name\t|
"""
    names_file = temp_dir / "names.dmp"  
    names_file.write_text(names_content)
    
    # NCBI nodes.dmp style file
    nodes_content = """1\t|\t1\t|\troot\t|\t\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|
2\t|\t1\t|\tsuperkingdom\t|\t\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|
3\t|\t2\t|\tphylum\t|\t\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|
4\t|\t3\t|\tspecies\t|\t\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|
"""
    nodes_file = temp_dir / "nodes.dmp"
    nodes_file.write_text(nodes_content)
    
    # Create NCBI directory
    ncbi_dir = temp_dir / "ncbi_dump"
    ncbi_dir.mkdir()
    (ncbi_dir / "names.dmp").write_text(names_content)
    (ncbi_dir / "nodes.dmp").write_text(nodes_content)
    files["ncbi"] = str(ncbi_dir)
    
    # GTDB taxonomy file  
    gtdb_content = """d__Bacteria;p__Proteobacteria;c__Gammaproteobacteria;o__Enterobacteriales;f__Enterobacteriaceae;g__Escherichia;s__Escherichia coli
"""
    gtdb_file = temp_dir / "gtdb_taxonomy.tsv" 
    gtdb_file.write_text(gtdb_content)
    files["gtdb"] = str(gtdb_file)
    
    # QIIME taxonomy file
    qiime_content = """taxon_123\tBacteria;Proteobacteria;Gammaproteobacteria;Enterobacteriales;Enterobacteriaceae;Escherichia;Escherichia coli
"""
    qiime_file = temp_dir / "qiime_taxonomy.txt"
    qiime_file.write_text(qiime_content)
    files["qiime"] = str(qiime_file)
    
    return files


@pytest.fixture
def mock_args():
    """Create mock argparse.Namespace objects for different commands."""
    def _create_args(**kwargs):
        args = argparse.Namespace()
        for key, value in kwargs.items():
            setattr(args, key, value)
        return args
    return _create_args


@pytest.fixture
def mock_input_output():
    """Mock input/output functions for CLI interaction testing."""
    with patch("builtins.input") as mock_input, \
         patch("builtins.print") as mock_print:
        yield {
            "input": mock_input,
            "print": mock_print
        }


@pytest.fixture
def cli_runner():
    """Provide utilities for running CLI commands in tests."""
    class CLIRunner:
        def __init__(self):
            self.captured_output = []
            self.captured_errors = []
            
        def run_command(self, command_class, args_dict, expected_exit_code=0):
            """Run a CLI command and capture results."""
            command = command_class()
            args = argparse.Namespace(**args_dict)
            
            try:
                result = command.execute(args)
                exit_code = result if result is not None else 0
            except SystemExit as e:
                exit_code = e.code
            except Exception as e:
                exit_code = 1
                self.captured_errors.append(str(e))
            
            return exit_code
            
        def assert_success(self, exit_code):
            """Assert command succeeded."""
            assert exit_code == 0, f"Command failed with exit code {exit_code}"
            
        def assert_failure(self, exit_code, expected_code=1):
            """Assert command failed with expected code.""" 
            assert exit_code == expected_code, f"Expected exit code {expected_code}, got {exit_code}"
    
    return CLIRunner()


class MockLogger:
    """Mock logger for testing."""
    def __init__(self):
        self.debug_calls = []
        self.info_calls = []
        self.warning_calls = []
        self.error_calls = []
        
    def debug(self, msg, *args, **kwargs):
        self.debug_calls.append(msg)
        
    def info(self, msg, *args, **kwargs):
        self.info_calls.append(msg)
        
    def warning(self, msg, *args, **kwargs):
        self.warning_calls.append(msg)
        
    def error(self, msg, *args, **kwargs):
        self.error_calls.append(msg)


@pytest.fixture
def mock_logger():
    """Provide a mock logger for testing."""
    return MockLogger()


@pytest.fixture
def cli_test_data():
    """Provide common CLI test data structures."""
    return {
        "valid_formats": ["tsv", "ncbi", "gtdb", "qiime", "silva", "cansnper"],
        "valid_classifiers": ["ncbi", "kraken2", "diamond", "ganon", "ganon2", "kaiju", "malt", "melon", "sourmash", "sylph", "metabuli", "metacache", "mmseqs2", "centrifuge"],
        "valid_export_formats": ["tsv", "json", "newick", "accession2taxid", "nucl2taxid", "prot2taxid", "genome_sizes", "malt_mapdb", "kmcp"],
        "valid_ranks": ["root", "superkingdom", "phylum", "class", "order", "family", "genus", "species"],
        "invalid_paths": ["/nonexistent/path", "", "   ", "/root/forbidden"],
        "empty_files": [],
        "sample_modifications": [
            {"action": "add", "name": "New Species", "parent_id": 4, "rank": "species"},
            {"action": "update", "tax_id": 4, "name": "Updated Name"},
            {"action": "delete", "tax_id": 4}
        ]
    }


@pytest.fixture  
def patch_filesystem():
    """Patch filesystem operations for testing."""
    patches = {}
    
    with patch("pathlib.Path.exists") as mock_exists, \
         patch("pathlib.Path.is_file") as mock_is_file, \
         patch("pathlib.Path.is_dir") as mock_is_dir, \
         patch("pathlib.Path.mkdir") as mock_mkdir, \
         patch("pathlib.Path.stat") as mock_stat:
        
        # Default behaviors
        mock_exists.return_value = True
        mock_is_file.return_value = True
        mock_is_dir.return_value = False
        
        # Mock file stats
        mock_stat_obj = Mock()
        mock_stat_obj.st_size = 1024  # Non-empty file
        mock_stat.return_value = mock_stat_obj
        
        patches.update({
            "exists": mock_exists,
            "is_file": mock_is_file, 
            "is_dir": mock_is_dir,
            "mkdir": mock_mkdir,
            "stat": mock_stat
        })
        
        yield patches