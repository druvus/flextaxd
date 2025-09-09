# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the FlexTaxD repository.

## Overview

FlexTaxD is a bioinformatics tool for creating, customizing, and managing taxonomy databases from diverse sources. The tool provides support for multiple input formats, extensive export capabilities, and database operations suitable for bioinformatics workflows.

## Current Status (2025-09-09)

### Implemented Features

#### Core Functionality
- **Database Creation**: Support for 6 input formats (NCBI, GTDB, TSV, QIIME, SILVA, CanSNPer)
- **Export System**: 22+ classification tool formats supporting major bioinformatics tools
- **Visualization**: Tree, plot, and Newick format outputs
- **Statistics**: Database analysis with file validation capabilities
- **NCBI Integration**: Direct download via NCBI Datasets API

#### Recent Developments
- **Accession-based download system**: Implementation of precise genome control mechanisms
- **Data integrity**: MD5 checksum storage and validation 
- **Metadata management**: Automated cleaning of NCBI metadata
- **Status reporting**: Enhanced user feedback systems
- **File path management**: Cleanup of orphaned file references

#### Test Infrastructure Improvements (2025-09-09)
- **Critical test failures resolved**: Systematic 4-phase debugging approach implemented
- **CLI Integration Tests**: Export command attribute compatibility fixes
- **Database Tests**: File validation and connection handling improvements
- **Sequence Manager Tests**: Method delegation and implementation enhancements
- **Genome Validator Tests**: Export requirements infrastructure development
- **Test Suite Stability**: Foundation established for continued development

### Areas Requiring Attention

#### Code Organization
- **Orphaned modules**: Approximately 2,000 lines of unused code in performance-related modules
- **Deprecated components**: Legacy files requiring cleanup (modify.py.deprecated)
- **Validation systems**: Multiple overlapping validation approaches requiring consolidation
- **Command structure**: Flat command hierarchy with 20+ commands may benefit from logical grouping

#### Documentation
- **Wiki maintenance**: References to deprecated functionality require updates
- **Workflow documentation**: New features lack comprehensive tutorials
- **API documentation**: Limited in-code documentation for developers
- **Example consistency**: Parameter references across documentation need standardization

### Development Priorities

#### High Priority
1. **Code maintenance**: Remove orphaned modules and consolidate validation systems
2. **Documentation updates**: Align documentation with current implementation
3. **Test coverage expansion**: Develop comprehensive test suites for newer commands
4. **Legacy cleanup**: Remove deprecated files and update references

#### Medium Priority
1. **Command organization**: Consider logical grouping for improved user experience
2. **Performance validation**: Benchmark claims with empirical testing
3. **Integration enhancements**: Expand capabilities for pipeline integration

## Command Reference

### Database Operations
```bash
flextaxd create        # Create taxonomy database from various sources
flextaxd stats         # Display database statistics and metrics
flextaxd validate      # Validate database integrity and consistency
flextaxd purge         # Remove taxonomic nodes without associated data
```

### Data Management
```bash
flextaxd import-accessions  # Import accession-to-taxonomy mappings
flextaxd download          # Download genomes by accession
flextaxd register          # Register sequence files with database
flextaxd list-missing      # Identify missing files in database
```

### Export and Visualization
```bash
flextaxd export           # Export to classification tool formats
flextaxd export-mappings  # Export standard mapping files
flextaxd visualize        # Generate tree visualizations
```

### Node Management
```bash
flextaxd add-node      # Add individual taxonomic node
flextaxd add-genome    # Associate genome with taxonomic node
flextaxd import-tree   # Import complete taxonomy tree
```

## Architecture

```
flextaxd/
├── cli/                  # Command-line interface
│   └── commands/         # 20+ subcommands covering database lifecycle
├── core/                 # Core data structures
│   ├── models.py         # TaxonomyTree, TaxonomyNode, GenomeInfo classes
│   └── *.py             # Note: Contains orphaned performance modules
├── parsers/              # Input format parsers
│   └── [6 format parsers: NCBI, GTDB, TSV, QIIME, SILVA, CanSNPer]
├── exporters/            # Output format exporters  
│   └── [22+ exporters supporting major classification tools]
├── database/             # Database operations
│   └── sqlite.py         # SQLite backend with transaction support
├── validation/           # Validation modules requiring consolidation
├── sequence/             # Sequence management and file tracking
└── utils/                # Utility functions for logging and progress
```

## Development Guidelines

### Implementation Guidelines
1. **Check existing functionality** - Avoid duplication of capabilities
2. **Include test coverage** - Maintain testing for new code paths
3. **Update documentation** - Keep help text and documentation current
4. **Use type annotations** - Maintain type safety throughout codebase
5. **Follow established patterns** - Ensure consistency with existing code

### Testing Requirements
```bash
# Validation before commits
pytest tests/unit/        # Unit test execution
pytest tests/integration/ # Integration test validation
mypy flextaxd/           # Type checking verification
ruff check flextaxd/     # Code linting
```

### Code Patterns
```python
# Database operations
repository = SQLiteTaxonomyRepository(database_path)
tree = repository.get_tree()

# Command implementation
class MyCommand(BaseCommand):
    @staticmethod
    def register_args(parser):
        # Add arguments
    
    def execute(self, args):
        # Implementation

# Error handling
try:
    # Operation
except ValidationError as e:
    logger.error(f"Validation failed: {e}")
    return 1
```

## Performance Characteristics

### Current Limitations
- Primarily single-threaded operations (download operations support concurrency)
- Memory requirements scale with taxonomy size for tree operations
- SQLite backend serializes concurrent write operations

### Optimization Opportunities
- Multiprocessing implementation for batch operations
- Streaming parser development for large file processing
- PostgreSQL evaluation for large-scale deployments
- Progress indicator implementation for long-running operations

## Key Code Components

### Database Schema
- `flextaxd/database/sqlite.py`: Primary database operations implementation
- Schema components: nodes, genomes, accession_mappings tables
- Recent enhancement: file_checksum column for data integrity verification

### Core Data Models
- `flextaxd/core/models.py`: Fundamental data structure definitions
- Primary classes: TaxonomyNode, GenomeInfo, TaxonomyTree
- Recent addition: file_checksum field integration in GenomeInfo

### Download Infrastructure
- `flextaxd/cli/commands/download.py`: Accession-based genome acquisition
- `flextaxd/utils/ncbi_datasets.py`: NCBI Datasets API integration
- Capabilities: flat file organization, MD5 verification, metadata processing

## Current Issues

1. **Deprecated functionality**: modify command referenced in documentation despite deprecation
2. **Test infrastructure**: Some test suites resolved, others require attention
3. **Dependency management**: Orphaned imports creating unnecessary dependencies
4. **Logging consistency**: Variation in logging approaches across modules

## Documentation Status

### Current Documentation
- Basic usage examples and command references
- Export format descriptions for classification tools
- Database creation workflows for various input formats

### Documentation Requiring Updates
- Wiki walkthroughs referencing deprecated command structures
- Accession-based workflow documentation for new features
- Validation system documentation reflecting current implementation
- Performance optimization guidelines for large-scale usage

## Development Roadmap

### Immediate Actions
1. Validation system consolidation into unified framework
2. Deprecated command cleanup and reference updates
3. Test coverage expansion for newer command implementations
4. Documentation alignment with current functionality

### Future Enhancements
1. Progress indicator implementation for user feedback
2. Parallel processing evaluation for performance improvements
3. Database versioning and migration support
4. User interface development for non-command-line usage

### Long-term Considerations
1. Alternative database backend evaluation (PostgreSQL)
2. Cloud storage integration capabilities
3. API development for programmatic access
4. Containerization support for deployment flexibility

## Development Best Practices

1. **Test-driven development** - Implement tests alongside functionality
2. **Pattern consistency** - Follow established architectural principles
3. **Documentation maintenance** - Keep user-facing documentation current
4. **Performance monitoring** - Profile operations with realistic datasets
5. **Input validation** - Implement comprehensive user input validation

## Migration Information

### Command Structure Evolution
- Legacy `flextaxd-create` → Current `flextaxd create`
- Deprecated `flextaxd-modify` → Use `add-node`, `import-tree`
- Parameter standardization with consistent `--` prefix usage

### Database Compatibility
- Backward compatibility maintained for databases from previous versions
- Schema updates applied automatically (e.g., file_checksum column addition)
- Database backup recommended before major operations

## Resources

- **Repository**: https://github.com/FOI-Bioinformatics/flextaxd
- **Documentation**: Repository wiki section
- **Example Data**: Available in wiki/example_data directory
- **Issue Tracking**: GitHub Issues for bug reports and feature requests