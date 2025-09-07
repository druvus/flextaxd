"""Tests for NCBI datasets integration utilities."""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from flextaxd.utils.ncbi_datasets import (
    NCBIDatasetsManager,
    NCBIDatasetsError,
    NCBIDatasetInfo,
    AssemblyInfo,
    check_ncbi_datasets_installation,
)
from flextaxd.utils.subprocess_utils import SubprocessError


class TestNCBIDatasetsManager:
    """Test NCBI Datasets manager functionality."""
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_init_with_datasets_installed(self, mock_validate):
        """Test initialization when datasets command is available."""
        mock_validate.return_value = True
        
        manager = NCBIDatasetsManager()
        assert manager.cache_dir == Path.home() / ".flextaxd" / "ncbi_cache"
        mock_validate.assert_called_once_with("datasets")
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_init_without_datasets_installed(self, mock_validate):
        """Test initialization when datasets command is not available."""
        mock_validate.return_value = False
        
        with pytest.raises(NCBIDatasetsError, match="NCBI Datasets command not found"):
            NCBIDatasetsManager()
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_validate_taxon_success(self, mock_run_command, mock_validate):
        """Test successful taxon validation."""
        mock_validate.return_value = True
        
        # Mock successful command response
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '{"taxon": "Escherichia coli", "valid": true}'
        mock_run_command.return_value = mock_result
        
        manager = NCBIDatasetsManager()
        result = manager.validate_taxon("Escherichia coli")
        
        assert result["valid"] is True
        assert result["taxon"] == "Escherichia coli"
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_validate_taxon_failure(self, mock_run_command, mock_validate):
        """Test failed taxon validation."""
        mock_validate.return_value = True
        
        # Mock failed command response
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Taxon not found"
        mock_run_command.return_value = mock_result
        
        manager = NCBIDatasetsManager()
        result = manager.validate_taxon("InvalidTaxon")
        
        assert result["valid"] is False
        assert "Taxon not found" in result["error"]
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_get_available_assembly_levels(self, mock_validate):
        """Test getting available assembly levels."""
        mock_validate.return_value = True
        
        manager = NCBIDatasetsManager()
        levels = manager.get_available_assembly_levels()
        
        expected = ["complete", "chromosome", "scaffold", "contig", "all"]
        assert levels == expected
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_download_taxonomy(self, mock_run_command, mock_validate):
        """Test taxonomy download functionality."""
        mock_validate.return_value = True
        
        # Mock successful download
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result
        
        # Create temporary directory structure
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Mock the extracted structure
            data_dir = temp_path / "ncbi_dataset" / "data"
            data_dir.mkdir(parents=True)
            
            # Create mock taxonomy.jsonl
            taxonomy_file = data_dir / "taxonomy.jsonl"
            with open(taxonomy_file, 'w') as f:
                f.write('{"tax_id": 562, "sci_name": "Escherichia coli", "parent_tax_id": 561, "rank": "species"}\n')
            
            manager = NCBIDatasetsManager()
            
            # Mock the extraction method
            with patch.object(manager, '_extract_dataset'):
                with patch.object(manager, '_convert_jsonl_to_dumps') as mock_convert:
                    taxonomy_dir = temp_path / "taxonomy_dumps"
                    taxonomy_dir.mkdir()
                    (taxonomy_dir / "names.dmp").touch()
                    mock_convert.return_value = taxonomy_dir
                    
                    result = manager.download_taxonomy("Escherichia coli", temp_path)
                    
                    assert isinstance(result, NCBIDatasetInfo)
                    assert result.taxon == "Escherichia coli"
                    assert result.assembly_level == "taxonomy_only"
                    assert result.genome_count == 0
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_convert_jsonl_to_dumps(self, mock_validate):
        """Test conversion from JSONL to dump format."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create mock JSONL file
            jsonl_file = temp_path / "taxonomy.jsonl"
            with open(jsonl_file, 'w') as f:
                f.write('{"tax_id": 1, "sci_name": "root", "parent_tax_id": 1, "rank": "root"}\n')
                f.write('{"tax_id": 562, "sci_name": "Escherichia coli", "parent_tax_id": 561, "rank": "species"}\n')
            
            manager = NCBIDatasetsManager()
            result_dir = manager._convert_jsonl_to_dumps(jsonl_file, temp_path)
            
            assert result_dir.exists()
            assert (result_dir / "names.dmp").exists()
            assert (result_dir / "nodes.dmp").exists()
            
            # Check names.dmp content
            with open(result_dir / "names.dmp") as f:
                names_content = f.read()
                assert "1\t|\troot\t|\t\t|\tscientific name\t|\n" in names_content
                assert "562\t|\tEscherichia coli\t|\t\t|\tscientific name\t|\n" in names_content
            
            # Check nodes.dmp content
            with open(result_dir / "nodes.dmp") as f:
                nodes_content = f.read()
                assert "1\t|\t1\t|\troot\t|\t" in nodes_content
                assert "562\t|\t561\t|\tspecies\t|\t" in nodes_content


class TestNCBIDatasetInfo:
    """Test NCBI dataset info data class."""
    
    def test_ncbi_dataset_info_creation(self):
        """Test creating NCBIDatasetInfo instance."""
        info = NCBIDatasetInfo(
            taxon="Escherichia coli",
            assembly_level="complete",
            genome_count=5,
            download_path=Path("/tmp/test"),
            metadata_file=Path("/tmp/test/metadata.jsonl")
        )
        
        assert info.taxon == "Escherichia coli"
        assert info.assembly_level == "complete"
        assert info.genome_count == 5
        assert info.taxonomy_file is None
        assert info.genomes_directory is None


class TestAssemblyInfo:
    """Test assembly info data class."""
    
    def test_assembly_info_creation(self):
        """Test creating AssemblyInfo instance."""
        info = AssemblyInfo(
            accession="GCF_000005825.2",
            organism_name="Escherichia coli str. K-12 substr. MG1655",
            tax_id=511145,
            assembly_level="Complete Genome"
        )
        
        assert info.accession == "GCF_000005825.2"
        assert info.organism_name == "Escherichia coli str. K-12 substr. MG1655"
        assert info.tax_id == 511145
        assert info.assembly_level == "Complete Genome"
        assert info.genome_size is None


class TestInstallationCheck:
    """Test installation check functionality."""
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_check_installation_success(self, mock_run_command, mock_validate):
        """Test successful installation check."""
        mock_validate.return_value = True
        
        # Mock version command
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "datasets version 13.0.0"
        mock_run_command.return_value = mock_result
        
        result = check_ncbi_datasets_installation()
        
        assert result["installed"] is True
        assert "13.0.0" in result["version"]
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_check_installation_not_found(self, mock_validate):
        """Test installation check when command not found."""
        mock_validate.return_value = False
        
        result = check_ncbi_datasets_installation()
        
        assert result["installed"] is False
        assert "datasets command not found" in result["error"]
        assert "install_instructions" in result
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_check_installation_version_fail(self, mock_run_command, mock_validate):
        """Test installation check when version command fails."""
        mock_validate.return_value = True
        
        # Mock failed version command
        mock_result = Mock()
        mock_result.returncode = 1
        mock_run_command.return_value = mock_result
        
        result = check_ncbi_datasets_installation()
        
        assert result["installed"] is True
        assert result["version"] == "unknown"
        assert "version check failed" in result["warning"]


class TestErrorHandling:
    """Test error handling in NCBI datasets utilities."""
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_subprocess_error_handling(self, mock_run_command, mock_validate):
        """Test handling of subprocess errors."""
        mock_validate.return_value = True
        mock_run_command.side_effect = SubprocessError("Command failed")
        
        manager = NCBIDatasetsManager()
        result = manager.validate_taxon("test")
        
        assert result["valid"] is False
        assert "Command failed" in result["error"]
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_json_parsing_error(self, mock_validate):
        """Test handling of JSON parsing errors."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create invalid JSONL file
            jsonl_file = temp_path / "taxonomy.jsonl"
            with open(jsonl_file, 'w') as f:
                f.write('{"invalid": json}\n')
            
            manager = NCBIDatasetsManager()
            
            with pytest.raises(NCBIDatasetsError, match="Failed to parse taxonomy JSONL"):
                manager._convert_jsonl_to_dumps(jsonl_file, temp_path)
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_missing_metadata_file_error(self, mock_validate):
        """Test handling of missing metadata files."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create dataset info with missing metadata file
            dataset_info = NCBIDatasetInfo(
                taxon="test",
                assembly_level="complete",
                genome_count=0,
                download_path=temp_path,
                metadata_file=temp_path / "nonexistent.jsonl"
            )
            
            manager = NCBIDatasetsManager()
            
            with pytest.raises(NCBIDatasetsError, match="No taxonomy file available"):
                manager.create_flextaxd_database(
                    dataset_info=dataset_info,
                    database_path=temp_path / "test.ftd",
                    include_genomes=False
                )


@pytest.fixture
def sample_assembly_metadata():
    """Sample assembly metadata for testing."""
    return {
        "accession": "GCF_000005825.2",
        "organism": {
            "tax_id": 511145,
            "organism_name": "Escherichia coli str. K-12 substr. MG1655"
        },
        "assembly_info": {
            "assembly_level": "Complete Genome"
        }
    }


@pytest.fixture
def mock_ncbi_manager():
    """Mock NCBI datasets manager for testing."""
    with patch("flextaxd.utils.ncbi_datasets.validate_command_exists", return_value=True):
        manager = NCBIDatasetsManager()
        return manager