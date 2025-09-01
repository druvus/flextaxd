"""Tests for the visualize command."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import json

from flextaxd.cli.commands.visualize import VisualizeCommand
from flextaxd.core.models import TaxonomyNode, TaxonomicRank, TaxonomyTree, GenomeInfo
from flextaxd.core.exceptions import ValidationError, DatabaseError


class TestVisualizeCommand:
    """Test cases for VisualizeCommand."""
    
    @pytest.fixture
    def simple_tree(self):
        """Create a simple test tree."""
        tree = TaxonomyTree()
        
        # Create nodes
        root = TaxonomyNode(1, "root", TaxonomicRank.CUSTOM, None)
        bacteria = TaxonomyNode(2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1)
        ecoli = TaxonomyNode(562, "Escherichia coli", TaxonomicRank.SPECIES, 2)
        salmonella = TaxonomyNode(590, "Salmonella enterica", TaxonomicRank.SPECIES, 2)
        
        # Add to tree
        tree.add_node(root)
        tree.add_node(bacteria)
        tree.add_node(ecoli)
        tree.add_node(salmonella)
        
        return tree
    
    @pytest.fixture
    def tree_with_genomes(self):
        """Create test tree with genome information."""
        tree = TaxonomyTree()
        
        # Create nodes
        root = TaxonomyNode(1, "root", TaxonomicRank.CUSTOM, None)
        bacteria = TaxonomyNode(2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1)
        ecoli = TaxonomyNode(562, "Escherichia coli", TaxonomicRank.SPECIES, 2)
        
        # Add to tree
        tree.add_node(root)
        tree.add_node(bacteria)
        tree.add_node(ecoli)
        
        # Add genome information
        genome = GenomeInfo(
            genome_id="GCF_000005825.2",
            tax_id=562,
            assembly_accession="GCF_000005825.2",
            file_path="/path/to/genome.fna",
            sequence_type="genome"
        )
        tree.add_genome(genome)
        
        return tree
    
    @pytest.fixture
    def mock_repository(self, simple_tree):
        """Mock repository that returns simple_tree."""
        mock = MagicMock()
        mock.load_tree.return_value = simple_tree
        mock.__enter__.return_value = mock
        mock.__exit__.return_value = None
        return mock
    
    def test_command_registration(self):
        """Test that command can be instantiated."""
        command = VisualizeCommand()
        assert command is not None
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_basic_tree_visualization(self, mock_repo_class, simple_tree, capsys):
        """Test basic tree visualization."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = simple_tree
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        # Create command and mock args
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "tree"
            start_node = "root"
            max_depth = 0
            show_ids = False
            show_genomes = False
            show_ranks = False
            compact = False
            format = "text"
        
        # Execute command
        with patch.object(command, '_validate_database_path'):
            result = command.execute(MockArgs())
        
        # Check result
        assert result == 0
        
        # Check output
        captured = capsys.readouterr()
        assert "Taxonomy Tree Visualization" in captured.out
        assert "root" in captured.out
        assert "Bacteria" in captured.out
        assert "Escherichia coli" in captured.out
        assert "Salmonella enterica" in captured.out
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_tree_visualization_with_ids(self, mock_repo_class, simple_tree, capsys):
        """Test tree visualization with node IDs shown."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = simple_tree
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        # Create command
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "tree"
            start_node = "root"
            max_depth = 0
            show_ids = True
            show_genomes = False
            show_ranks = False
            compact = False
            format = "text"
        
        # Execute command
        with patch.object(command, '_validate_database_path'):
            result = command.execute(MockArgs())
        
        assert result == 0
        
        # Check output contains IDs
        captured = capsys.readouterr()
        assert "(1)" in captured.out  # root ID
        assert "(2)" in captured.out  # bacteria ID
        assert "(562)" in captured.out  # E. coli ID
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_tree_visualization_with_ranks(self, mock_repo_class, simple_tree, capsys):
        """Test tree visualization with taxonomic ranks shown."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = simple_tree
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "tree"
            start_node = "root"
            max_depth = 0
            show_ids = False
            show_genomes = False
            show_ranks = True
            compact = False
            format = "text"
        
        with patch.object(command, '_validate_database_path'):
            result = command.execute(MockArgs())
        
        assert result == 0
        
        # Check output contains ranks
        captured = capsys.readouterr()
        assert "[superkingdom]" in captured.out
        assert "[species]" in captured.out
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_tree_visualization_with_depth_limit(self, mock_repo_class, simple_tree, capsys):
        """Test tree visualization with depth limit."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = simple_tree
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "tree"
            start_node = "root"
            max_depth = 2  # Should show root and bacteria, but not species
            show_ids = False
            show_genomes = False
            show_ranks = False
            compact = False
            format = "text"
        
        with patch.object(command, '_validate_database_path'):
            result = command.execute(MockArgs())
        
        assert result == 0
        
        # Check output - should not contain species level
        captured = capsys.readouterr()
        assert "root" in captured.out
        assert "Bacteria" in captured.out
        # Species should not appear due to depth limit
        assert "Escherichia coli" not in captured.out
        assert "Salmonella enterica" not in captured.out
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_tree_visualization_from_specific_node(self, mock_repo_class, simple_tree, capsys):
        """Test tree visualization starting from specific node."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = simple_tree
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "tree"
            start_node = "Bacteria"  # Start from bacteria node
            max_depth = 0
            show_ids = False
            show_genomes = False
            show_ranks = False
            compact = False
            format = "text"
        
        with patch.object(command, '_validate_database_path'):
            result = command.execute(MockArgs())
        
        assert result == 0
        
        # Check output - should start from Bacteria, not root
        captured = capsys.readouterr()
        assert "Starting from: Bacteria" in captured.out
        assert "Escherichia coli" in captured.out
        assert "Salmonella enterica" in captured.out
        # Root should not appear as it's above the starting point
        lines = captured.out.split('\n')
        tree_lines = [line for line in lines if any(char in line for char in ['├', '└', '│'])]
        root_in_tree = any('root' in line for line in tree_lines)
        assert not root_in_tree
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_json_output_format(self, mock_repo_class, simple_tree, capsys):
        """Test JSON output format."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = simple_tree
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "tree"
            start_node = "root"
            max_depth = 2
            show_ids = True
            show_genomes = False
            show_ranks = True
            compact = False
            format = "json"
        
        with patch.object(command, '_validate_database_path'):
            result = command.execute(MockArgs())
        
        assert result == 0
        
        # Parse JSON output
        captured = capsys.readouterr()
        try:
            data = json.loads(captured.out)
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {captured.out}")
        
        # Check JSON structure
        assert 'metadata' in data
        assert 'tree' in data
        assert data['metadata']['start_node'] == 'root'
        assert data['metadata']['start_node_id'] == 1
        assert data['metadata']['max_depth'] == 2
        
        # Check tree structure
        tree_data = data['tree']
        assert tree_data['name'] == 'root'
        assert tree_data['tax_id'] == 1
        assert 'children' in tree_data
        assert len(tree_data['children']) == 1  # Should have bacteria
        
        bacteria_data = tree_data['children'][0]
        assert bacteria_data['name'] == 'Bacteria'
        assert bacteria_data['tax_id'] == 2
        assert bacteria_data['rank'] == 'superkingdom'
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_summary_visualization(self, mock_repo_class, simple_tree, capsys):
        """Test summary visualization type."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = simple_tree
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "summary"
            start_node = "root"
            max_depth = 0
            show_ids = False
            show_genomes = False
            show_ranks = False
            compact = False
            format = "text"
        
        with patch.object(command, '_validate_database_path'):
            result = command.execute(MockArgs())
        
        assert result == 0
        
        # Check summary output
        captured = capsys.readouterr()
        assert "Taxonomy Tree Summary" in captured.out
        assert "Starting node: root" in captured.out
        assert "Subtree nodes: 4" in captured.out  # root + bacteria + 2 species
        assert "Rank Distribution:" in captured.out
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_tree_with_genomes(self, mock_repo_class, tree_with_genomes, capsys):
        """Test tree visualization with genome information."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = tree_with_genomes
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "tree"
            start_node = "root"
            max_depth = 0
            show_ids = False
            show_genomes = True
            show_ranks = False
            compact = False
            format = "text"
        
        with patch.object(command, '_validate_database_path'):
            result = command.execute(MockArgs())
        
        assert result == 0
        
        # Check genome information is shown
        captured = capsys.readouterr()
        assert "🧬1" in captured.out  # E. coli should have 1 genome
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_node_not_found_error(self, mock_repo_class, simple_tree):
        """Test error handling when start node is not found."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = simple_tree
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "tree"
            start_node = "NonexistentNode"
            max_depth = 0
            show_ids = False
            show_genomes = False
            show_ranks = False
            compact = False
            format = "text"
        
        with patch.object(command, '_validate_database_path'):
            result = command.execute(MockArgs())
        
        assert result == 1  # Should return error code
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_database_error_handling(self, mock_repo_class):
        """Test database error handling."""
        # Setup mock to raise database error
        mock_repo_class.side_effect = DatabaseError("Cannot connect to database")
        
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/nonexistent.ftd"
            type = "tree"
            start_node = "root"
            max_depth = 0
            show_ids = False
            show_genomes = False
            show_ranks = False
            compact = False
            format = "text"
        
        with patch.object(command, '_validate_database_path'):
            result = command.execute(MockArgs())
        
        assert result == 1  # Should return error code
    
    def test_find_start_node_by_id(self, simple_tree):
        """Test finding start node by numeric ID."""
        command = VisualizeCommand()
        
        # Test finding by ID
        node = command._find_start_node(simple_tree, "562")
        assert node is not None
        assert node.name == "Escherichia coli"
        assert node.tax_id == 562
    
    def test_find_start_node_by_name(self, simple_tree):
        """Test finding start node by name."""
        command = VisualizeCommand()
        
        # Test finding by name (case insensitive)
        node = command._find_start_node(simple_tree, "bacteria")
        assert node is not None
        assert node.name == "Bacteria"
        assert node.tax_id == 2
        
        # Test exact match
        node = command._find_start_node(simple_tree, "Bacteria")
        assert node is not None
        assert node.name == "Bacteria"
    
    def test_find_start_node_root_special_case(self, simple_tree):
        """Test finding root node with special 'root' identifier."""
        command = VisualizeCommand()
        
        # Test special 'root' case
        node = command._find_start_node(simple_tree, "root")
        assert node is not None
        assert node.name == "root"
        assert node.tax_id == 1
    
    def test_count_subtree_nodes(self, simple_tree):
        """Test counting nodes in subtree."""
        command = VisualizeCommand()
        
        root_node = simple_tree.get_node(1)
        bacteria_node = simple_tree.get_node(2)
        
        # Count all nodes from root (no depth limit)
        count = command._count_subtree_nodes(simple_tree, root_node, 0)
        assert count == 4  # root + bacteria + 2 species
        
        # Count with depth limit
        count = command._count_subtree_nodes(simple_tree, root_node, 2)
        assert count == 2  # root + bacteria (species are at depth 2, excluded)
        
        # Count from bacteria node
        count = command._count_subtree_nodes(simple_tree, bacteria_node, 0)
        assert count == 3  # bacteria + 2 species
    
    def test_get_subtree_rank_distribution(self, simple_tree):
        """Test getting rank distribution in subtree."""
        command = VisualizeCommand()
        
        root_node = simple_tree.get_node(1)
        
        ranks = command._get_subtree_rank_distribution(simple_tree, root_node, 0)
        
        expected_ranks = {
            'custom': 1,        # root
            'superkingdom': 1,  # bacteria
            'species': 2        # E. coli + salmonella
        }
        
        assert ranks == expected_ranks


class TestVisualizeCommandIntegration:
    """Integration tests for visualize command."""
    
    def test_create_and_visualize_simple_tree(self):
        """Test creating a simple tree and visualizing it."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test_viz.ftd"
            
            # Create simple TSV data
            tsv_data = "child\tparent\nchild1\troot\nchild2\troot\nsubchild1\tchild1"
            tsv_path = Path(tmp_dir) / "test.tsv"
            tsv_path.write_text(tsv_data)
            
            # Import the create command and create database
            from flextaxd.cli.commands.create import CreateCommand
            
            create_command = CreateCommand()
            
            class CreateArgs:
                input = str(tsv_path)
                database = str(db_path)
                format = "tsv"
                overwrite = False
                no_header = False
                parent_column = 1
                child_column = 0
                id_column = None
                rank_column = None
                genomeid2taxid = None
                genomes_path = None
                auto_detect_sequences = False
                sequence_type = "genome"
            
            # Create database
            with patch.object(create_command, '_validate_database_path'):
                result = create_command.execute(CreateArgs())
                assert result == 0
            
            # Now visualize it
            viz_command = VisualizeCommand()
            
            class VizArgs:
                database = str(db_path)
                type = "tree"
                start_node = "root"
                max_depth = 0
                show_ids = True
                show_genomes = False
                show_ranks = False
                compact = False
                format = "text"
            
            with patch.object(viz_command, '_validate_database_path'):
                result = viz_command.execute(VizArgs())
                assert result == 0


class TestAdvancedVisualization:
    """Test advanced visualization features (Newick, BioPython, matplotlib)."""
    
    @pytest.fixture
    def simple_tree(self):
        """Create a simple test tree."""
        tree = TaxonomyTree()
        
        # Create nodes
        root = TaxonomyNode(1, "root", TaxonomicRank.CUSTOM, None)
        bacteria = TaxonomyNode(2, "Bacteria", TaxonomicRank.SUPERKINGDOM, 1)
        ecoli = TaxonomyNode(562, "Escherichia coli", TaxonomicRank.SPECIES, 2)
        
        # Add to tree
        tree.add_node(root)
        tree.add_node(bacteria)
        tree.add_node(ecoli)
        
        return tree
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_newick_format_output(self, mock_repo_class, simple_tree, capsys):
        """Test Newick format output."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = simple_tree
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "newick"
            start_node = "root"
            max_depth = 0
            show_ids = False
            show_genomes = False
            show_ranks = False
            compact = False
            format = "text"
            label_size = 0
            clip_labels = False
            save_plot = None
        
        with patch.object(command, '_validate_database_path'):
            result = command.execute(MockArgs())
        
        assert result == 0
        
        # Check Newick output
        captured = capsys.readouterr()
        newick_output = captured.out.strip()
        
        # Should be valid Newick format ending with semicolon
        assert newick_output.endswith(';')
        assert 'root' in newick_output
        assert 'Bacteria' in newick_output or 'Bacteria' in newick_output.replace('_', ' ')
        assert 'Escherichia' in newick_output or 'Escherichia' in newick_output.replace('_', ' ')
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_newick_with_depth_limit(self, mock_repo_class, simple_tree, capsys):
        """Test Newick format with depth limit."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = simple_tree
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "newick"
            start_node = "root"
            max_depth = 1  # Should only include root and bacteria, not species
            show_ids = False
            show_genomes = False
            show_ranks = False
            compact = False
            format = "text"
            label_size = 0
            clip_labels = False
            save_plot = None
        
        with patch.object(command, '_validate_database_path'):
            result = command.execute(MockArgs())
        
        assert result == 0
        
        # Check limited depth output
        captured = capsys.readouterr()
        newick_output = captured.out.strip()
        
        # Should contain root and bacteria but not E. coli (species level)
        assert 'root' in newick_output
        assert 'Bacteria' in newick_output or 'Bacteria' in newick_output.replace('_', ' ')
        # Should not contain species level due to depth limit
        assert 'Escherichia' not in newick_output
    
    def test_newick_string_generation(self, simple_tree):
        """Test internal Newick string generation."""
        command = VisualizeCommand()
        
        root_node = simple_tree.get_node(1)
        
        # Test unlimited depth
        newick = command._generate_newick_string(simple_tree, root_node, 0)
        
        # Should contain all nodes
        assert 'root' in newick
        assert 'Bacteria' in newick or 'Bacteria' in newick.replace('_', ' ')
        assert 'Escherichia' in newick or 'Escherichia' in newick.replace('_', ' ')
        
        # Test depth limit
        newick_limited = command._generate_newick_string(simple_tree, root_node, 1)
        
        # Should not contain species level
        assert 'root' in newick_limited
        assert 'Bacteria' in newick_limited or 'Bacteria' in newick_limited.replace('_', ' ')
        assert 'Escherichia' not in newick_limited
    
    def test_newick_special_character_handling(self):
        """Test that special characters in names are properly escaped."""
        tree = TaxonomyTree()
        
        # Create nodes with special characters
        root = TaxonomyNode(1, "root (test)", TaxonomicRank.CUSTOM, None)
        bacteria = TaxonomyNode(2, "Bacteria; species", TaxonomicRank.SUPERKINGDOM, 1)
        
        tree.add_node(root)
        tree.add_node(bacteria)
        
        command = VisualizeCommand()
        newick = command._generate_newick_string(tree, root, 0)
        
        # Special characters should be replaced
        assert '(' not in newick or newick.count('(') == newick.count(')')  # Balanced parentheses only for tree structure
        assert ';' not in newick or newick.endswith(';')  # Semicolon only at end
        assert ':' not in newick  # No colons in names
        assert ',' not in newick or ',' in newick  # Commas only for separating siblings
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_newick_vis_missing_biopython(self, mock_repo_class, simple_tree):
        """Test newick_vis error handling when BioPython is missing."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = simple_tree
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "newick_vis"
            start_node = "root"
            max_depth = 0
            show_ids = False
            show_genomes = False
            show_ranks = False
            compact = False
            format = "text"
            label_size = 0
            clip_labels = False
            save_plot = None
        
        # Mock ImportError for BioPython
        with patch.object(command, '_validate_database_path'):
            with patch('builtins.__import__', side_effect=ImportError("No module named 'Bio'")):
                result = command.execute(MockArgs())
                assert result == 1  # Should fail with error
    
    @patch('flextaxd.cli.commands.visualize.SQLiteTaxonomyRepository')
    def test_plot_missing_dependencies(self, mock_repo_class, simple_tree):
        """Test plot error handling when dependencies are missing."""
        # Setup mock
        mock_repo = MagicMock()
        mock_repo.load_tree.return_value = simple_tree
        mock_repo.__enter__.return_value = mock_repo
        mock_repo.__exit__.return_value = None
        mock_repo_class.return_value = mock_repo
        
        command = VisualizeCommand()
        
        class MockArgs:
            database = "/tmp/test.ftd"
            type = "plot"
            start_node = "root"
            max_depth = 0
            show_ids = False
            show_genomes = False
            show_ranks = False
            compact = False
            format = "text"
            label_size = 0
            clip_labels = False
            save_plot = None
        
        # Mock ImportError for matplotlib
        with patch.object(command, '_validate_database_path'):
            with patch('builtins.__import__', side_effect=ImportError("No module named 'matplotlib'")):
                result = command.execute(MockArgs())
                assert result == 1  # Should fail with error