"""Mock data and utilities for CLI testing."""

from typing import Dict, Any, List
from unittest.mock import Mock
import argparse

from flextaxd.core.models import TaxonomyTree, TaxonomyNode, GenomeInfo, TaxonomicRank


class MockData:
    """Container for mock data used in CLI tests."""
    
    @staticmethod
    def create_complex_taxonomy_tree() -> TaxonomyTree:
        """Create a complex taxonomy tree for comprehensive testing."""
        tree = TaxonomyTree()
        
        # Create multi-level taxonomy
        #         root(1)
        #        /   |   \
        #   bact(2) arch(3) euk(4)
        #      |      |      |
        #   prot(5)  meth(6) anim(7)
        #   /    \     |      |
        # ecoli(8) sal(9) meta(10) homo(11)
        
        nodes = [
            (1, "root", TaxonomicRank.ROOT, None),
            (2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1),
            (3, "Archaea", TaxonomicRank.SUPERKINGDOM, 1),
            (4, "Eukaryota", TaxonomicRank.SUPERKINGDOM, 1),
            (5, "Proteobacteria", TaxonomicRank.PHYLUM, 2),
            (6, "Methanobrevibacter", TaxonomicRank.GENUS, 3),
            (7, "Animalia", TaxonomicRank.KINGDOM, 4),
            (8, "Escherichia coli", TaxonomicRank.SPECIES, 5),
            (9, "Salmonella enterica", TaxonomicRank.SPECIES, 5),
            (10, "Methanobrevibacter smithii", TaxonomicRank.SPECIES, 6),
            (11, "Homo sapiens", TaxonomicRank.SPECIES, 7),
        ]
        
        for tax_id, name, rank, parent_id in nodes:
            node = TaxonomyNode(tax_id=tax_id, name=name, rank=rank, parent_id=parent_id)
            tree.add_node(node)
        
        # Add diverse genomes
        genomes = [
            GenomeInfo(genome_id="ecoli_k12", tax_id=8, file_path="/genomes/ecoli_k12.fasta", 
                      sequence_length=4641652, sequence_type="genome", assembly_accession="GCF_000005825.2", source="NCBI"),
            GenomeInfo(genome_id="ecoli_o157", tax_id=8, file_path="/genomes/ecoli_o157.fasta",
                      sequence_length=5528445, sequence_type="genome", assembly_accession="GCF_000008865.2", source="NCBI"),
            GenomeInfo(genome_id="salmonella_meta", tax_id=9, assembly_accession="GCF_000006945.2",
                      sequence_length=4857450, sequence_type="genome", source="NCBI"),  # No file_path
            GenomeInfo(genome_id="msmith_genome", tax_id=10, file_path="/archaea/msmith.fasta",
                      sequence_length=1853160, sequence_type="genome", assembly_accession="GCF_000016525.1", source="NCBI"),
            GenomeInfo(genome_id="human_chr1", tax_id=11, assembly_accession="GCF_000001405.40", 
                      sequence_length=248956422, sequence_type="chromosome", source="NCBI"),  # No file_path
        ]
        
        for genome in genomes:
            tree.add_genome(genome)
            
        return tree
    
    @staticmethod
    def get_sample_purge_results() -> Dict[str, Any]:
        """Get sample purge operation results."""
        return {
            "nodes_before": 11,
            "nodes_after": 7,
            "nodes_removed": 4,
            "genomes_retained": 4,
            "lineages_preserved": 3,
            "nodes_with_genomes": 3,
            "essential_nodes_kept": 7
        }
    
    @staticmethod
    def get_sample_stats() -> Dict[str, Any]:
        """Get sample database statistics."""
        return {
            "total_nodes": 11,
            "total_genomes": 5,
            "nodes_with_genomes": 4,
            "average_children_per_node": 1.8,
            "max_depth": 4,
            "rank_distribution": {
                "root": 1,
                "superkingdom": 3, 
                "phylum": 1,
                "kingdom": 1,
                "genus": 1,
                "species": 4
            },
            "genome_distribution": {
                "genome": 3,
                "chromosome": 1,
                "contig": 1
            },
            "source_distribution": {
                "NCBI": 5
            }
        }
    
    @staticmethod
    def get_export_test_data() -> Dict[str, Any]:
        """Get test data for export command testing."""
        return {
            "classifiers": {
                "ncbi": {"files": ["names.dmp", "nodes.dmp"], "dir": True},
                "kraken2": {"files": ["taxonomy.tab"], "dir": True},
                "diamond": {"files": ["prot.accession2taxid"], "dir": True},
                "ganon2": {"files": ["taxonomy.tsv"], "dir": True},
            },
            "formats": {
                "tsv": {"extension": ".tsv", "single_file": True},
                "json": {"extension": ".json", "single_file": True},
                "newick": {"extension": ".nwk", "single_file": True},
                "accession2taxid": {"extension": ".txt", "single_file": True},
            },
            "sample_content": {
                "tsv": "tax_id\tparent_id\tname\trank\n1\t\troot\troot\n",
                "json": '{"nodes": [{"tax_id": 1, "name": "root", "rank": "root"}]}',
                "newick": "(Escherichia_coli:1.0,Salmonella_enterica:1.0)Proteobacteria:1.0;",
            }
        }
    
    @staticmethod
    def get_create_command_args() -> Dict[str, Dict[str, Any]]:
        """Get various argument combinations for create command testing."""
        return {
            "basic_tsv": {
                "input": "/test/taxonomy.tsv",
                "database": "/test/output.ftd",
                "format": "tsv",
                "verbose": False
            },
            "ncbi_format": {
                "input": "/test/ncbi_dump/",
                "database": "/test/ncbi.ftd", 
                "format": "ncbi",
                "verbose": True
            },
            "gtdb_format": {
                "input": "/test/gtdb_taxonomy.tsv",
                "database": "/test/gtdb.ftd",
                "format": "gtdb",
                "verbose": False
            },
            "auto_detect": {
                "input": "/test/taxonomy.tsv",
                "database": "/test/auto.ftd",
                # format will be auto-detected
                "verbose": False
            },
            "with_validation": {
                "input": "/test/taxonomy.tsv",
                "database": "/test/validated.ftd",
                "format": "tsv",
                "validate": True,
                "verbose": True
            }
        }
    
    @staticmethod 
    def get_modify_command_args() -> Dict[str, Dict[str, Any]]:
        """Get various argument combinations for modify command testing."""
        return {
            "add_node": {
                "database": "/test/db.ftd",
                "add_node": "New Species",
                "parent_id": 8,
                "rank": "species",
                "verbose": False
            },
            "update_node": {
                "database": "/test/db.ftd",
                "update_node": 8,
                "name": "Updated Name",
                "verbose": False
            },
            "delete_node": {
                "database": "/test/db.ftd", 
                "delete_node": 8,
                "force": True,
                "verbose": False
            },
            "mod_file": {
                "database": "/test/db.ftd",
                "mod_file": "/test/modifications.tsv",
                "replace": False,
                "verbose": True
            },
            "batch_replace": {
                "database": "/test/db.ftd",
                "mod_file": "/test/replacements.tsv",
                "replace": True,
                "backup": "/test/backup.ftd",
                "verbose": False
            }
        }
    
    @staticmethod
    def get_stats_command_args() -> Dict[str, Dict[str, Any]]:
        """Get various argument combinations for stats command testing."""
        return {
            "basic_stats": {
                "database": "/test/db.ftd",
                "detailed": False,
                "verbose": False
            },
            "detailed_stats": {
                "database": "/test/db.ftd",
                "detailed": True,
                "verbose": True
            },
            "with_output": {
                "database": "/test/db.ftd", 
                "detailed": True,
                "output": "/test/stats.json",
                "verbose": False
            },
            "specific_rank": {
                "database": "/test/db.ftd",
                "detailed": True,
                "rank": "species",
                "verbose": False
            }
        }
    
    @staticmethod
    def get_export_command_args() -> Dict[str, Dict[str, Any]]:
        """Get various argument combinations for export command testing."""
        return {
            "classifier_export": {
                "database": "/test/db.ftd",
                "classifier": "kraken2",
                "output": "/test/kraken2_db/",
                "verbose": False
            },
            "format_export": {
                "database": "/test/db.ftd",
                "format": "tsv",
                "output": "/test/taxonomy.tsv",
                "verbose": False
            },
            "legacy_format": {
                "database": "/test/db.ftd",
                "legacy_format": "ncbi",
                "output": "/test/ncbi_dump/", 
                "verbose": True
            },
            "with_validation": {
                "database": "/test/db.ftd",
                "classifier": "diamond", 
                "output": "/test/diamond_db/",
                "validate": True,
                "verbose": True
            },
            "compressed_output": {
                "database": "/test/db.ftd",
                "format": "json",
                "output": "/test/taxonomy.json.gz",
                "compress": True,
                "verbose": False
            }
        }
    
    @staticmethod
    def get_visualize_command_args() -> Dict[str, Dict[str, Any]]:
        """Get various argument combinations for visualize command testing."""
        return {
            "tree_plot": {
                "database": "/test/db.ftd",
                "type": "tree",
                "output": "/test/tree.png",
                "verbose": False
            },
            "newick_export": {
                "database": "/test/db.ftd", 
                "type": "newick",
                "output": "/test/tree.nwk",
                "verbose": False
            },
            "plot_with_options": {
                "database": "/test/db.ftd",
                "type": "plot",
                "output": "/test/phylo.png",
                "width": 12,
                "height": 8,
                "dpi": 300,
                "verbose": True
            },
            "filtered_tree": {
                "database": "/test/db.ftd",
                "type": "tree", 
                "output": "/test/filtered.png",
                "max_depth": 5,
                "min_genomes": 1,
                "verbose": False
            }
        }
    
    @staticmethod
    def get_validation_errors() -> Dict[str, str]:
        """Get common validation error messages for testing."""
        return {
            "missing_database": "Database file does not exist",
            "invalid_format": "Unknown input format",
            "empty_file": "Input file is empty", 
            "invalid_classifier": "Unknown classifier",
            "invalid_rank": "Invalid taxonomic rank",
            "missing_parent": "Parent node does not exist",
            "circular_dependency": "Would create circular dependency",
            "invalid_output_path": "Cannot create output directory"
        }


class CLITestHelper:
    """Helper utilities for CLI testing."""
    
    @staticmethod
    def create_mock_args(**kwargs) -> argparse.Namespace:
        """Create a mock argparse.Namespace with specified attributes."""
        args = argparse.Namespace()
        for key, value in kwargs.items():
            setattr(args, key, value)
        return args
    
    @staticmethod
    def assert_log_contains(mock_logger, level: str, message: str):
        """Assert that logger was called with specific message."""
        log_calls = getattr(mock_logger, f"{level}_calls", [])
        assert any(message in call for call in log_calls), f"Expected '{message}' in {level} logs: {log_calls}"
    
    @staticmethod
    def assert_file_operations(patches, expected_operations: List[str]):
        """Assert that expected file operations were performed."""
        for operation in expected_operations:
            if operation == "exists":
                assert patches["exists"].called
            elif operation == "mkdir":
                assert patches["mkdir"].called
            elif operation == "is_file":
                assert patches["is_file"].called
            elif operation == "is_dir":
                assert patches["is_dir"].called
    
    @staticmethod
    def setup_filesystem_mock(patches, scenario: str):
        """Set up filesystem mocking for different test scenarios."""
        if scenario == "missing_database":
            patches["exists"].return_value = False
        elif scenario == "empty_file":
            mock_stat = Mock()
            mock_stat.st_size = 0
            patches["stat"].return_value = mock_stat
        elif scenario == "directory_input":
            patches["is_dir"].return_value = True
            patches["is_file"].return_value = False
        elif scenario == "read_only":
            patches["mkdir"].side_effect = OSError("Permission denied")
    
    @staticmethod
    def capture_command_output(command_func, *args, **kwargs):
        """Capture output from command execution."""
        output = []
        errors = []
        
        def mock_print(*args, **kwargs):
            output.append(" ".join(str(arg) for arg in args))
            
        def mock_error(msg):
            errors.append(msg)
        
        with patch("builtins.print", side_effect=mock_print):
            try:
                result = command_func(*args, **kwargs)
                return {"result": result, "output": output, "errors": errors}
            except Exception as e:
                errors.append(str(e))
                return {"result": None, "output": output, "errors": errors}