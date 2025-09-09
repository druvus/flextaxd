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


class TestGenomeDownloads:
    """Test genome download functionality."""
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_download_genomes_success(self, mock_run_command, mock_validate):
        """Test successful genome download."""
        mock_validate.return_value = True
        
        # Mock successful download
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create mock extracted structure
            data_dir = temp_path / "ncbi_dataset" / "data"
            data_dir.mkdir(parents=True)
            
            # Create mock assembly metadata
            metadata_file = data_dir / "assembly_data_report.jsonl"
            assembly_data = {
                "accession": "GCF_000005825.2", 
                "organism": {"tax_id": 511145, "organism_name": "E. coli"},
                "assembly_info": {"assembly_level": "Complete Genome"}
            }
            with open(metadata_file, 'w') as f:
                f.write(json.dumps(assembly_data) + '\n')
            
            manager = NCBIDatasetsManager()
            
            # Mock helper methods
            with patch.object(manager, '_extract_dataset') as mock_extract:
                with patch.object(manager, '_count_assemblies', return_value=1) as mock_count:
                    with patch.object(manager, '_extract_taxonomy_from_assemblies') as mock_tax:
                        taxonomy_dir = temp_path / "taxonomy"
                        taxonomy_dir.mkdir()
                        (taxonomy_dir / "names.dmp").touch()
                        mock_tax.return_value = taxonomy_dir
                        
                        result = manager.download_genomes(
                            "Escherichia coli", 
                            temp_path, 
                            assembly_level="complete", 
                            max_genomes=5
                        )
                        
                        assert isinstance(result, NCBIDatasetInfo)
                        assert result.taxon == "Escherichia coli"
                        assert result.assembly_level == "complete"
                        assert result.genome_count == 1
                        assert result.genomes_directory == data_dir
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_download_genomes_with_options(self, mock_run_command, mock_validate):
        """Test genome download with additional options."""
        mock_validate.return_value = True
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            data_dir = temp_path / "ncbi_dataset" / "data" 
            data_dir.mkdir(parents=True)
            
            metadata_file = data_dir / "assembly_data_report.jsonl"
            metadata_file.write_text('{"accession": "GCF_123", "organism": {"tax_id": 562}}\n')
            
            manager = NCBIDatasetsManager()
            
            with patch.object(manager, '_extract_dataset'):
                with patch.object(manager, '_count_assemblies', return_value=2):
                    with patch.object(manager, '_extract_taxonomy_from_assemblies', return_value=None):
                        result = manager.download_genomes(
                            "562",
                            temp_path,
                            assembly_level="all",
                            max_genomes=None,
                            include_gbff=True,
                            include_protein=True
                        )
                        
                        # Verify command arguments
                        cmd_call = mock_run_command.call_args[0][0]
                        assert "taxon 562" in cmd_call
                        assert "--include-gbff" in cmd_call
                        assert "--include-protein" in cmd_call
                        assert "--assembly-level" not in cmd_call  # "all" means no filter
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_download_genomes_command_failure(self, mock_run_command, mock_validate):
        """Test handling of failed genome download command."""
        mock_validate.return_value = True
        
        # Mock failed command
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Download failed: Network error"
        mock_run_command.return_value = mock_result
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            manager = NCBIDatasetsManager()
            
            with pytest.raises(NCBIDatasetsError, match="Genome download failed: Download failed: Network error"):
                manager.download_genomes("InvalidTaxon", temp_path)
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")  
    def test_download_genomes_missing_metadata(self, mock_run_command, mock_validate):
        """Test handling of missing assembly metadata file."""
        mock_validate.return_value = True
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            manager = NCBIDatasetsManager()
            
            with patch.object(manager, '_extract_dataset'):
                with pytest.raises(NCBIDatasetsError, match="Assembly metadata file not found"):
                    manager.download_genomes("Escherichia coli", temp_path)


class TestGenomesByAccession:
    """Test downloading genomes by specific accession numbers."""
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_download_genomes_by_accession_success(self, mock_run_command, mock_validate):
        """Test successful download by accession."""
        mock_validate.return_value = True
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result
        
        accessions = ["GCF_000005825.2", "GCF_000009605.1"]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create mock directory structure
            data_dir = temp_path / "ncbi_dataset" / "data"
            data_dir.mkdir(parents=True)
            
            # Create mock genome files
            for acc in accessions:
                acc_dir = data_dir / acc
                acc_dir.mkdir()
                genome_file = acc_dir / f"{acc}_genomic.fna"
                genome_file.write_text(f">genome_{acc}\nATCGATCG\n")
            
            # Create MD5 file
            md5_file = temp_path / "md5sum.txt"
            md5_content = ""
            for acc in accessions:
                md5_content += f"abc123def456  ncbi_dataset/data/{acc}/{acc}_genomic.fna\n"
            md5_file.write_text(md5_content)
            
            manager = NCBIDatasetsManager()
            
            # Create expected zip file (mock the download result)
            zip_file = temp_path / "dataset.zip"
            zip_file.write_text("mock zip content")  # Create the file the code expects
            
            with patch.object(manager, '_extract_dataset'):
                result = manager.download_genomes_by_accession(
                    accessions, temp_path, flatten_files=True
                )
                
                assert result['downloaded'] == accessions
                assert result['failed'] == []
                assert len(result['genome_files']) == 2
                
                # Check that files were flattened to root directory
                for acc in accessions:
                    expected_file = temp_path / f"{acc}_genomic.fna"
                    assert expected_file.exists()
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_download_genomes_by_accession_keep_structure(self, mock_run_command, mock_validate):
        """Test download by accession keeping nested structure."""
        mock_validate.return_value = True
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result
        
        accessions = ["GCF_000005825.2"]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            data_dir = temp_path / "ncbi_dataset" / "data" 
            data_dir.mkdir(parents=True)
            
            acc_dir = data_dir / accessions[0]
            acc_dir.mkdir()
            genome_file = acc_dir / f"{accessions[0]}_genomic.fna"
            genome_file.write_text(">genome\nATCG\n")
            
            manager = NCBIDatasetsManager()
            
            # Create expected zip file (mock the download result)
            zip_file = temp_path / "dataset.zip"
            zip_file.write_text("mock zip content")  # Create the file the code expects
            
            with patch.object(manager, '_extract_dataset'):
                result = manager.download_genomes_by_accession(
                    accessions, temp_path, flatten_files=False, keep_metadata=True
                )
                
                assert result['downloaded'] == accessions
                # Verify file stays in nested structure
                assert result['genome_files'][accessions[0]].resolve() == genome_file.resolve()
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")  
    def test_download_genomes_by_accession_invalid_accessions(self, mock_validate):
        """Test handling of invalid accession numbers."""
        mock_validate.return_value = True
        
        invalid_accessions = ["INVALID_123", "NOT_AN_ACCESSION"]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            manager = NCBIDatasetsManager()
            result = manager.download_genomes_by_accession(invalid_accessions, temp_path)
            
            assert result['downloaded'] == []
            assert result['failed'] == invalid_accessions
            assert result['genome_files'] == {}
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_download_genomes_by_accession_command_failure(self, mock_run_command, mock_validate):
        """Test handling of failed download command."""
        mock_validate.return_value = True
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Invalid accession numbers"
        mock_run_command.return_value = mock_result
        
        accessions = ["GCF_000005825.2"]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            manager = NCBIDatasetsManager()
            
            with pytest.raises(NCBIDatasetsError, match="Genome download by accession failed"):
                manager.download_genomes_by_accession(accessions, temp_path)


class TestDatabaseCreation:
    """Test FlexTaxD database creation from NCBI datasets."""
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_create_flextaxd_database_taxonomy_only(self, mock_validate):
        """Test creating database with taxonomy only."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create taxonomy directory structure
            taxonomy_dir = temp_path / "taxonomy"
            taxonomy_dir.mkdir()
            names_file = taxonomy_dir / "names.dmp"
            nodes_file = taxonomy_dir / "nodes.dmp"
            
            # Create basic dump files
            names_file.write_text("1\t|\troot\t|\t\t|\tscientific name\t|\n")
            nodes_file.write_text("1\t|\t1\t|\troot\t|\t\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\n")
            
            dataset_info = NCBIDatasetInfo(
                taxon="test",
                assembly_level="taxonomy_only", 
                genome_count=0,
                download_path=temp_path,
                metadata_file=temp_path / "taxonomy.jsonl",
                taxonomy_file=names_file
            )
            
            database_path = temp_path / "test.ftd"
            
            manager = NCBIDatasetsManager()
            
            # Mock the parser and tree components
            with patch("flextaxd.parsers.ncbi.NCBITaxonomyParser") as mock_parser:
                with patch("flextaxd.database.sqlite.SQLiteTaxonomyRepository") as mock_repo:
                    mock_tree = Mock()
                    mock_tree.node_count = 1
                    mock_parser.return_value.parse.return_value = mock_tree
                    
                    mock_repo_instance = Mock()
                    mock_repo_instance.__enter__ = Mock(return_value=mock_repo_instance)
                    mock_repo_instance.__exit__ = Mock(return_value=None)
                    mock_repo_instance.get_statistics.return_value = {"nodes": 1, "genomes": 0}
                    mock_repo.return_value = mock_repo_instance
                    
                    stats = manager.create_flextaxd_database(dataset_info, database_path, include_genomes=False)
                    
                    assert stats["nodes"] == 1
                    assert stats["genomes"] == 0
                    mock_parser.return_value.parse.assert_called_once_with(taxonomy_dir)
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_create_flextaxd_database_with_genomes(self, mock_validate):
        """Test creating database with genome information."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create required files  
            taxonomy_dir = temp_path / "taxonomy"
            taxonomy_dir.mkdir()
            (taxonomy_dir / "names.dmp").write_text("562\t|\tE. coli\t|\t\t|\tscientific name\t|\n")
            (taxonomy_dir / "nodes.dmp").write_text("562\t|\t561\t|\tspecies\t|\t\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\t0\t|\n")
            
            genomes_dir = temp_path / "genomes"
            genomes_dir.mkdir()
            
            metadata_file = temp_path / "assembly_data_report.jsonl"
            assembly_data = {
                "accession": "GCF_000005825.2",
                "organism": {"tax_id": 562, "organism_name": "E. coli"}, 
                "assembly_info": {"assembly_level": "Complete Genome"}
            }
            metadata_file.write_text(json.dumps(assembly_data) + '\n')
            
            dataset_info = NCBIDatasetInfo(
                taxon="Escherichia coli",
                assembly_level="complete",
                genome_count=1,
                download_path=temp_path,
                metadata_file=metadata_file,
                taxonomy_file=taxonomy_dir / "names.dmp",
                genomes_directory=genomes_dir
            )
            
            database_path = temp_path / "ecoli.ftd"
            
            manager = NCBIDatasetsManager()
            
            with patch("flextaxd.parsers.ncbi.NCBITaxonomyParser") as mock_parser:
                with patch("flextaxd.database.sqlite.SQLiteTaxonomyRepository") as mock_repo:
                    with patch.object(manager, '_add_genome_info_to_tree', return_value=1) as mock_add_genomes:
                        mock_tree = Mock()
                        mock_tree.node_count = 1
                        mock_parser.return_value.parse.return_value = mock_tree
                        
                        mock_repo_instance = Mock()
                        mock_repo_instance.__enter__ = Mock(return_value=mock_repo_instance)
                        mock_repo_instance.__exit__ = Mock(return_value=None)
                        mock_repo_instance.get_statistics.return_value = {"nodes": 1, "genomes": 1}
                        mock_repo.return_value = mock_repo_instance
                        
                        stats = manager.create_flextaxd_database(dataset_info, database_path, include_genomes=True)
                        
                        assert stats["nodes"] == 1
                        assert stats["genomes"] == 1
                        mock_add_genomes.assert_called_once_with(mock_tree, metadata_file, genomes_dir)
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_create_flextaxd_database_no_taxonomy_file(self, mock_validate):
        """Test error when no taxonomy file is available."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            dataset_info = NCBIDatasetInfo(
                taxon="test",
                assembly_level="complete",
                genome_count=0,
                download_path=temp_path,
                metadata_file=temp_path / "metadata.jsonl",
                taxonomy_file=None  # No taxonomy file
            )
            
            database_path = temp_path / "test.ftd"
            
            manager = NCBIDatasetsManager()
            
            with pytest.raises(NCBIDatasetsError, match="No taxonomy file available in dataset"):
                manager.create_flextaxd_database(dataset_info, database_path)


class TestHelperMethods:
    """Test helper methods for file processing and data extraction."""
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_extract_dataset_success(self, mock_validate):
        """Test successful dataset extraction."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create a test zip file
            import zipfile
            zip_path = temp_path / "test_dataset.zip"
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr("data/test_file.txt", "test content")
                zf.writestr("metadata.json", '{"test": true}')
            
            manager = NCBIDatasetsManager()
            manager._extract_dataset(zip_path, temp_path)
            
            # Verify extraction
            assert (temp_path / "data" / "test_file.txt").exists()
            assert (temp_path / "metadata.json").exists()
            
            # Verify zip file was removed  
            assert not zip_path.exists()
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_extract_dataset_bad_zip(self, mock_validate):
        """Test handling of corrupted zip files.""" 
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create invalid zip file
            zip_path = temp_path / "bad.zip"
            zip_path.write_text("not a zip file")
            
            manager = NCBIDatasetsManager()
            
            with pytest.raises(NCBIDatasetsError, match="Invalid zip file"):
                manager._extract_dataset(zip_path, temp_path)
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_count_assemblies(self, mock_validate):
        """Test counting assemblies from metadata file."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create mock metadata file
            metadata_file = temp_path / "assembly_data_report.jsonl"
            assembly_data = [
                {"accession": "GCF_001", "organism": {"tax_id": 562}},
                {"accession": "GCF_002", "organism": {"tax_id": 563}},
                {"accession": "GCF_003", "organism": {"tax_id": 564}}
            ]
            
            with open(metadata_file, 'w') as f:
                for data in assembly_data:
                    f.write(json.dumps(data) + '\n')
            
            manager = NCBIDatasetsManager()
            count = manager._count_assemblies(metadata_file)
            
            assert count == 3
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_count_assemblies_missing_file(self, mock_validate):
        """Test counting assemblies when metadata file is missing."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            manager = NCBIDatasetsManager()
            count = manager._count_assemblies(temp_path / "nonexistent.jsonl")
            
            assert count == 0
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_extract_taxonomy_from_assemblies(self, mock_validate):
        """Test extracting taxonomy information from assembly metadata."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create assembly metadata
            metadata_file = temp_path / "assembly_data_report.jsonl"
            assembly_data = [
                {
                    "accession": "GCF_000005825.2",
                    "organism": {
                        "tax_id": 511145,
                        "organism_name": "Escherichia coli str. K-12 substr. MG1655"
                    }
                },
                {
                    "accession": "GCF_000009605.1",
                    "organism": {
                        "tax_id": 386585,
                        "organism_name": "Escherichia coli O157:H7 str. Sakai"
                    }
                }
            ]
            
            with open(metadata_file, 'w') as f:
                for data in assembly_data:
                    f.write(json.dumps(data) + '\n')
            
            manager = NCBIDatasetsManager()
            taxonomy_dir = manager._extract_taxonomy_from_assemblies(metadata_file, temp_path)
            
            assert taxonomy_dir is not None
            assert (taxonomy_dir / "names.dmp").exists()
            assert (taxonomy_dir / "nodes.dmp").exists()
            
            # Verify names.dmp content
            with open(taxonomy_dir / "names.dmp") as f:
                names_content = f.read()
                assert "511145\t|\tEscherichia coli str. K-12 substr. MG1655" in names_content
                assert "386585\t|\tEscherichia coli O157:H7 str. Sakai" in names_content
            
            # Verify nodes.dmp content
            with open(taxonomy_dir / "nodes.dmp") as f:
                nodes_content = f.read()
                assert "511145\t|\t511145\t|\tspecies" in nodes_content
                assert "386585\t|\t386585\t|\tspecies" in nodes_content
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_extract_taxonomy_from_assemblies_empty_metadata(self, mock_validate):
        """Test extracting taxonomy when metadata has no organism information."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create metadata without organism info
            metadata_file = temp_path / "assembly_data_report.jsonl"
            metadata_file.write_text('{"accession": "GCF_123", "other_info": "no organism"}\n')
            
            manager = NCBIDatasetsManager()
            result = manager._extract_taxonomy_from_assemblies(metadata_file, temp_path)
            
            assert result is None
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists") 
    def test_extract_taxonomy_from_assemblies_invalid_json(self, mock_validate):
        """Test handling of invalid JSON in assembly metadata."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create invalid JSON metadata
            metadata_file = temp_path / "assembly_data_report.jsonl"
            metadata_file.write_text('{"invalid": json content}\n')
            
            manager = NCBIDatasetsManager()
            result = manager._extract_taxonomy_from_assemblies(metadata_file, temp_path)
            
            assert result is None
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_add_genome_info_to_tree(self, mock_validate):
        """Test adding genome information to taxonomy tree."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create mock genomes directory structure
            genomes_dir = temp_path / "genomes"
            genomes_dir.mkdir()
            
            accession = "GCF_000005825.2"
            assembly_dir = genomes_dir / accession
            assembly_dir.mkdir()
            
            # Create FASTA file
            fasta_file = assembly_dir / f"{accession}_genomic.fna"
            fasta_file.write_text(f">sequence1\nATCGATCG\n")
            
            # Create assembly metadata
            metadata_file = temp_path / "assembly_data_report.jsonl"
            assembly_data = {
                "accession": accession,
                "organism": {
                    "tax_id": 511145,
                    "organism_name": "Escherichia coli K-12"
                },
                "assembly_info": {
                    "assembly_level": "Complete Genome"
                }
            }
            metadata_file.write_text(json.dumps(assembly_data) + '\n')
            
            # Create mock tree
            mock_tree = Mock()
            
            manager = NCBIDatasetsManager()
            genomes_added = manager._add_genome_info_to_tree(mock_tree, metadata_file, genomes_dir)
            
            assert genomes_added == 1
            mock_tree.add_genome.assert_called_once()
            
            # Verify genome info passed to tree
            call_args = mock_tree.add_genome.call_args[0][0]
            assert call_args.genome_id == accession
            assert call_args.tax_id == 511145
            assert call_args.file_path == str(fasta_file)
            assert call_args.source == "NCBI"
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_add_genome_info_to_tree_missing_accession(self, mock_validate):
        """Test adding genome info when accession is missing."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create metadata without accession
            metadata_file = temp_path / "assembly_data_report.jsonl"
            invalid_data = {"organism": {"tax_id": 562}}  # Missing accession
            metadata_file.write_text(json.dumps(invalid_data) + '\n')
            
            genomes_dir = temp_path / "genomes"
            genomes_dir.mkdir()
            
            mock_tree = Mock()
            
            manager = NCBIDatasetsManager()
            genomes_added = manager._add_genome_info_to_tree(mock_tree, metadata_file, genomes_dir)
            
            assert genomes_added == 0
            mock_tree.add_genome.assert_not_called()


class TestFileManagement:
    """Test file management and cleanup functionality."""
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_catalog_downloaded_genomes_flatten_files(self, mock_validate):
        """Test cataloging downloaded genomes with file flattening."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create mock NCBI dataset structure
            data_dir = temp_path / "ncbi_dataset" / "data"
            data_dir.mkdir(parents=True)
            
            accessions = ["GCF_000005825.2", "GCF_000009605.1"]
            
            # Create mock genome files  
            for acc in accessions:
                acc_dir = data_dir / acc
                acc_dir.mkdir()
                fasta_file = acc_dir / f"{acc}_genomic.fna"
                fasta_file.write_text(f">genome_{acc}\nATCG\n")
            
            manager = NCBIDatasetsManager()
            genome_files = manager._catalog_downloaded_genomes(
                temp_path, accessions, flatten_files=True, remove_ncbi_dirs=True
            )
            
            assert len(genome_files) == 2
            
            # Verify files were flattened to root directory
            for acc in accessions:
                assert acc in genome_files
                expected_path = temp_path / f"{acc}_genomic.fna"
                assert genome_files[acc] == expected_path
                assert expected_path.exists()
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_catalog_downloaded_genomes_keep_structure(self, mock_validate):
        """Test cataloging genomes while keeping nested structure."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            data_dir = temp_path / "ncbi_dataset" / "data"
            data_dir.mkdir(parents=True)
            
            accession = "GCF_000005825.2"
            acc_dir = data_dir / accession
            acc_dir.mkdir()
            fasta_file = acc_dir / f"{accession}_genomic.fna"
            fasta_file.write_text(">genome\nATCG\n")
            
            manager = NCBIDatasetsManager()
            genome_files = manager._catalog_downloaded_genomes(
                temp_path, [accession], flatten_files=False, remove_ncbi_dirs=False
            )
            
            assert len(genome_files) == 1
            assert genome_files[accession] == fasta_file
            assert fasta_file.exists()
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_catalog_downloaded_genomes_missing_files(self, mock_validate):
        """Test cataloging when some genome files are missing."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            data_dir = temp_path / "ncbi_dataset" / "data"
            data_dir.mkdir(parents=True)
            
            # Create structure for only one accession
            acc1 = "GCF_000005825.2"
            acc2 = "GCF_000009605.1"  # This one will be missing
            
            acc_dir = data_dir / acc1
            acc_dir.mkdir()
            fasta_file = acc_dir / f"{acc1}_genomic.fna"
            fasta_file.write_text(">genome\nATCG\n")
            
            manager = NCBIDatasetsManager()
            genome_files = manager._catalog_downloaded_genomes(
                temp_path, [acc1, acc2], flatten_files=True
            )
            
            # Only one file should be found
            assert len(genome_files) == 1
            assert acc1 in genome_files
            assert acc2 not in genome_files
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_parse_md5sum_file(self, mock_validate):
        """Test parsing MD5 checksum file."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create sample MD5 file
            md5_file = temp_path / "md5sum.txt"
            md5_content = """# MD5 checksums generated by NCBI
abc123def456  ncbi_dataset/data/GCF_000005825.2/GCF_000005825.2_genomic.fna
789012345678  ncbi_dataset/data/GCF_000009605.1/GCF_000009605.1_genomic.fna"""
            md5_file.write_text(md5_content)
            
            # Create genome files mapping
            genome_files = {
                "GCF_000005825.2": temp_path / "GCF_000005825.2_genomic.fna",
                "GCF_000009605.1": temp_path / "GCF_000009605.1_genomic.fna"
            }
            
            manager = NCBIDatasetsManager()
            checksums = manager._parse_md5sum_file(md5_file, genome_files)
            
            assert len(checksums) == 2
            assert checksums[str(genome_files["GCF_000005825.2"])] == "abc123def456"
            assert checksums[str(genome_files["GCF_000009605.1"])] == "789012345678"
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_parse_md5sum_file_invalid_format(self, mock_validate):
        """Test parsing MD5 file with invalid format lines."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create MD5 file with invalid lines
            md5_file = temp_path / "md5sum.txt"
            md5_content = """abc123def456 invalid_format_no_double_space
def456789012  valid_format_file.fna
invalid line without checksum"""
            md5_file.write_text(md5_content)
            
            genome_files = {"test": temp_path / "valid_format_file.fna"}
            
            manager = NCBIDatasetsManager()
            checksums = manager._parse_md5sum_file(md5_file, genome_files)
            
            # Only the valid format line should be parsed
            assert len(checksums) == 1
            assert checksums[str(genome_files["test"])] == "def456789012"
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_process_metadata_and_cleanup(self, mock_validate):
        """Test processing metadata and cleanup functionality."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create metadata files
            md5_file = temp_path / "md5sum.txt"
            readme_file = temp_path / "README.md"
            ncbi_dir = temp_path / "ncbi_dataset"
            
            md5_file.write_text("abc123  test_file.fna\n")
            readme_file.write_text("# README\nTest readme content")
            ncbi_dir.mkdir()
            (ncbi_dir / "data").mkdir()
            (ncbi_dir / "metadata.json").write_text('{"test": true}')
            
            genome_files = {"test": temp_path / "test_file.fna"}
            
            manager = NCBIDatasetsManager()
            checksums = manager._process_metadata_and_cleanup(
                temp_path, genome_files, keep_metadata=False
            )
            
            # Verify checksums were parsed
            assert len(checksums) == 1
            assert checksums[str(genome_files["test"])] == "abc123"
            
            # Verify cleanup happened
            assert not md5_file.exists()
            assert not readme_file.exists()
            assert not ncbi_dir.exists()
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_process_metadata_and_cleanup_keep_metadata(self, mock_validate):
        """Test processing with metadata preservation."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            md5_file = temp_path / "md5sum.txt"
            readme_file = temp_path / "README.md"
            
            md5_file.write_text("abc123  test_file.fna\n")
            readme_file.write_text("# README")
            
            genome_files = {"test": temp_path / "test_file.fna"}
            
            manager = NCBIDatasetsManager()
            checksums = manager._process_metadata_and_cleanup(
                temp_path, genome_files, keep_metadata=True
            )
            
            # Verify checksums were parsed but files kept
            assert len(checksums) == 1
            assert md5_file.exists()
            assert readme_file.exists()
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_cleanup_empty_directories(self, mock_validate):
        """Test recursive cleanup of empty directories."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create nested directory structure
            root_dir = temp_path / "ncbi_dataset"
            data_dir = root_dir / "data"
            acc_dir1 = data_dir / "GCF_001"
            acc_dir2 = data_dir / "GCF_002"
            
            root_dir.mkdir()
            data_dir.mkdir()
            acc_dir1.mkdir()
            acc_dir2.mkdir()
            
            # Add a file to one directory so it won't be removed
            (acc_dir2 / "remaining_file.txt").write_text("content")
            
            manager = NCBIDatasetsManager()
            manager._cleanup_empty_directories(root_dir)
            
            # Empty directories should be removed
            assert not acc_dir1.exists()
            
            # Directory with file should remain
            assert acc_dir2.exists()
            assert data_dir.exists()
            assert root_dir.exists()
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_cleanup_empty_directories_nonexistent(self, mock_validate):
        """Test cleanup when root directory doesn't exist."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            nonexistent_dir = temp_path / "does_not_exist"
            
            manager = NCBIDatasetsManager()
            # Should not raise an error
            manager._cleanup_empty_directories(nonexistent_dir)


class TestAdvancedErrorHandling:
    """Test comprehensive error handling scenarios."""
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_download_taxonomy_subprocess_error(self, mock_run_command, mock_validate):
        """Test handling of subprocess errors in taxonomy download."""
        mock_validate.return_value = True
        mock_run_command.side_effect = SubprocessError("Command execution failed")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            manager = NCBIDatasetsManager()
            
            with pytest.raises(NCBIDatasetsError, match="Failed to download taxonomy for test: Command execution failed"):
                manager.download_taxonomy("test", temp_path)
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_download_genomes_subprocess_error(self, mock_run_command, mock_validate):
        """Test handling of subprocess errors in genome download."""
        mock_validate.return_value = True
        mock_run_command.side_effect = SubprocessError("Network timeout")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            manager = NCBIDatasetsManager()
            
            with pytest.raises(NCBIDatasetsError, match="Failed to download genomes for test: Network timeout"):
                manager.download_genomes("test", temp_path)
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_download_genomes_by_accession_subprocess_error(self, mock_run_command, mock_validate):
        """Test handling of subprocess errors in accession-based download."""
        mock_validate.return_value = True
        mock_run_command.side_effect = SubprocessError("Invalid parameters")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            manager = NCBIDatasetsManager()
            
            with pytest.raises(NCBIDatasetsError, match="Failed to download genomes by accession: Invalid parameters"):
                manager.download_genomes_by_accession(["GCF_000005825.2"], temp_path)
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_validate_taxon_json_decode_error(self, mock_validate):
        """Test taxon validation with invalid JSON response."""
        mock_validate.return_value = True
        
        with patch("flextaxd.utils.ncbi_datasets.run_command_safely") as mock_run_command:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "invalid json response"
            mock_run_command.return_value = mock_result
            
            manager = NCBIDatasetsManager()
            result = manager.validate_taxon("test_taxon")
            
            # Should handle JSON decode error gracefully
            assert result["valid"] is True
            assert result["summary"] is None


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    def test_custom_cache_dir(self, mock_validate):
        """Test initialization with custom cache directory."""
        mock_validate.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_cache = Path(temp_dir) / "custom_ncbi_cache"
            
            manager = NCBIDatasetsManager(cache_dir=custom_cache)
            
            assert manager.cache_dir == custom_cache
            assert custom_cache.exists()
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_download_taxonomy_alternative_metadata_locations(self, mock_run_command, mock_validate):
        """Test finding taxonomy metadata in alternative locations."""
        mock_validate.return_value = True
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create metadata in alternative location
            data_dir = temp_path / "data"
            data_dir.mkdir()
            taxonomy_file = data_dir / "taxonomy.jsonl"
            taxonomy_file.write_text('{"tax_id": 1, "sci_name": "root"}\n')
            
            manager = NCBIDatasetsManager()
            
            with patch.object(manager, '_extract_dataset'):
                with patch.object(manager, '_convert_jsonl_to_dumps') as mock_convert:
                    taxonomy_dir = temp_path / "taxonomy_dumps"
                    taxonomy_dir.mkdir()
                    (taxonomy_dir / "names.dmp").touch()
                    mock_convert.return_value = taxonomy_dir
                    
                    result = manager.download_taxonomy("test", temp_path)
                    
                    # Should find metadata in alternative location
                    assert result.metadata_file == taxonomy_file
    
    @patch("flextaxd.utils.ncbi_datasets.validate_command_exists")
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_download_genomes_alternative_data_locations(self, mock_run_command, mock_validate):
        """Test finding genome data in alternative locations."""
        mock_validate.return_value = True
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_command.return_value = mock_result
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create metadata in alternative location
            data_dir = temp_path / "data"
            data_dir.mkdir()
            metadata_file = data_dir / "assembly_data_report.jsonl"
            metadata_file.write_text('{"accession": "GCF_001", "organism": {"tax_id": 562}}\n')
            
            manager = NCBIDatasetsManager()
            
            with patch.object(manager, '_extract_dataset'):
                with patch.object(manager, '_count_assemblies', return_value=1):
                    with patch.object(manager, '_extract_taxonomy_from_assemblies', return_value=None):
                        result = manager.download_genomes("test", temp_path)
                        
                        # Should find metadata and data dir in alternative location
                        assert result.metadata_file == metadata_file
                        assert result.genomes_directory == data_dir
    
    @patch("flextaxd.utils.ncbi_datasets.run_command_safely")
    def test_check_installation_exception_handling(self, mock_run_command):
        """Test installation check with unexpected exceptions."""
        mock_run_command.side_effect = Exception("Unexpected error")
        
        result = check_ncbi_datasets_installation()
        
        assert result["installed"] is False
        assert "Error checking installation: Unexpected error" in result["error"]